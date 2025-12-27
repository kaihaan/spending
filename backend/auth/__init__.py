"""
Flask-Login authentication configuration

Configures session management, user loading, and authentication boundaries.
"""

from flask_login import LoginManager, login_required, current_user
from models.user import User


# Initialize Flask-Login manager
login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # Redirect to login page if not authenticated
login_manager.session_protection = 'strong'  # Protect against session hijacking
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for session management.

    Called by Flask-Login to load the user object from the session.
    This is called on every request that requires authentication.

    Args:
        user_id: User ID stored in session (as string)

    Returns:
        User object or None if user not found/inactive
    """
    try:
        user_id_int = int(user_id)
        return User.get_by_id(user_id_int)
    except (ValueError, TypeError):
        return None


@login_manager.unauthorized_handler
def unauthorized():
    """Handle unauthorized access attempts.

    Called when a user tries to access a @login_required route without auth.

    Returns:
        JSON error response with 401 status
    """
    from flask import jsonify
    return jsonify({
        'error': 'Authentication required',
        'message': 'Please log in to access this resource'
    }), 401


def init_app(app):
    """Initialize Flask-Login with Flask app.

    Args:
        app: Flask application instance
    """
    login_manager.init_app(app)


# Export commonly used decorators and objects
__all__ = [
    'login_manager',
    'login_required',
    'current_user',
    'init_app'
]
