"""
Authentication endpoints (§6).

Every mutating response sets or clears the session cookie directly — the
raw session token is NEVER present in a JSON response body, only in the
Set-Cookie header (HttpOnly, so client-side JS can't read it either).
Services commit their own transactions (see app/services/auth_service.py,
session_service.py) — this file's job is HTTP plumbing only: parse the
request, call the service, shape the cookie, return the envelope.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps_auth import SESSION_COOKIE_NAME, require_authenticated_user
from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.core.security.actor import CurrentActor
from app.core.security.csrf import CSRF_COOKIE_NAME
from app.core.security.errors import AuthErrorCode, GENERIC_PASSWORD_RESET_MESSAGE
from app.core.security.rate_limiter import BackoffLockout
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    UserOut,
)
from app.schemas.common import ok
from app.services.auth_service import AuthService
from app.services.email_provider import get_email_provider
from app.services.rate_limit_service import RedisRateLimitStore
from app.services.rbac_service import RBACService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


def _lockout() -> BackoffLockout:
    # A fresh RedisRateLimitStore() per call is intentional and cheap —
    # it just wraps whatever app.db.redis_client.get_redis() returns
    # (itself process-cached), so this doesn't reconnect per request.
    return BackoffLockout(RedisRateLimitStore())


def _set_session_cookie(response: Response, raw_token: str, *, max_age_seconds: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=(settings.app_env == "production"),
        samesite="lax",
        path="/",
    )


def _set_csrf_cookie(response: Response, csrf_cookie_value: str, *, max_age_seconds: int) -> None:
    settings = get_settings()
    # NOT httponly — the frontend JS must be able to read this and echo
    # it in the X-CSRF-Token header (§19 / app.middleware.csrf).
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_cookie_value,
        max_age=max_age_seconds,
        httponly=False,
        secure=(settings.app_env == "production"),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


def _user_out(user, roles, permissions) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        status=user.status,
        email_verified=user.email_verified,
        roles=sorted(roles),
        permissions=sorted(permissions),
        created_at=user.created_at,
    )


def _issue_session_and_respond(db: Session, response: Response, user, request_id: str):
    raw_token, csrf_token, session = SessionService(db).create_session(user, request_id=request_id)
    max_age = int((session.expires_at - session.created_at).total_seconds())
    _set_session_cookie(response, raw_token, max_age_seconds=max_age)
    _set_csrf_cookie(response, csrf_token.cookie_value, max_age_seconds=max_age)
    rbac = RBACService(db)
    return ok(_user_out(user, rbac.roles_for_user(user.id), rbac.permissions_for_user(user.id)), request_id)


@router.post("/register")
def register(body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    request_id = _request_id(request)
    user = AuthService(db).register(
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        request_id=request_id,
    )
    return _issue_session_and_respond(db, response, user, request_id)


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    request_id = _request_id(request)
    user = AuthService(db, lockout=_lockout()).authenticate(
        email=body.email, password=body.password, request_id=request_id
    )
    return _issue_session_and_respond(db, response, user, request_id)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    request_id = _request_id(request)
    if session_token:
        session_service = SessionService(db)
        session = session_service.validate_session(session_token)
        if session is not None:
            session_service.revoke(session, request_id=request_id)
    _clear_session_cookie(response)
    return ok({"logged_out": True}, request_id)


@router.post("/logout-all")
def logout_all(
    request: Request,
    response: Response,
    actor: CurrentActor = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    request_id = _request_id(request)
    count = SessionService(db).revoke_all_for_user(actor.user_id, request_id=request_id, reason="logout_all")
    _clear_session_cookie(response)
    return ok({"logged_out": True, "sessions_revoked": count}, request_id)


@router.get("/me")
def me(
    request: Request,
    actor: CurrentActor = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    request_id = _request_id(request)
    user = UserRepository(db).get_by_id(actor.user_id)
    if user is None:  # session outlived the user row — shouldn't happen, fail closed
        raise AuthError(AuthErrorCode.AUTHENTICATION_REQUIRED, "Please sign in to continue.")
    return ok(_user_out(user, actor.roles, actor.permissions), request_id)


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    request_id = _request_id(request)
    if not session_token:
        raise AuthError(AuthErrorCode.AUTHENTICATION_REQUIRED, "Please sign in to continue.")
    session_service = SessionService(db)
    session = session_service.validate_session(session_token)
    if session is None:
        raise AuthError(AuthErrorCode.SESSION_EXPIRED, "Your session has expired. Please sign in again.")
    from app.services.session_service import DEFAULT_SESSION_TTL

    new_raw = session_service.refresh_session(session)
    _set_session_cookie(response, new_raw, max_age_seconds=int(DEFAULT_SESSION_TTL.total_seconds()))
    return ok({"refreshed": True}, request_id)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    actor: CurrentActor = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    request_id = _request_id(request)
    user = UserRepository(db).get_by_id(actor.user_id)
    if user is None:
        raise AuthError(AuthErrorCode.AUTHENTICATION_REQUIRED, "Please sign in to continue.")
    AuthService(db).change_password(
        user, current_password=body.current_password, new_password=body.new_password, request_id=request_id
    )
    # §29: password change revokes existing sessions. Re-issue a fresh
    # one for THIS browser so changing your own password doesn't log you
    # out of the tab you just did it from — every OTHER session is gone.
    session_service = SessionService(db)
    session_service.revoke_all_for_user(actor.user_id, request_id=request_id, reason="password_changed")
    raw_token, csrf_token, session = session_service.create_session(user, request_id=request_id)
    max_age = int((session.expires_at - session.created_at).total_seconds())
    _set_session_cookie(response, raw_token, max_age_seconds=max_age)
    _set_csrf_cookie(response, csrf_token.cookie_value, max_age_seconds=max_age)
    return ok({"password_changed": True}, request_id)


@router.post("/request-password-reset")
def request_password_reset(body: RequestPasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    request_id = _request_id(request)
    raw_token = AuthService(db).request_password_reset(email=body.email, request_id=request_id)
    if raw_token is not None:
        settings = get_settings()
        reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
        get_email_provider().send_password_reset(to_email=body.email, reset_url=reset_url)
    # ALWAYS the same generic response (§28) — never branch the HTTP
    # response itself on whether raw_token was None.
    return ok({"message": GENERIC_PASSWORD_RESET_MESSAGE}, request_id)


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    request_id = _request_id(request)
    user = AuthService(db).reset_password(raw_token=body.token, new_password=body.new_password, request_id=request_id)
    SessionService(db).revoke_all_for_user(user.id, request_id=request_id, reason="password_reset")
    return ok({"password_reset": True}, request_id)
