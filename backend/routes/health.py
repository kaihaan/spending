"""
Minimal health check endpoint for Cloud Run

Fix #9: Minimal response with no verbose error messages or internal state exposed.
Different responses for Cloud Run health probes vs authenticated admin users.
"""

from datetime import datetime

import database_postgres as database
from flask import Blueprint, jsonify, request
from flask_login import current_user

# Create health blueprint
health_bp = Blueprint("health", __name__, url_prefix="/api")


def check_db_connection() -> bool:
    """Test database connectivity.

    Returns:
        True if database is accessible
    """
    try:
        with database.get_db() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
    except Exception:
        return False


def check_redis_connection() -> bool:
    """Test Redis connectivity.

    Returns:
        True if Redis is accessible
    """
    try:
        from backend.middleware.rate_limiter import redis_client

        return redis_client.ping()
    except Exception:
        return False


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Minimal health check endpoint.

    Fix #9: No verbose error messages or internal state exposed.

    Three response levels:
    1. Cloud Run health probes: Minimal {"status": "ok"}
    2. Unauthenticated requests: Minimal {"status": "ok"}
    3. Authenticated admin requests: Detailed health checks

    Returns:
        200: Service is healthy
        503: Service is unhealthy (admin view only)
    """
    # Check if request is from Cloud Run health probe
    user_agent = request.headers.get("User-Agent", "")
    if user_agent.startswith("GoogleHC"):
        # Minimal response for Cloud Run
        return jsonify({"status": "ok"}), 200

    # Check if user is authenticated admin
    if not current_user.is_authenticated or not current_user.is_admin:
        # Minimal response for non-admin users
        return jsonify({"status": "ok"}), 200

    # Detailed health check for admin users only
    health = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "checks": {
            "database": check_db_connection(),
            "redis": check_redis_connection(),
        },
    }

    # Overall status: healthy only if all checks pass
    all_healthy = all(health["checks"].values())
    health["status"] = "ok" if all_healthy else "degraded"

    status_code = 200 if all_healthy else 503

    return jsonify(health), status_code


@health_bp.route("/ping", methods=["GET"])
def ping():
    """Ultra-minimal ping endpoint for basic uptime checks.

    Returns:
        200: {"pong": true}
    """
    return jsonify({"pong": True}), 200
