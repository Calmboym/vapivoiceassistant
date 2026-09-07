from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tokens import EmailVerificationToken, PasswordResetToken


class PasswordResetTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token_hash(self, token_hash: str) -> Optional[PasswordResetToken]:
        return self.db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))

    def invalidate_all_unused_for_user(self, user_id, *, now: Optional[datetime] = None) -> None:
        """§28: a reset token is single-use, and issuing a NEW one
        invalidates any still-outstanding older one so an old emailed
        link can't be used after a newer request superseded it."""
        now = now or datetime.now(timezone.utc)
        tokens = self.db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None)
            )
        )
        for token in tokens:
            token.used_at = now

    def add(self, token: PasswordResetToken) -> PasswordResetToken:
        self.db.add(token)
        self.db.flush()
        return token


class EmailVerificationTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token_hash(self, token_hash: str) -> Optional[EmailVerificationToken]:
        return self.db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash))

    def add(self, token: EmailVerificationToken) -> EmailVerificationToken:
        self.db.add(token)
        self.db.flush()
        return token
