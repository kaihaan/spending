# backend/database/models/user.py
"""
User model for authentication and account management.

Maps to:
- users table
- account_mappings table - User-friendly names for bank accounts

See: .claude/docs/database/DATABASE_SCHEMA.md
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
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


class AccountMapping(Base):
    """
    Maps bank account details (sort code + account number) to friendly names.

    Used for Santander account identification in the UI.
    """

    __tablename__ = "account_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sort_code = Column(String(10), nullable=False)
    account_number = Column(String(20), nullable=False)
    friendly_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "sort_code",
            "account_number",
            name="account_mappings_sort_code_account_number_key",
        ),
    )

    def __repr__(self) -> str:
        return f"<AccountMapping(id={self.id}, friendly_name={self.friendly_name})>"
