"""
Gmail OAuth 2.0 Authentication Module

Handles OAuth 2.0 authorization code flow for connecting to Gmail API.
Manages token storage, refresh, and encryption.
Following patterns from truelayer_auth.py
"""

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import database_postgres as database
import redis
import requests
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load environment variables (Docker env vars take precedence)
load_dotenv(override=False)

# Redis client for distributed locking
_redis_client = None


def get_redis_client():
    """Get or create Redis client for token refresh locking."""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(redis_url)
    return _redis_client


# Gmail OAuth Configuration
GMAIL_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GMAIL_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:5000/api/gmail/callback"
)

# Google OAuth URLs (same for sandbox and production)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Gmail API scope - readonly access to inbox
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

# Encryption key for storing tokens (shared with TrueLayer)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
cipher = Fernet(ENCRYPTION_KEY) if ENCRYPTION_KEY else None

# Frontend URL for redirects
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def generate_state() -> str:
    """Generate a random state parameter for OAuth security (CSRF prevention)."""
    return secrets.token_urlsafe(32)


def generate_pkce_challenge() -> tuple:
    """
    Generate PKCE code_verifier and code_challenge.

    PKCE (Proof Key for Code Exchange) adds security for public clients
    by requiring a code_verifier to be sent with the token exchange.
    """
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    )
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    return code_verifier, code_challenge


def get_authorization_url(user_id: int) -> dict:
    """
    Generate Google OAuth authorization URL for Gmail access.

    Args:
        user_id: User ID for tracking the OAuth flow

    Returns:
        Dictionary with 'auth_url' (to redirect user to)
    """
    if not GMAIL_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured. Please set it in .env")

    state = generate_state()
    code_verifier, code_challenge = generate_pkce_challenge()

    # Store state and code_verifier in database for callback validation
    database.store_gmail_oauth_state(user_id, state, code_verifier)

    params = {
        "client_id": GMAIL_CLIENT_ID,
        "redirect_uri": GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",  # Request refresh token
        "prompt": "consent",  # Force consent screen for refresh token
    }

    from urllib.parse import urlencode

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    print(f"📧 Generated Gmail OAuth URL for user {user_id}")
    print(f"   Redirect URI: {GMAIL_REDIRECT_URI}")
    print(f"   Scope: {GMAIL_SCOPE}")
    print("   State stored in database for callback validation")

    return {
        "auth_url": auth_url,
    }


def exchange_code_for_token(authorization_code: str, code_verifier: str) -> dict:
    """
    Exchange authorization code for access token.

    Args:
        authorization_code: Code received from OAuth callback
        code_verifier: PKCE code verifier

    Returns:
        Dictionary with 'access_token', 'refresh_token', 'expires_at', etc.
    """
    if not GMAIL_CLIENT_ID or not GMAIL_CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured")

    data = {
        "grant_type": "authorization_code",
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "redirect_uri": GMAIL_REDIRECT_URI,
        "code": authorization_code,
        "code_verifier": code_verifier,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        print("📧 Exchanging authorization code for tokens...")
        response = requests.post(
            GOOGLE_TOKEN_URL, data=data, headers=headers, timeout=10
        )
        response.raise_for_status()

        token_data = response.json()

        # Calculate expiration time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        print("   ✅ Token exchange successful")
        print(f"   Expires in: {expires_in} seconds")
        print(
            f"   Refresh token received: {'Yes' if token_data.get('refresh_token') else 'No'}"
        )

        return {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at.isoformat(),
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope", GMAIL_SCOPE),
        }
    except requests.RequestException as e:
        print(f"❌ Gmail token exchange failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise


def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh an expired access token.

    Args:
        refresh_token: Refresh token from previous authentication

    Returns:
        Dictionary with new 'access_token', 'expires_at', etc.
    """
    if not GMAIL_CLIENT_ID or not GMAIL_CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured")

    data = {
        "grant_type": "refresh_token",
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        print("📧 Refreshing Gmail access token...")
        response = requests.post(
            GOOGLE_TOKEN_URL, data=data, headers=headers, timeout=10
        )
        response.raise_for_status()

        token_data = response.json()

        # Calculate expiration time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        print("   ✅ Token refresh successful")
        print(f"   New token expires in: {expires_in} seconds")

        return {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get(
                "refresh_token", refresh_token
            ),  # Use old if not provided
            "expires_at": expires_at.isoformat(),
            "token_type": token_data.get("token_type", "Bearer"),
        }
    except requests.RequestException as e:
        print(f"❌ Gmail token refresh failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise


def encrypt_token(token: str) -> str:
    """Encrypt sensitive token for storage."""
    if not cipher:
        print(
            "⚠️  Warning: ENCRYPTION_KEY not set. Storing token unencrypted (NOT recommended for production)"
        )
        return token
    return cipher.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored token."""
    if not cipher:
        print("⚠️  ENCRYPTION_KEY not set. Assuming token is stored in plain text.")
        return encrypted_token

    try:
        if isinstance(encrypted_token, bytes):
            decrypted = cipher.decrypt(encrypted_token).decode()
        else:
            decrypted = cipher.decrypt(encrypted_token.encode()).decode()
        return decrypted
    except Exception as e:
        print(f"❌ Gmail token decryption failed: {e}")
        raise


def save_gmail_connection(user_id: int, email_address: str, token_data: dict) -> dict:
    """
    Save Gmail connection to database.

    Args:
        user_id: User ID
        email_address: Connected Gmail address
        token_data: Dictionary with tokens and connection info

    Returns:
        Dictionary with connection_id and status
    """
    try:
        # Encrypt sensitive tokens
        encrypted_access = encrypt_token(token_data["access_token"])
        encrypted_refresh = (
            encrypt_token(token_data["refresh_token"])
            if token_data.get("refresh_token")
            else None
        )

        # Insert into database
        connection_id = database.save_gmail_connection(
            user_id=user_id,
            email_address=email_address,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expires_at=token_data.get("expires_at"),
            scopes=token_data.get("scope"),
        )

        print(
            f"   ✅ Gmail connection saved: id={connection_id}, email={email_address}"
        )

        return {
            "connection_id": connection_id,
            "status": "connected",
            "email_address": email_address,
            "expires_at": token_data.get("expires_at"),
        }
    except Exception as e:
        print(f"❌ Error saving Gmail connection: {e}")
        raise


def validate_authorization_state(state: str, stored_state: str) -> bool:
    """Validate OAuth state parameter to prevent CSRF attacks."""
    return secrets.compare_digest(state, stored_state)


def get_gmail_user_email(access_token: str) -> str:
    """
    Fetch the email address of the authenticated Gmail user.

    Args:
        access_token: Valid Gmail API access token

    Returns:
        Email address string
    """
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://www.googleapis.com/gmail/v1/users/me/profile",
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        profile = response.json()
        email = profile.get("emailAddress")
        print(f"   📧 Gmail user email: {email}")
        return email
    except requests.RequestException as e:
        print(f"❌ Failed to get Gmail user profile: {e}")
        raise


def handle_oauth_callback(request_args: dict):
    """
    Handle Gmail OAuth callback from Google.

    Args:
        request_args: Flask request.args containing callback parameters

    Returns:
        Flask redirect response to frontend with status
    """
    from flask import redirect

    try:
        code = request_args.get("code")
        state = request_args.get("state")
        error = request_args.get("error")

        # Check for OAuth errors
        if error:
            print(f"❌ Gmail OAuth error: {error}")
            return redirect(f"{FRONTEND_URL}/settings?gmail_error={error}")

        if not code or not state:
            print("❌ Gmail OAuth callback missing code or state")
            return redirect(
                f"{FRONTEND_URL}/settings?gmail_error=Missing+code+or+state"
            )

        print("📧 Gmail OAuth Callback:")
        print(f"   State: {state[:20]}...")
        print(f"   Code: {code[:20]}...")

        # Retrieve stored OAuth state from database
        oauth_state = database.get_gmail_oauth_state(state)
        if not oauth_state:
            print("❌ Invalid or expired OAuth state")
            return redirect(
                f"{FRONTEND_URL}/settings?gmail_error=Invalid+or+expired+state"
            )

        user_id = oauth_state.get("user_id")
        code_verifier = oauth_state.get("code_verifier")

        if not user_id or not code_verifier:
            print("❌ OAuth state missing user_id or code_verifier")
            return redirect(f"{FRONTEND_URL}/settings?gmail_error=Invalid+OAuth+state")

        print(f"   User ID: {user_id}")

        # Exchange authorization code for tokens
        token_data = exchange_code_for_token(code, code_verifier)
        print("   ✅ Tokens exchanged successfully")

        # Get user's Gmail email address
        email_address = get_gmail_user_email(token_data["access_token"])

        # Save connection to database
        connection_info = save_gmail_connection(user_id, email_address, token_data)
        print(f"   ✅ Connection saved: ID={connection_info.get('connection_id')}")

        # Clean up OAuth state
        database.delete_gmail_oauth_state(state)

        # Redirect to frontend with success
        connection_id = connection_info.get("connection_id")
        return redirect(
            f"{FRONTEND_URL}/settings?gmail_status=connected&connection_id={connection_id}&email={email_address}"
        )

    except Exception as e:
        print(f"❌ Gmail OAuth callback error: {e}")
        import traceback

        traceback.print_exc()
        # Sanitize error message for URL
        error_msg = str(e).split("\n")[0].replace(" ", "+")
        return redirect(f"{FRONTEND_URL}/settings?gmail_error={error_msg}")


def get_valid_access_token(connection_id: int) -> str:
    """
    Get a valid access token for a Gmail connection, refreshing if needed.

    Args:
        connection_id: Database ID of the Gmail connection

    Returns:
        Valid access token string
    """
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        raise ValueError(f"Gmail connection {connection_id} not found")

    # Decrypt tokens
    access_token = decrypt_token(connection["access_token"])
    refresh_token = (
        decrypt_token(connection["refresh_token"])
        if connection.get("refresh_token")
        else None
    )

    # Check if token is expired
    expires_at = connection.get("token_expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

        # Ensure expires_at is timezone-aware for comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        # Refresh if expiring within 5 minutes
        if expires_at <= datetime.now(UTC) + timedelta(minutes=5):
            if not refresh_token:
                raise ValueError("Access token expired and no refresh token available")

            print("   🔄 Access token expired, refreshing...")
            new_tokens = refresh_access_token(refresh_token)

            # Update database with new tokens
            database.update_gmail_tokens(
                connection_id=connection_id,
                access_token=encrypt_token(new_tokens["access_token"]),
                refresh_token=encrypt_token(
                    new_tokens.get("refresh_token", refresh_token)
                ),
                token_expires_at=new_tokens["expires_at"],
            )

            access_token = new_tokens["access_token"]

    return access_token


def get_gmail_credentials(connection_id: int) -> tuple:
    """
    Get valid access and refresh tokens for a Gmail connection.

    This is used by build_gmail_service() to create credentials that support
    automatic token refresh by the Google library.

    Args:
        connection_id: Database ID of the Gmail connection

    Returns:
        Tuple of (access_token, refresh_token)
    """
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        raise ValueError(f"Gmail connection {connection_id} not found")

    # Decrypt tokens
    access_token = decrypt_token(connection["access_token"])
    refresh_token = (
        decrypt_token(connection["refresh_token"])
        if connection.get("refresh_token")
        else None
    )

    # Check if token is expired
    expires_at = connection.get("token_expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

        # Ensure expires_at is timezone-aware for comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        # Refresh if expiring within 5 minutes
        if expires_at <= datetime.now(UTC) + timedelta(minutes=5):
            if not refresh_token:
                raise ValueError("Access token expired and no refresh token available")

            # Use distributed lock to prevent concurrent token refreshes
            lock_key = f"gmail_token_refresh:{connection_id}"
            redis_client = get_redis_client()
            lock = redis_client.lock(lock_key, timeout=30, blocking_timeout=35)

            try:
                if lock.acquire(blocking=True):
                    try:
                        # Re-check token expiry after acquiring lock (another worker may have refreshed)
                        connection_recheck = database.get_gmail_connection_by_id(
                            connection_id
                        )
                        expires_at_recheck = connection_recheck.get("token_expires_at")
                        if isinstance(expires_at_recheck, str):
                            expires_at_recheck = datetime.fromisoformat(
                                expires_at_recheck.replace("Z", "+00:00")
                            )
                        if expires_at_recheck.tzinfo is None:
                            expires_at_recheck = expires_at_recheck.replace(tzinfo=UTC)

                        # If token was refreshed by another worker, use the new token
                        if expires_at_recheck > datetime.now(UTC) + timedelta(
                            minutes=5
                        ):
                            print("   ✓ Token already refreshed by another worker")
                            access_token = decrypt_token(
                                connection_recheck["access_token"]
                            )
                            refresh_token = decrypt_token(
                                connection_recheck["refresh_token"]
                            )
                        else:
                            # Still expired, refresh it
                            print("   🔄 Access token expired, refreshing...")
                            new_tokens = refresh_access_token(refresh_token)

                            # Update database with new tokens
                            database.update_gmail_tokens(
                                connection_id=connection_id,
                                access_token=encrypt_token(new_tokens["access_token"]),
                                refresh_token=encrypt_token(
                                    new_tokens.get("refresh_token", refresh_token)
                                ),
                                token_expires_at=new_tokens["expires_at"],
                            )

                            access_token = new_tokens["access_token"]
                            refresh_token = new_tokens.get(
                                "refresh_token", refresh_token
                            )
                    finally:
                        lock.release()
                else:
                    raise Exception(
                        f"Failed to acquire token refresh lock for connection {connection_id}"
                    )
            except redis.exceptions.LockError as e:
                print(f"   ⚠️ Redis lock error during token refresh: {e}")
                # If lock fails, try to get latest token from database (may have been refreshed)
                connection_fallback = database.get_gmail_connection_by_id(connection_id)
                access_token = decrypt_token(connection_fallback["access_token"])
                refresh_token = decrypt_token(connection_fallback["refresh_token"])

    return access_token, refresh_token


def disconnect_gmail(connection_id: int, user_id: int) -> dict:
    """
    Disconnect Gmail account and delete all associated data.

    Args:
        connection_id: Database ID of the Gmail connection
        user_id: User ID for verification

    Returns:
        Dictionary with status
    """
    try:
        # Verify connection belongs to user
        connection = database.get_gmail_connection_by_id(connection_id)
        if not connection or connection.get("user_id") != user_id:
            raise ValueError("Connection not found or doesn't belong to user")

        # Try to revoke the token with Google (best effort)
        try:
            access_token = decrypt_token(connection["access_token"])
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access_token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
            print("   ✅ Revoked Gmail token with Google")
        except Exception as e:
            print(f"   ⚠️  Failed to revoke token with Google (continuing): {e}")

        # Delete connection and all associated data (CASCADE will delete receipts)
        database.delete_gmail_connection(connection_id)

        print(f"   ✅ Gmail connection {connection_id} disconnected and data deleted")

        return {"status": "disconnected", "connection_id": connection_id}
    except Exception as e:
        print(f"❌ Error disconnecting Gmail: {e}")
        raise
