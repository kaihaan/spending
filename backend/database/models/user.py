# backend/database/models/user.py
"""
User model for authentication and account management.

Maps to: users table
See: .claude/docs/database/DATABASE_SCHEMA.md#1-users
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from database.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    username = Column(String(100), unique=True)
    password_hash = Column(String(255))
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    last_login_at = Column(DateTime(timezone=False))

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
