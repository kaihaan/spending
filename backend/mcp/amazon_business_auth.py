"""
Amazon Business OAuth via Login with Amazon (LWA)

Handles OAuth 2.0 authentication flow for Amazon Business Reporting API.
Similar pattern to TrueLayer auth but with Amazon-specific endpoints.
"""

import os
import requests
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

# Login with Amazon endpoints
LWA_AUTH_URL = "https://www.amazon.com/ap/oa"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# Scopes required for Amazon Business Reporting API
SCOPES = ["profile", "amazon_business:orders:read"]


def get_client_credentials():
    """Get Amazon Business client credentials from environment.

    Returns:
        Tuple of (client_id, client_secret, redirect_uri)

    Raises:
        ValueError: If required credentials are missing
    """
    client_id = os.getenv('AMAZON_BUSINESS_CLIENT_ID')
    client_secret = os.getenv('AMAZON_BUSINESS_CLIENT_SECRET')
    redirect_uri = os.getenv(
        'AMAZON_BUSINESS_REDIRECT_URI',
        'http://localhost:5000/api/amazon-business/callback'
    )

    if not client_id or not client_secret:
        raise ValueError(
            "Amazon Business credentials not configured. "
            "Set AMAZON_BUSINESS_CLIENT_ID and AMAZON_BUSINESS_CLIENT_SECRET "
            "environment variables."
        )

    return client_id, client_secret, redirect_uri


def generate_state_token() -> str:
    """Generate a secure random state token for OAuth.

    Returns:
        Random 32-character hex string
    """
    return secrets.token_hex(16)


def get_authorization_url(state: str = None) -> dict:
    """Generate OAuth authorization URL for Login with Amazon.

    Args:
        state: Optional state token (generated if not provided)

    Returns:
        Dictionary with 'authorization_url' and 'state'
    """
    client_id, _, redirect_uri = get_client_credentials()

    if state is None:
        state = generate_state_token()

    params = {
        "client_id": client_id,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state
    }

    authorization_url = f"{LWA_AUTH_URL}?{urlencode(params)}"

    return {
        "authorization_url": authorization_url,
        "state": state
    }


def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for access and refresh tokens.

    Args:
        code: Authorization code from OAuth callback

    Returns:
        Dictionary with token response:
        {
            'access_token': str,
            'refresh_token': str,
            'expires_in': int,
            'token_type': str
        }

    Raises:
        Exception: If token exchange fails
    """
    client_id, client_secret, redirect_uri = get_client_credentials()

    response = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    if response.status_code != 200:
        error_data = response.json()
        raise Exception(
            f"Token exchange failed: {error_data.get('error_description', error_data)}"
        )

    return response.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh access token using refresh token.

    Args:
        refresh_token: Valid refresh token

    Returns:
        Dictionary with new token response:
        {
            'access_token': str,
            'refresh_token': str (may be same or new),
            'expires_in': int,
            'token_type': str
        }

    Raises:
        Exception: If token refresh fails
    """
    client_id, client_secret, _ = get_client_credentials()

    response = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    if response.status_code != 200:
        error_data = response.json()
        raise Exception(
            f"Token refresh failed: {error_data.get('error_description', error_data)}"
        )

    return response.json()


def is_token_expired(expires_at: datetime, buffer_minutes: int = 5) -> bool:
    """Check if token is expired or will expire soon.

    Args:
        expires_at: Token expiry datetime
        buffer_minutes: Minutes before expiry to consider token expired

    Returns:
        True if token is expired or will expire within buffer time
    """
    if expires_at is None:
        return True

    buffer = timedelta(minutes=buffer_minutes)
    return datetime.now() >= (expires_at - buffer)


def get_valid_access_token(connection: dict) -> str:
    """Get a valid access token, refreshing if necessary.

    Args:
        connection: Database connection record with token info

    Returns:
        Valid access token string

    Raises:
        Exception: If token refresh fails
    """
    import database_postgres as database

    if is_token_expired(connection['token_expires_at']):
        # Token expired, refresh it
        print("[Amazon Business] Access token expired, refreshing...")
        tokens = refresh_access_token(connection['refresh_token'])

        # Calculate new expiry
        expires_at = datetime.now() + timedelta(seconds=tokens['expires_in'])

        # Update tokens in database
        database.update_amazon_business_tokens(
            connection['id'],
            tokens['access_token'],
            tokens.get('refresh_token', connection['refresh_token']),
            expires_at
        )

        return tokens['access_token']

    return connection['access_token']
