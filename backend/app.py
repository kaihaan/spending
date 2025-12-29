import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

import database

# Load .env from project root (parent directory)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS configuration - must support credentials for session-based auth
CORS(
    app,
    origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    supports_credentials=True,
)

# ============================================================================
# SECURITY CONFIGURATION (GCP Deployment)
# ============================================================================

# Flask secret key (use Secret Manager in production)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", os.urandom(32).hex())

# Cookie security settings (Fix #7 - SameSite=Strict)
# NOTE: __Host- prefix requires HTTPS; use regular name in development
is_production = os.getenv("FLASK_ENV") == "production"
app.config.update(
    SESSION_COOKIE_SECURE=is_production,  # HTTPS only in production
    SESSION_COOKIE_HTTPONLY=True,  # No JavaScript access
    SESSION_COOKIE_SAMESITE="Strict",  # Fix #7: Strict (not Lax)
    SESSION_COOKIE_NAME="__Host-session" if is_production else "session",
    PERMANENT_SESSION_LIFETIME=3600,  # 1 hour
    SESSION_COOKIE_DOMAIN=None,  # Current domain only
)

# Allow larger request bodies for CSV file uploads (16MB)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# Get frontend URL from environment, default to localhost:5173
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# ============================================================================
# FLASK-LOGIN INITIALIZATION
# ============================================================================

from auth import init_app as init_auth

init_auth(app)

# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

from middleware.security_headers import init_app as init_security_headers

init_security_headers(app)

# ============================================================================
# REGISTER BLUEPRINTS
# ============================================================================

from routes.amazon import amazon_bp, amazon_business_bp
from routes.apple import apple_bp
from routes.auth import auth_bp
from routes.categories import categories_v1_bp, categories_v2_bp, subcategories_v2_bp
from routes.direct_debit import direct_debit_bp
from routes.enrichment import enrichment_bp
from routes.gmail import gmail_bp
from routes.health import health_bp
from routes.huququllah import huququllah_bp
from routes.matching import matching_bp
from routes.migrations import migrations_bp
from routes.rules import rules_bp
from routes.settings import settings_bp
from routes.transactions import transactions_bp
from routes.truelayer import truelayer_bp
from routes.utilities import utilities_bp

# Register all blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(health_bp)
app.register_blueprint(gmail_bp)
app.register_blueprint(truelayer_bp)
app.register_blueprint(amazon_bp)
app.register_blueprint(amazon_business_bp)
app.register_blueprint(enrichment_bp)
app.register_blueprint(rules_bp)
app.register_blueprint(apple_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(categories_v1_bp)
app.register_blueprint(categories_v2_bp)
app.register_blueprint(subcategories_v2_bp)
app.register_blueprint(huququllah_bp)
app.register_blueprint(direct_debit_bp)
app.register_blueprint(matching_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(migrations_bp)
app.register_blueprint(utilities_bp)

# ============================================================================
# AUTHENTICATION ENFORCEMENT (Global Route Protection)
# ============================================================================

from flask import request as flask_request
from flask_login import current_user

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = {
    # Health check
    "/api/health",
    # Authentication routes
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/check",
    # Static files (if any)
    "/static",
}


@app.before_request
def require_authentication():
    """Enforce authentication on all routes except public endpoints.

    This global check ensures that:
    1. All routes are protected by default (security by default)
    2. New routes don't need @login_required decorator
    3. Public routes are explicitly listed (easy to audit)

    Returns:
        - None if authenticated or accessing public endpoint
        - 401 Unauthorized if not authenticated and accessing protected route
    """
    # Allow OPTIONS requests (CORS preflight)
    if flask_request.method == "OPTIONS":
        return None

    # Check if endpoint is public
    path = flask_request.path

    # Exact match or prefix match for public endpoints
    is_public = any(
        path == endpoint or path.startswith(endpoint + "/")
        for endpoint in PUBLIC_ENDPOINTS
    )

    if is_public:
        return None

    # Require authentication for all other routes
    if not current_user.is_authenticated:
        return {
            "error": "Authentication required",
            "message": "You must be logged in to access this endpoint",
        }, 401

    return None


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

if __name__ == "__main__":
    # Initialize database on startup (SQLite only)
    if hasattr(database, "init_db"):
        database.init_db()
    # Run migration to add huququllah column if needed (SQLite only)
    if hasattr(database, "migrate_add_huququllah_column"):
        database.migrate_add_huququllah_column()

    print("\n" + "=" * 50)
    print("🚀 Personal Finance Backend Starting...")
    print("=" * 50)
    print("📍 API available at: http://localhost:5000")
    print("💡 Test health: http://localhost:5000/api/health")
    print("=" * 50 + "\n")

    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000)
