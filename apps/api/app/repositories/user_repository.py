from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id) -> Optional[User]:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        # Case-insensitive: emails are stored lowercased/stripped at
        # write time (see AuthService.register) and looked up the same
        # way, so "Jane@x.com" and "jane@x.com" are the same account.
        return self.db.scalar(select(User).where(User.email == email.lower().strip()))

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user
