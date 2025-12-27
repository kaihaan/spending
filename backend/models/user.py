"""
User model for Flask-Login authentication

Implements UserMixin interface for session management with secure password hashing.
Uses database_postgres for data persistence with the users table.
"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from typing import Optional, Dict, Any


class User(UserMixin):
    """User model with Flask-Login integration.

    Attributes:
        id: User ID (primary key)
        username: Unique username for login
        email: Unique email address
        password_hash: Hashed password (pbkdf2:sha256:600000)
        is_admin: Admin privilege flag
        is_active: Account active status
        last_login_at: Timestamp of last successful login
        created_at: Account creation timestamp
        updated_at: Last update timestamp
    """

    def __init__(
        self,
        id: int,
        email: str,
        username: Optional[str] = None,
        password_hash: Optional[str] = None,
        is_admin: bool = False,
        is_active: bool = True,
        last_login_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ):
        """Initialize User instance.

        Args:
            id: User ID from database
            email: User email address
            username: Username for login (optional during migration)
            password_hash: Pre-hashed password
            is_admin: Admin privilege flag (default False)
            is_active: Account active status (default True)
            last_login_at: Last login timestamp (optional)
            created_at: Creation timestamp (optional)
            updated_at: Update timestamp (optional)
        """
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.is_admin = is_admin
        self._is_active = is_active
        self.last_login_at = last_login_at
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def is_active(self) -> bool:
        """Flask-Login requires is_active property."""
        return self._is_active

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash.

        Args:
            password: Plain text password to check

        Returns:
            True if password matches, False otherwise
        """
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def create(username: str, email: str, password: str, is_admin: bool = False) -> 'User':
        """Create new user with hashed password.

        Uses pbkdf2:sha256:600000 for password hashing (NIST recommended).

        Args:
            username: Unique username
            email: Unique email address
            password: Plain text password
            is_admin: Admin privilege flag (default False)

        Returns:
            User instance with database ID

        Raises:
            Exception: If username or email already exists
        """
        import database_postgres as database

        # Hash password using PBKDF2 with 600,000 iterations (NIST recommendation)
        password_hash = generate_password_hash(
            password,
            method='pbkdf2:sha256:600000'
        )

        # Insert user into database
        user_id = database.insert_user(
            username=username,
            email=email,
            password_hash=password_hash,
            is_admin=is_admin
        )

        return User(
            id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            is_admin=is_admin,
            is_active=True
        )

    @staticmethod
    def get_by_id(user_id: int) -> Optional['User']:
        """Load user by ID.

        Args:
            user_id: User ID to load

        Returns:
            User instance or None if not found
        """
        import database_postgres as database

        user_data = database.get_user_by_id(user_id)
        if user_data:
            return User(**user_data)
        return None

    @staticmethod
    def get_by_username(username: str) -> Optional['User']:
        """Load user by username.

        Args:
            username: Username to look up

        Returns:
            User instance or None if not found
        """
        import database_postgres as database

        user_data = database.get_user_by_username(username)
        if user_data:
            return User(**user_data)
        return None

    @staticmethod
    def get_by_email(email: str) -> Optional['User']:
        """Load user by email.

        Args:
            email: Email address to look up

        Returns:
            User instance or None if not found
        """
        import database_postgres as database

        user_data = database.get_user_by_email(email)
        if user_data:
            return User(**user_data)
        return None

    def update_last_login(self) -> None:
        """Update last_login_at timestamp to now."""
        import database_postgres as database

        self.last_login_at = datetime.now()
        database.update_user_last_login(self.id, self.last_login_at)

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary (for JSON serialization).

        Note: password_hash is excluded for security.

        Returns:
            Dictionary with user data (no password hash)
        """
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<User {self.username} (id={self.id}, admin={self.is_admin})>"
