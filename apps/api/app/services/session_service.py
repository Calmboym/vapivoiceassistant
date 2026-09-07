"""
Session lifecycle (§5, §29): creation, validation, refresh, revocation.

A route handler never touches app.models.session directly — everything
goes through this service, so "hash before storing, never store the raw
token" (§5) and "rotate the token on refresh" have exactly one
implementation each. See app.core.security.tokens for the underlying
primitives (dependency-free, real unit tests).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.security.csrf import CsrfToken, issue_csrf_token
from app.core.security.tokens import IssuedToken, hash_token, is_expired
from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.services.audit_service import record_audit_event

DEFAULT_SESSION_TTL = timedelta(days=14)


class SessionService:
    def __init__(self, db: DBSession):
        self.db = db
        self.sessions = SessionRepository(db)

    def create_session(
        self,
        user: User,
        *,
        ttl: timedelta = DEFAULT_SESSION_TTL,
        ip_hash: Optional[str] = None,
        user_agent_hash: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> tuple[str, CsrfToken, SessionModel]:
        """Returns (raw_session_token, csrf_token, Session row). The raw
        session token goes into the HttpOnly session cookie; csrf_token
        goes into the separate, JS-readable CSRF cookie (§19) — bound to
        THIS session's id, per app.core.security.csrf. Neither raw value
        is ever persisted — only session_token_hash is."""
        issued = IssuedToken.issue(ttl=ttl)
        session = SessionModel(
            user_id=user.id,
            session_token_hash=issued.hash,
            expires_at=issued.expires_at,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
        )
        self.sessions.add(session)
        csrf_token = issue_csrf_token(str(session.id), get_settings().secret_key)
        record_audit_event(
            self.db, actor=f"user:{user.id}", actor_type="user", action="auth.session_created",
            resource="session", resource_id=str(session.id), request_id=request_id,
        )
        self.db.commit()
        return issued.raw, csrf_token, session

    def validate_session(self, raw_token: str) -> Optional[SessionModel]:
        """Returns the live Session row for a raw cookie value, or None
        if it doesn't exist, is revoked, or is expired. Never raises —
        the caller (app.api.deps.get_current_actor) treats None as
        "anonymous", not a server error."""
        session = self.sessions.get_by_token_hash(hash_token(raw_token))
        if session is None or session.revoked_at is not None or is_expired(session.expires_at):
            return None
        # Known, deliberate simplification: this touches last_used_at in
        # memory but does NOT commit here — get_current_actor() calls
        # this on every request, including pure GETs, and committing on
        # every read would add a DB write to every authenticated request
        # for a field that's advisory (abuse detection / "is this
        # session still active"), not security-critical. It IS persisted
        # whenever the same request separately commits for another
        # reason (any mutating route). A production hardening pass could
        # debounce this to "update at most once per N minutes" instead.
        session.last_used_at = datetime.now(timezone.utc)
        return session

    def refresh_session(self, session: SessionModel, *, ttl: timedelta = DEFAULT_SESSION_TTL) -> str:
        """§6 POST /auth/refresh. Rotates the token — a fresh random
        value with a fresh stored hash — rather than just extending
        expires_at on the same token, so a stolen-but-unused cookie
        value has a bounded useful lifetime even if the legitimate user
        keeps refreshing."""
        issued = IssuedToken.issue(ttl=ttl)
        session.session_token_hash = issued.hash
        session.expires_at = issued.expires_at
        session.last_used_at = datetime.now(timezone.utc)
        self.db.commit()
        return issued.raw

    def revoke(self, session: SessionModel, *, request_id: Optional[str] = None) -> None:
        self.sessions.revoke(session)
        record_audit_event(
            self.db, actor=f"user:{session.user_id}", actor_type="user", action="auth.session_revoked",
            resource="session", resource_id=str(session.id), request_id=request_id,
        )
        self.db.commit()

    def revoke_all_for_user(self, user_id, *, request_id: Optional[str] = None, reason: str = "logout_all") -> int:
        """§29: logout-all, and also called by the route layer on
        password change / admin suspend so an already-issued session
        stops authorizing requests immediately rather than at its
        natural expiry."""
        count = self.sessions.revoke_all_for_user(user_id)
        record_audit_event(
            self.db, actor=f"user:{user_id}", actor_type="user", action="auth.all_sessions_revoked",
            resource="user", resource_id=str(user_id), request_id=request_id, metadata={"count": count, "reason": reason},
        )
        self.db.commit()
        return count
