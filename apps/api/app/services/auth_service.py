"""
Registration, credential verification, and password reset (§6).

Deliberately does NOT touch sessions (see session_service.py) — this
keeps "who is this person and do they know the current password" (a
credentials question) separate from "what does a signed-in browser hold
onto" (a session-lifecycle question). A route handler composes both:
AuthService.authenticate() to check the password, then
SessionService.create_session() to actually log them in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.core.security.errors import AuthErrorCode, GENERIC_LOGIN_FAILURE_MESSAGE
from app.core.security.password_policy import validate_password_strength
from app.core.security.passwords import PasswordHasher, default_password_hasher
from app.core.security.rate_limiter import BackoffLockout
from app.core.security.tokens import IssuedToken, hash_token, is_expired
from app.models.tokens import PasswordResetToken
from app.models.user import User
from app.repositories.rbac_repository import RbacRepository
from app.repositories.token_repository import PasswordResetTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import record_audit_event

PASSWORD_RESET_TTL = timedelta(hours=1)


class AuthService:
    def __init__(
        self,
        db: Session,
        *,
        password_hasher: PasswordHasher = default_password_hasher,
        lockout: Optional[BackoffLockout] = None,
    ):
        self.db = db
        self.hasher = password_hasher
        self.lockout = lockout
        self.users = UserRepository(db)
        self.rbac = RbacRepository(db)
        self.reset_tokens = PasswordResetTokenRepository(db)

    # ------------------------------------------------------------ register

    def register(
        self,
        *,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> User:
        email = email.strip().lower()
        policy = validate_password_strength(password, email=email, first_name=first_name, last_name=last_name)
        if not policy.valid:
            raise AuthError(AuthErrorCode.WEAK_PASSWORD.value, "; ".join(policy.problems))

        if self.users.get_by_email(email) is not None:
            # Registration is the one boundary where we DO tell a caller
            # "you already have an account" (§28 asks us not to reveal
            # this at LOGIN/password-reset — a generic message there
            # would make those flows unusable for a legitimate user who
            # mistyped their password, but leaks nothing an attacker
            # couldn't already learn for free by just trying to register
            # the same address themselves; see docs/SECURITY.md
            # "Enumeration trade-offs").
            raise AuthError(
                AuthErrorCode.EMAIL_ALREADY_REGISTERED.value, "An account with this email already exists."
            )

        user = User(
            email=email,
            password_hash=self.hasher.hash(password),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            status="PENDING_VERIFICATION",
            email_verified=False,
        )
        self.users.add(user)
        self.rbac.assign_role(user.id, "CUSTOMER")

        record_audit_event(
            self.db,
            actor=f"user:{user.id}",
            actor_type="user",
            action="auth.registered",
            resource="user",
            resource_id=str(user.id),
            request_id=request_id,
        )
        self.db.commit()
        return user

    # ------------------------------------------------------------ authenticate

    def authenticate(self, *, email: str, password: str, request_id: Optional[str] = None) -> User:
        """Raises UnauthorizedError with a GENERIC message/code for every
        failure mode — no account, wrong password — collapsed into one
        (§18/§28/§33: never let a login response reveal whether an
        email exists). ACCOUNT_SUSPENDED/ACCOUNT_DISABLED are the only
        exceptions, and only fire AFTER the password has already been
        confirmed correct: telling an attacker who doesn't know the
        password "that account happens to be suspended" would itself be
        an enumeration leak.
        """
        email = email.strip().lower()
        lockout_key = f"login:{email}"
        if self.lockout is not None:
            lock_state = self.lockout.is_locked(lockout_key)
            if not lock_state.allowed:
                raise AuthError(
                    AuthErrorCode.RATE_LIMITED.value, "Too many attempts. Please wait a moment and try again."
                )

        user = self.users.get_by_email(email)
        # Always run verify() even when user is None, against a fixed
        # dummy hash — hashing the SAME cost every time regardless of
        # whether the account exists closes the timing side-channel that
        # would otherwise let an attacker distinguish "no such user"
        # (fast: no hash computed) from "wrong password" (slow: a real
        # Argon2id hash computed) purely from response latency.
        target_hash = user.password_hash if user is not None else _DUMMY_HASH_FOR_TIMING_SAFETY
        password_ok = self.hasher.verify(password, target_hash) and user is not None

        if not password_ok:
            if self.lockout is not None:
                self.lockout.record_failure(lockout_key)
            record_audit_event(
                self.db,
                actor=f"email:{email}",
                actor_type="user",
                action="auth.login_failed",
                resource="user",
                resource_id=(str(user.id) if user else None),
                request_id=request_id,
            )
            self.db.commit()
            raise AuthError(AuthErrorCode.INVALID_CREDENTIALS.value, GENERIC_LOGIN_FAILURE_MESSAGE)

        if self.lockout is not None:
            self.lockout.record_success(lockout_key)

        if user.status == "SUSPENDED":
            record_audit_event(
                self.db, actor=f"user:{user.id}", actor_type="user", action="auth.login_blocked_suspended",
                resource="user", resource_id=str(user.id), request_id=request_id,
            )
            self.db.commit()
            raise AuthError(
                AuthErrorCode.ACCOUNT_SUSPENDED.value, "This account is suspended. Contact support for help."
            )
        if user.status == "DISABLED":
            record_audit_event(
                self.db, actor=f"user:{user.id}", actor_type="user", action="auth.login_blocked_disabled",
                resource="user", resource_id=str(user.id), request_id=request_id,
            )
            self.db.commit()
            raise AuthError(AuthErrorCode.ACCOUNT_DISABLED.value, "This account has been disabled.")

        if self.hasher.needs_rehash(user.password_hash):
            user.password_hash = self.hasher.hash(password)

        user.last_login_at = datetime.now(timezone.utc)
        record_audit_event(
            self.db, actor=f"user:{user.id}", actor_type="user", action="auth.login_succeeded",
            resource="user", resource_id=str(user.id), request_id=request_id,
        )
        self.db.commit()
        return user

    # ------------------------------------------------------------ password change / reset

    def change_password(
        self, user: User, *, current_password: str, new_password: str, request_id: Optional[str] = None
    ) -> None:
        if not self.hasher.verify(current_password, user.password_hash):
            raise AuthError(AuthErrorCode.INVALID_CREDENTIALS.value, "Current password is incorrect.")
        policy = validate_password_strength(
            new_password, email=user.email, first_name=user.first_name, last_name=user.last_name
        )
        if not policy.valid:
            raise AuthError(AuthErrorCode.WEAK_PASSWORD.value, "; ".join(policy.problems))
        user.password_hash = self.hasher.hash(new_password)
        record_audit_event(
            self.db, actor=f"user:{user.id}", actor_type="user", action="auth.password_changed",
            resource="user", resource_id=str(user.id), request_id=request_id,
        )
        self.db.commit()
        # Session revocation on password change (§29) is the route
        # handler's job via SessionService.revoke_all_for_user — kept
        # out of AuthService on purpose, see module docstring.

    def request_password_reset(self, *, email: str, request_id: Optional[str] = None) -> Optional[str]:
        """Returns the RAW reset token, or None if no account matched.
        The distinction only matters to the caller for deciding whether
        to call the email provider — the HTTP response must be the
        SAME generic message either way (§28), never branching on
        whether this returned a token. Never log this return value."""
        email = email.strip().lower()
        user = self.users.get_by_email(email)
        if user is None:
            return None
        self.reset_tokens.invalidate_all_unused_for_user(user.id)
        issued = IssuedToken.issue(ttl=PASSWORD_RESET_TTL)
        self.reset_tokens.add(PasswordResetToken(user_id=user.id, token_hash=issued.hash, expires_at=issued.expires_at))
        record_audit_event(
            self.db, actor=f"user:{user.id}", actor_type="user", action="auth.password_reset_requested",
            resource="user", resource_id=str(user.id), request_id=request_id,
        )
        self.db.commit()
        return issued.raw

    def reset_password(self, *, raw_token: str, new_password: str, request_id: Optional[str] = None) -> User:
        record = self.reset_tokens.get_by_token_hash(hash_token(raw_token))
        if record is None or record.used_at is not None or is_expired(record.expires_at):
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN.value, "This password reset link is invalid or has expired."
            )
        user = self.users.get_by_id(record.user_id)
        if user is None:  # pragma: no cover — FK integrity makes this unreachable in practice
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN.value, "This password reset link is invalid or has expired."
            )
        policy = validate_password_strength(
            new_password, email=user.email, first_name=user.first_name, last_name=user.last_name
        )
        if not policy.valid:
            raise AuthError(AuthErrorCode.WEAK_PASSWORD.value, "; ".join(policy.problems))
        user.password_hash = self.hasher.hash(new_password)
        record.used_at = datetime.now(timezone.utc)
        record_audit_event(
            self.db, actor=f"user:{user.id}", actor_type="user", action="auth.password_reset_completed",
            resource="user", resource_id=str(user.id), request_id=request_id,
        )
        self.db.commit()
        return user


# A fixed, precomputed-at-import-time Argon2id hash of a value nobody will
# ever type, used purely so authenticate() always pays the same hashing
# cost whether or not `email` matched a real user — see the comment at
# its call site above.
_DUMMY_HASH_FOR_TIMING_SAFETY = default_password_hasher.hash("no-such-user-timing-safety-constant-do-not-reuse")
