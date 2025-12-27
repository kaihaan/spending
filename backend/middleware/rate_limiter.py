"""
Redis-based rate limiting middleware

Implements sliding window rate limiting using Redis sorted sets.
CRITICAL: Prevents database self-DoS on authentication endpoints.

Fix #5 from deployment plan - NO database writes on login path.
"""

import os
from datetime import datetime

from redis import Redis

# Initialize Redis client
# Uses environment variable REDIS_URL or defaults to localhost
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=False)


def rate_limit_login(
    ip_address: str, max_attempts: int = 5, window_minutes: int = 15
) -> bool:
    """Redis sliding window rate limiter for login attempts.

    Uses Redis sorted sets to track login attempts per IP address.
    NO database writes - prevents self-DoS on authentication path.

    Algorithm:
    1. Remove attempts older than window (ZREMRANGEBYSCORE)
    2. Count remaining attempts (ZCARD)
    3. Add current attempt (ZADD)
    4. Set expiry on key (EXPIRE)

    Args:
        ip_address: Client IP address (from X-Forwarded-For or remote_addr)
        max_attempts: Maximum attempts allowed in window (default 5)
        window_minutes: Time window in minutes (default 15)

    Returns:
        True if request is allowed, False if rate limit exceeded

    Example:
        >>> if not rate_limit_login(request.remote_addr):
        >>>     return jsonify({'error': 'Too many attempts'}), 429
    """
    key = f"login_attempts:{ip_address}"
    now = datetime.now().timestamp()
    window_start = now - (window_minutes * 60)

    try:
        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()

        # Remove old attempts outside the window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count attempts in current window
        pipe.zcard(key)

        # Add current attempt
        pipe.zadd(key, {now: now})

        # Set expiry to window duration (cleanup)
        pipe.expire(key, window_minutes * 60)

        # Execute pipeline
        results = pipe.execute()

        # results[1] is the count BEFORE adding current attempt
        attempt_count = results[1]

        # Check if under limit
        return attempt_count < max_attempts

    except Exception as e:
        # On Redis failure, allow the request (fail open)
        # Log the error but don't block legitimate users
        print(f"[Rate Limiter] Redis error: {e}")
        return True


def rate_limit_api(
    identifier: str, max_requests: int = 100, window_seconds: int = 60
) -> bool:
    """General API rate limiter (per-user or per-IP).

    Uses Redis sliding window for general API endpoint protection.

    Args:
        identifier: User ID or IP address
        max_requests: Maximum requests allowed in window (default 100)
        window_seconds: Time window in seconds (default 60)

    Returns:
        True if request is allowed, False if rate limit exceeded

    Example:
        >>> if not rate_limit_api(f"user:{current_user.id}"):
        >>>     return jsonify({'error': 'Rate limit exceeded'}), 429
    """
    key = f"api_requests:{identifier}"
    now = datetime.now().timestamp()
    window_start = now - window_seconds

    try:
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {now: now})
        pipe.expire(key, window_seconds)

        results = pipe.execute()
        request_count = results[1]

        return request_count < max_requests

    except Exception as e:
        print(f"[Rate Limiter] Redis error: {e}")
        return True  # Fail open


def get_rate_limit_status(ip_address: str, window_minutes: int = 15) -> dict:
    """Get current rate limit status for an IP address.

    Args:
        ip_address: Client IP address
        window_minutes: Time window in minutes (default 15)

    Returns:
        Dictionary with rate limit status:
        {
            'attempts': int,
            'remaining': int,
            'reset_at': float (timestamp)
        }
    """
    key = f"login_attempts:{ip_address}"
    now = datetime.now().timestamp()
    window_start = now - (window_minutes * 60)

    try:
        # Clean old attempts
        redis_client.zremrangebyscore(key, 0, window_start)

        # Get current attempts
        attempts = redis_client.zcard(key)

        # Get oldest attempt for reset calculation
        oldest = redis_client.zrange(key, 0, 0, withscores=True)
        reset_at = oldest[0][1] + (window_minutes * 60) if oldest else now

        return {
            "attempts": attempts,
            "remaining": max(0, 5 - attempts),
            "reset_at": reset_at,
        }

    except Exception as e:
        print(f"[Rate Limiter] Redis error: {e}")
        return {"attempts": 0, "remaining": 5, "reset_at": now + (window_minutes * 60)}


def clear_rate_limit(ip_address: str) -> bool:
    """Clear rate limit for an IP address (e.g., after successful login).

    Args:
        ip_address: Client IP address

    Returns:
        True if cleared successfully
    """
    key = f"login_attempts:{ip_address}"
    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        print(f"[Rate Limiter] Redis error: {e}")
        return False


def block_ip(ip_address: str, duration_hours: int = 24) -> bool:
    """Permanently block an IP address for specified duration.

    Args:
        ip_address: Client IP address
        duration_hours: Block duration in hours (default 24)

    Returns:
        True if blocked successfully
    """
    key = f"blocked_ip:{ip_address}"
    try:
        redis_client.setex(key, duration_hours * 3600, datetime.now().isoformat())
        return True
    except Exception as e:
        print(f"[Rate Limiter] Redis error: {e}")
        return False


def is_ip_blocked(ip_address: str) -> bool:
    """Check if an IP address is blocked.

    Args:
        ip_address: Client IP address

    Returns:
        True if IP is blocked
    """
    key = f"blocked_ip:{ip_address}"
    try:
        return redis_client.exists(key) > 0
    except Exception as e:
        print(f"[Rate Limiter] Redis error: {e}")
        return False  # Fail open
