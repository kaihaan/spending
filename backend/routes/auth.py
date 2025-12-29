"""
Authentication routes (login, logout, registration)

Implements secure authentication with rate limiting and audit logging.
"""

import os
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
    data = request.get_json(force=True, silent=True)
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

    # Look up user by username OR email
    user = User.get_by_username(username)
    if not user:
        # Try email lookup if username not found
        user = User.get_by_email(username)

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


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register new user account.

    Request Body:
        {
            "email": str (required),
            "password": str (required, min 8 characters),
            "username": str (optional)
        }

    Returns:
        Success:
            201: {
                "success": true,
                "user": {...},
                "message": "Account created successfully"
            }
        Errors:
            400: Missing/invalid fields
            409: Email already registered
    """
    from email_service import email_service

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    username = data.get("username", "").strip() or email.split("@")[0]

    # Validate input
    if not email or not password:
        return jsonify(
            {"error": "Missing fields", "message": "Email and password are required"}
        ), 400

    if len(password) < 8:
        return jsonify(
            {
                "error": "Invalid password",
                "message": "Password must be at least 8 characters",
            }
        ), 400

    # Check if email already exists
    existing_user = User.get_by_email(email)
    if existing_user:
        return jsonify(
            {
                "error": "Email already registered",
                "message": "An account with this email already exists",
            }
        ), 409

    try:
        # Create new user
        user = User.create(username=username, email=email, password=password)

        # Auto-login after registration
        login_user(user, remember=True, duration=timedelta(days=7))

        # Update last login timestamp
        user.update_last_login()

        # Log successful registration
        ip_address = get_client_ip()
        user_agent = request.headers.get("User-Agent", "")

        database.log_security_event(
            user_id=user.id,
            event_type="registration_success",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Send welcome email (non-blocking, failures are logged but don't block)
        email_service.send_welcome_email(email, username)

        return jsonify(
            {
                "success": True,
                "user": user.to_dict(),
                "message": "Account created successfully",
            }
        ), 201

    except Exception as e:
        return jsonify({"error": "Registration failed", "message": str(e)}), 500


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Request password reset email.

    Request Body:
        {
            "email": str
        }

    Returns:
        200: {
            "success": true,
            "message": "If email exists, reset link sent"
        }

    Note: Always returns success to prevent user enumeration.
    """
    from auth_tokens import generate_reset_token
    from email_service import email_service

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email required"}), 400

    # Look up user (but don't reveal if they exist)
    user = User.get_by_email(email)

    if user:
        # Generate reset token
        token = generate_reset_token(user.id)

        # Get frontend URL from environment
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        reset_url = f"{frontend_url}/reset-password"

        # Send email
        email_service.send_password_reset(email, token, reset_url)

        # Log password reset request
        ip_address = get_client_ip()
        user_agent = request.headers.get("User-Agent", "")

        database.log_security_event(
            user_id=user.id,
            event_type="password_reset_requested",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # Always return same response (prevent user enumeration)
    return jsonify(
        {
            "success": True,
            "message": "If an account exists with that email, a password reset link has been sent",
        }
    ), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """Reset password using token from email.

    Request Body:
        {
            "token": str (from email link),
            "password": str (new password, min 8 characters)
        }

    Returns:
        Success:
            200: {
                "success": true,
                "message": "Password reset successful"
            }
        Errors:
            400: Missing/invalid fields
            401: Invalid or expired token
    """
    from auth_tokens import consume_reset_token

    import database

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    token = data.get("token", "").strip()
    new_password = data.get("password", "")

    if not token or not new_password:
        return jsonify(
            {
                "error": "Missing fields",
                "message": "Token and new password are required",
            }
        ), 400

    if len(new_password) < 8:
        return jsonify(
            {
                "error": "Invalid password",
                "message": "Password must be at least 8 characters",
            }
        ), 400

    # Verify and consume token (single-use)
    user_id = consume_reset_token(token)

    if not user_id:
        return jsonify(
            {
                "error": "Invalid token",
                "message": "Password reset token is invalid or has expired",
            }
        ), 401

    # Update password
    from werkzeug.security import generate_password_hash

    password_hash = generate_password_hash(new_password, method="pbkdf2:sha256:600000")

    try:
        database.update_user_password(user_id, password_hash)

        # Log password reset success
        ip_address = get_client_ip()
        user_agent = request.headers.get("User-Agent", "")

        database.log_security_event(
            user_id=user_id,
            event_type="password_reset_completed",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return jsonify(
            {
                "success": True,
                "message": "Password reset successful. You can now log in with your new password.",
            }
        ), 200

    except Exception as e:
        return jsonify({"error": "Password reset failed", "message": str(e)}), 500


@auth_bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    """Get current user's profile information.

    Returns:
        200: {
            "id": int,
            "username": str,
            "email": str,
            "is_admin": bool,
            "created_at": str (ISO 8601),
            "last_login_at": str (ISO 8601)
        }
    """
    return jsonify(current_user.to_dict()), 200


@auth_bp.route("/profile", methods=["PUT"])
@login_required
def update_profile():
    """Update current user's profile.

    Request Body:
        {
            "username": str (optional),
            "current_password": str (required if changing password),
            "new_password": str (optional, min 8 characters)
        }

    Returns:
        Success:
            200: {
                "success": true,
                "user": {...},
                "message": "Profile updated successfully"
            }
        Errors:
            400: Invalid input
            401: Incorrect current password
    """
    import database

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    username = data.get("username", "").strip()
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    # Update username if provided
    if username and username != current_user.username:
        try:
            database.update_user_username(current_user.id, username)
            current_user.username = username
        except Exception as e:
            return jsonify(
                {"error": "Failed to update username", "message": str(e)}
            ), 500

    # Update password if provided
    if new_password:
        # Require current password for security
        if not current_password:
            return jsonify(
                {
                    "error": "Current password required",
                    "message": "You must provide your current password to change it",
                }
            ), 400

        # Verify current password
        if not current_user.check_password(current_password):
            # Log failed password change attempt
            ip_address = get_client_ip()
            user_agent = request.headers.get("User-Agent", "")

            database.log_security_event(
                user_id=current_user.id,
                event_type="password_change_failed",
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"reason": "incorrect_current_password"},
            )

            return jsonify(
                {
                    "error": "Incorrect password",
                    "message": "Current password is incorrect",
                }
            ), 401

        # Validate new password
        if len(new_password) < 8:
            return jsonify(
                {
                    "error": "Invalid password",
                    "message": "New password must be at least 8 characters",
                }
            ), 400

        # Update password
        from werkzeug.security import generate_password_hash

        password_hash = generate_password_hash(
            new_password, method="pbkdf2:sha256:600000"
        )

        try:
            database.update_user_password(current_user.id, password_hash)
            current_user.password_hash = password_hash

            # Log successful password change
            ip_address = get_client_ip()
            user_agent = request.headers.get("User-Agent", "")

            database.log_security_event(
                user_id=current_user.id,
                event_type="password_change_success",
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        except Exception as e:
            return jsonify(
                {"error": "Failed to update password", "message": str(e)}
            ), 500

    return jsonify(
        {
            "success": True,
            "user": current_user.to_dict(),
            "message": "Profile updated successfully",
        }
    ), 200
