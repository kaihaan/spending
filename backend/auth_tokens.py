"""
Password reset token management using Redis.

Implements secure, time-limited password reset tokens with single-use validation.
"""

import os
import secrets

from redis import Redis

# Initialize Redis client (reuse same connection settings as rate limiter)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

# Token expiry duration (1 hour in seconds)
TOKEN_EXPIRY_SECONDS = 3600


def generate_reset_token(user_id: int) -> str:
    """Generate a password reset token and store in Redis with 1-hour expiry.

    Args:
        user_id: User ID to associate with the token

    Returns:
        URL-safe reset token (32 bytes = 43 characters base64)

    Example:
        >>> token = generate_reset_token(user_id=1)
        >>> # token: "abc123def456..." (43 chars)
        >>> # Stored in Redis: password_reset:abc123def456... = 1 (expires in 1h)
    """
    # Generate cryptographically secure random token
    token = secrets.token_urlsafe(32)

    # Store token -> user_id mapping in Redis with expiry
    key = f"password_reset:{token}"
    redis_client.setex(key, TOKEN_EXPIRY_SECONDS, user_id)

    return token


def verify_reset_token(token: str) -> int | None:
    """Verify password reset token and return associated user_id.

    Does NOT consume the token - allows checking validity before committing.

    Args:
        token: Reset token to verify

    Returns:
        User ID if token is valid, None if expired or invalid

    Example:
        >>> user_id = verify_reset_token("abc123...")
        >>> if user_id:
        >>>     print(f"Token valid for user {user_id}")
    """
    key = f"password_reset:{token}"

    try:
        user_id = redis_client.get(key)
        if user_id:
            return int(user_id)
        return None
    except (ValueError, TypeError):
        return None


def consume_reset_token(token: str) -> int | None:
    """Verify and consume (delete) password reset token.

    Single-use validation: Token is deleted after successful verification.
    This prevents token reuse attacks.

    Args:
        token: Reset token to verify and consume

    Returns:
        User ID if token is valid, None if expired/invalid/already used

    Example:
        >>> user_id = consume_reset_token("abc123...")
        >>> if user_id:
        >>>     # Token is valid and now deleted
        >>>     update_password(user_id, new_password)
        >>> else:
        >>>     # Token is invalid, expired, or already used
        >>>     return error_response("Invalid token")
    """
    key = f"password_reset:{token}"

    try:
        # Use GETDEL (atomic get + delete) if available (Redis 6.2+)
        # Falls back to GET + DEL for older Redis versions
        user_id_str = redis_client.getdel(key)

        if user_id_str:
            return int(user_id_str)

        # Fallback: Try GET + DEL separately
        user_id_str = redis_client.get(key)
        if user_id_str:
            redis_client.delete(key)
            return int(user_id_str)

        return None
    except (ValueError, TypeError):
        return None


def revoke_reset_token(token: str) -> bool:
    """Revoke (delete) a password reset token before it expires.

    Useful for canceling password reset requests.

    Args:
        token: Reset token to revoke

    Returns:
        True if token was revoked, False if token didn't exist

    Example:
        >>> revoke_reset_token("abc123...")
    """
    key = f"password_reset:{token}"
    return redis_client.delete(key) > 0
