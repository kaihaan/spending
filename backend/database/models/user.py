# backend/database/models/user.py
"""
User model for authentication and account management.

Maps to:
- users table
- account_mappings table - User-friendly names for bank accounts
- user_sessions table - Session management for authenticated users
- security_audit_log table - Security event tracking

See: .claude/docs/database/DATABASE_SCHEMA.md
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class UserSession(Base):
    """
    Session management for authenticated users.

    Stores session data with expiration and activity tracking.
    """

    __tablename__ = "user_sessions"

    id = Column(String(255), primary_key=True)  # UUID or session token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_data = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    expires_at = Column(DateTime(timezone=False), nullable=False)
    last_activity_at = Column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    __table_args__ = ({"comment": "User sessions for authentication"},)

    def __repr__(self) -> str:
        return f"<UserSession(id={self.id}, user_id={self.user_id})>"


class SecurityAuditLog(Base):
    """
    Security event tracking and audit log.

    Records authentication events, permission changes, and security-relevant actions.
    """

    __tablename__ = "security_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_type = Column(String(50), nullable=False)
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(Text)
    timestamp = Column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    metadata_ = Column(
        "metadata", JSONB, server_default="{}"
    )  # 'metadata' is reserved in SQLAlchemy
    success = Column(Boolean, nullable=False, server_default="false")

    def __repr__(self) -> str:
        return f"<SecurityAuditLog(id={self.id}, event_type={self.event_type})>"
