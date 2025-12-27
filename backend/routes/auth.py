"""
Authentication routes (login, logout, registration)

Implements secure authentication with rate limiting and audit logging.
"""

from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user
from middleware.rate_limiter import clear_rate_limit, is_ip_blocked, rate_limit_login
from models.user import User

import database

# Create authentication blueprint
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def get_client_ip() -> str:
    """Extract client IP address from request.

    Handles X-Forwarded-For header from reverse proxies (Cloud Run).

    Returns:
        Client IP address
    """
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first (client)
        return x_forwarded_for.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate user and create session.

    Request Body:
        {
            "username": str,
            "password": str,
            "remember": bool (optional, default True)
        }

    Returns:
        Success:
            200: {
                "success": true,
                "user": {
                    "id": int,
                    "username": str,
                    "email": str,
                    "is_admin": bool
                }
            }
        Errors:
            400: Missing credentials
            401: Invalid credentials
            429: Rate limit exceeded
            403: IP blocked
    """
    # Get client IP and user agent
    ip_address = get_client_ip()
    user_agent = request.headers.get("User-Agent", "")

    # Check if IP is permanently blocked
    if is_ip_blocked(ip_address):
        database.log_security_event(
            user_id=None,
            event_type="login_blocked_ip",
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": "IP permanently blocked"},
        )
        return jsonify(
            {
                "error": "Access denied",
                "message": "Your IP address has been blocked due to suspicious activity",
            }
        ), 403

    # Rate limiting (Fix #5 - Redis-based, NO database writes)
    if not rate_limit_login(ip_address):
        # Log rate limit event (async Celery task would be better)
        database.log_security_event(
            user_id=None,
            event_type="rate_limit_exceeded",
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"endpoint": "/api/auth/login"},
        )

        return jsonify(
            {
                "error": "Too many attempts",
                "message": "Too many failed login attempts. Please try again in 15 minutes.",
            }
        ), 429

    # Parse request body
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    remember = data.get("remember", True)

    # Validate input
    if not username or not password:
        return jsonify(
            {
                "error": "Missing credentials",
                "message": "Username and password are required",
            }
        ), 400

    # Look up user by username
    user = User.get_by_username(username)

    if not user:
        # Log failed attempt (invalid username)
        database.log_security_event(
            user_id=None,
            event_type="login_failed",
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"username": username, "reason": "user_not_found"},
        )
        return jsonify(
            {"error": "Invalid credentials", "message": "Invalid username or password"}
        ), 401

    # Check password
    if not user.check_password(password):
        # Log failed attempt (invalid password)
        database.log_security_event(
            user_id=user.id,
            event_type="login_failed",
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": "invalid_password"},
        )
        return jsonify(
            {"error": "Invalid credentials", "message": "Invalid username or password"}
        ), 401

    # Check if account is active
    if not user.is_active:
        database.log_security_event(
            user_id=user.id,
            event_type="login_failed",
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": "account_inactive"},
        )
        return jsonify(
            {
                "error": "Account disabled",
                "message": "Your account has been disabled. Contact support.",
            }
        ), 401

    # Login successful - create session
    login_user(
        user,
        remember=remember,
        duration=timedelta(hours=1) if not remember else timedelta(days=7),
    )

    # Update last login timestamp
    user.update_last_login()

    # Clear rate limit for this IP (successful login)
    clear_rate_limit(ip_address)

    # Log successful login
    database.log_security_event(
        user_id=user.id,
        event_type="login_success",
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return jsonify({"success": True, "user": user.to_dict()}), 200


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Logout current user and destroy session.

    Returns:
        200: {"success": true}
    """
    # Log logout event
    ip_address = get_client_ip()
    user_agent = request.headers.get("User-Agent", "")

    database.log_security_event(
        user_id=current_user.id,
        event_type="logout",
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Destroy session
    logout_user()

    return jsonify({"success": True}), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_current_user():
    """Get current authenticated user information.

    Returns:
        200: User object (without password hash)
        401: Not authenticated
    """
    return jsonify(current_user.to_dict()), 200


@auth_bp.route("/check", methods=["GET"])
def check_auth():
    """Check if user is authenticated (for frontend).

    Returns:
        200: {
            "authenticated": bool,
            "user": {...} (if authenticated)
        }
    """
    if current_user.is_authenticated:
        return jsonify({"authenticated": True, "user": current_user.to_dict()}), 200
    return jsonify({"authenticated": False}), 200


# TODO: Add registration endpoint if needed
# @auth_bp.route('/register', methods=['POST'])
# def register():
#     """Register new user account."""
#     pass
