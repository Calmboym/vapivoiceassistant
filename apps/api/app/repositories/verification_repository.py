from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.verification import VerificationSession


class VerificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token_hash(self, token_hash: str) -> Optional[VerificationSession]:
        return self.db.scalar(select(VerificationSession).where(VerificationSession.token_hash == token_hash))

    def add(self, session: VerificationSession) -> VerificationSession:
        self.db.add(session)
        self.db.flush()
        return session
