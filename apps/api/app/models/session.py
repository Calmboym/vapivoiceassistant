from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, _utcnow


class Session(Base, UUIDPrimaryKeyMixin):
    """A browser session (§5). Only `session_token_hash` is ever
    persisted — the raw token exists only in the HttpOnly cookie on the
    client and briefly in server memory while handling /auth/login,
    /auth/refresh, or a request's auth dependency. See
    app.core.security.tokens for why an unsalted SHA-256 lookup hash is
    the right call for a 256-bit random token specifically (unlike a
    password)."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    user: Mapped["User"] = relationship(back_populates="sessions")

    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Hashed, never raw — good enough to notice "this session is
    # suddenly being used from a completely different network/client"
    # for abuse detection, without holding a directly-identifying IP
    # indefinitely tied to a person (§24/§36 data-minimization spirit).
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Session {self.id} user={self.user_id}>"
