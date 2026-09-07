from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.session import Session as SessionModel


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token_hash(self, token_hash: str) -> Optional[SessionModel]:
        return self.db.scalar(select(SessionModel).where(SessionModel.session_token_hash == token_hash))

    def add(self, session: SessionModel) -> SessionModel:
        self.db.add(session)
        self.db.flush()
        return session

    def list_active_for_user(self, user_id) -> list[SessionModel]:
        now = datetime.now(timezone.utc)
        return list(
            self.db.scalars(
                select(SessionModel).where(
                    SessionModel.user_id == user_id,
                    SessionModel.revoked_at.is_(None),
                    SessionModel.expires_at > now,
                )
            )
        )

    def revoke(self, session: SessionModel, *, now: Optional[datetime] = None) -> None:
        session.revoked_at = now or datetime.now(timezone.utc)

    def revoke_all_for_user(self, user_id, *, now: Optional[datetime] = None) -> int:
        """§29: 'logout all sessions' and 'password change revokes
        existing sessions where appropriate'. Returns the count revoked
        (useful for the audit-log metadata)."""
        now = now or datetime.now(timezone.utc)
        sessions = self.list_active_for_user(user_id)
        for session in sessions:
            session.revoked_at = now
        return len(sessions)
