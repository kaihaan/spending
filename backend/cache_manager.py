"""
Redis Cache Manager for Personal Finance App
Provides caching utilities with graceful degradation.
Uses Redis DB 1 (DB 0 is reserved for Celery task queue).
"""

import json
import redis
import logging
import os
from functools import wraps
from typing import Any, Optional, Callable
from datetime import timedelta

logger = logging.getLogger(__name__)

# Redis connection singleton
_redis_client: Optional[redis.Redis] = None

# Default TTL (15 minutes = 900 seconds)
DEFAULT_TTL = 900


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get Redis client for caching (DB 1).
    Returns None if Redis is unavailable (graceful degradation).
    """
    global _redis_client

    if _redis_client is None:
        try:
            # Use environment variables for Docker compatibility
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', '6379'))

            _redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=1,  # Use DB 1 for caching (DB 0 is for Celery)
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            _redis_client.ping()
            logger.info("✓ Redis cache connected successfully (DB 1)")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis cache unavailable (graceful degradation): {e}")
            _redis_client = None

    return _redis_client


def cache_get(key: str) -> Optional[Any]:
    """
    Get cached value by key.
    Returns None if key not found or Redis unavailable.

    Args:
        key: Cache key

    Returns:
        Deserialized cached value or None
    """
    client = get_redis_client()
    if not client:
        return None

    try:
        value = client.get(key)
        if value:
            logger.debug(f"Cache HIT: {key}")
            return json.loads(value)
        else:
            logger.debug(f"Cache MISS: {key}")
            return None
    except (redis.RedisError, json.JSONDecodeError) as e:
        logger.warning(f"Cache read error for key '{key}': {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Set cached value with TTL.

    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time-to-live in seconds (default 900 = 15 minutes)

    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        return False

    try:
        serialized = json.dumps(value, default=str)  # default=str handles datetime
        client.setex(key, ttl, serialized)
        logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
        return True
    except (redis.RedisError, TypeError, ValueError) as e:
        logger.warning(f"Cache write error for key '{key}': {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete cached value.

    Args:
        key: Cache key to delete

    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        return False

    try:
        client.delete(key)
        logger.debug(f"Cache DELETE: {key}")
        return True
    except redis.RedisError as e:
        logger.warning(f"Cache delete error for key '{key}': {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern (e.g., "transactions:*").

    Args:
        pattern: Key pattern with wildcards

    Returns:
        Number of keys deleted
    """
    client = get_redis_client()
    if not client:
        return 0

    try:
        keys = client.keys(pattern)
        if keys:
            deleted = client.delete(*keys)
            logger.debug(f"Cache DELETE pattern '{pattern}': {deleted} keys")
            return deleted
        return 0
    except redis.RedisError as e:
        logger.warning(f"Cache pattern delete error for '{pattern}': {e}")
        return 0


def cache_invalidate_transactions():
    """Invalidate all transaction-related caches."""
    cache_delete_pattern("transactions:*")
    logger.info("Invalidated transaction caches")


def cache_invalidate_amazon():
    """Invalidate all Amazon-related caches."""
    cache_delete_pattern("amazon:*")
    logger.info("Invalidated Amazon caches")


def cache_invalidate_all():
    """Invalidate all caches."""
    client = get_redis_client()
    if client:
        try:
            client.flushdb()
            logger.info("Flushed all caches (DB 1)")
        except redis.RedisError as e:
            logger.warning(f"Cache flush error: {e}")


def cached(key_prefix: str, ttl: int = DEFAULT_TTL, key_func: Optional[Callable] = None):
    """
    Decorator to cache function results.

    Args:
        key_prefix: Prefix for cache key
        ttl: Time-to-live in seconds
        key_func: Optional function to generate cache key from args/kwargs

    Usage:
        @cached("transactions:all", ttl=900)
        def get_all_transactions():
            return expensive_query()

        @cached("user", ttl=600, key_func=lambda user_id: f"user:{user_id}")
        def get_user(user_id):
            return db.query(user_id)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: use prefix only (for parameter-less functions)
                cache_key = key_prefix

            # Try to get from cache
            cached_value = cache_get(cache_key)
            if cached_value is not None:
                return cached_value

            # Cache miss - compute value
            result = func(*args, **kwargs)

            # Store in cache
            cache_set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


def get_cache_stats() -> dict:
    """
    Get cache statistics.

    Returns:
        Dictionary with cache stats
    """
    client = get_redis_client()
    if not client:
        return {
            'available': False,
            'error': 'Redis not available'
        }

    try:
        info = client.info()
        return {
            'available': True,
            'used_memory': info.get('used_memory_human', 'N/A'),
            'total_keys': client.dbsize(),
            'hit_rate': info.get('keyspace_hits', 0) / max(1, info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0)),
            'uptime_seconds': info.get('uptime_in_seconds', 0)
        }
    except redis.RedisError as e:
        return {
            'available': False,
            'error': str(e)
        }
