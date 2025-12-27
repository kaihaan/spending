"""
Amazon Business API OAuth Authentication

Handles OAuth 2.0 authentication flow for Amazon Business API using Login with Amazon (LWA).
CRITICAL: Amazon Business API uses different OAuth flow than SP-API:
- Different authorization URL (buyer portal, not SellerCentral)
- Uses 'applicationId' parameter
- Regional domains (amazon.co.uk for UK)

Documentation: https://developer-docs.amazon.com/amazon-business/docs/website-authorization-workflow
"""

import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet

# Login with Amazon (LWA) endpoints for Amazon Business API
# Regional OAuth URLs by region
AMAZON_BUSINESS_OAUTH_URLS = {
    "UK": "https://www.amazon.co.uk/b2b/abws/oauth",
    "DE": "https://www.amazon.de/b2b/abws/oauth",
    "FR": "https://www.amazon.fr/b2b/abws/oauth",
    "ES": "https://www.amazon.es/b2b/abws/oauth",
    "IT": "https://www.amazon.it/b2b/abws/oauth",
    "US": "https://www.amazon.com/b2b/abws/oauth",
    "CA": "https://www.amazon.ca/b2b/abws/oauth",
    "MX": "https://www.amazon.com.mx/b2b/abws/oauth",
    "JP": "https://www.amazon.co.jp/b2b/abws/oauth",
    "AU": "https://www.amazon.com.au/b2b/abws/oauth",
}

# Token exchange endpoint (same for all regions)
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# Encryption for token storage
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
cipher = Fernet(ENCRYPTION_KEY.encode()) if ENCRYPTION_KEY else None


def get_client_credentials():
    """Get Amazon Business API client credentials from environment.

    Returns:
        Tuple of (client_id, client_secret, redirect_uri)

    Raises:
        ValueError: If required credentials are missing
    """
    client_id = os.getenv("AMAZON_BUSINESS_CLIENT_ID")
    client_secret = os.getenv("AMAZON_BUSINESS_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "AMAZON_BUSINESS_REDIRECT_URI",
        "http://localhost:5000/api/amazon-business/callback",
    )

    if not client_id or not client_secret:
        raise ValueError(
            "Amazon Business API credentials not configured. "
            "Set AMAZON_BUSINESS_CLIENT_ID and AMAZON_BUSINESS_CLIENT_SECRET "
            "environment variables."
        )

    return client_id, client_secret, redirect_uri


def generate_state_token() -> str:
    """Generate a secure random state token for OAuth CSRF protection.

    Returns:
        Random 32-character hex string
    """
    return secrets.token_hex(16)


def get_authorization_url(state: str = None, region: str = "UK") -> dict:
    """Generate OAuth authorization URL for Amazon Business API.

    CRITICAL: Amazon Business API uses different parameters than SP-API:
    - Uses 'applicationId' instead of 'application_id'
    - Regional buyer portal URLs (not SellerCentral)
    - NO 'version' parameter

    Args:
        state: Optional state token (generated if not provided)
        region: Region code for marketplace (default 'UK')

    Returns:
        Dictionary with 'authorization_url' and 'state'
    """
    client_id, _, redirect_uri = get_client_credentials()

    if state is None:
        state = generate_state_token()

    # Get regional OAuth URL
    oauth_base_url = AMAZON_BUSINESS_OAUTH_URLS.get(
        region, AMAZON_BUSINESS_OAUTH_URLS["UK"]
    )

    # Amazon Business API specific parameters
    params = {
        "applicationId": client_id,  # Note: 'applicationId', not 'application_id'
        "state": state,
        "redirect_uri": redirect_uri,
        # Note: NO 'version' parameter (unlike SP-API)
    }

    authorization_url = f"{oauth_base_url}?{urlencode(params)}"

    return {"authorization_url": authorization_url, "state": state}


def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for access and refresh tokens.

    This uses the standard LWA token endpoint (same as other Amazon services).

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
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        error_data = response.json()
        error_msg = error_data.get(
            "error_description", error_data.get("error", "Unknown error")
        )
        raise Exception(f"Amazon Business API token exchange failed: {error_msg}")

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
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        error_data = response.json()
        error_msg = error_data.get(
            "error_description", error_data.get("error", "Unknown error")
        )
        raise Exception(f"Amazon Business API token refresh failed: {error_msg}")

    return response.json()


def encrypt_token(token: str) -> str:
    """Encrypt token for secure storage.

    Args:
        token: Plain text token

    Returns:
        Encrypted token (base64 encoded)
    """
    if not cipher:
        return token  # Fallback if encryption not configured
    return cipher.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored token.

    Args:
        encrypted_token: Encrypted token from database

    Returns:
        Plain text token
    """
    if not cipher:
        return encrypted_token  # Fallback if encryption not configured
    return cipher.decrypt(encrypted_token.encode()).decode()


def is_token_expired(expires_at: datetime, buffer_minutes: int = 5) -> bool:
    """Check if token is expired or will expire soon.

    Args:
        expires_at: Token expiry datetime
        buffer_minutes: Minutes before expiry to consider token expired (default 5)

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
        Valid access token string (decrypted)

    Raises:
        Exception: If token refresh fails
    """
    import database_postgres as database

    # Decrypt stored token
    access_token = decrypt_token(connection["access_token"])

    # Check if token needs refresh
    if is_token_expired(connection["token_expires_at"]):
        print("[Amazon Business API] Access token expired, refreshing...")

        # Decrypt refresh token
        refresh_token = decrypt_token(connection["refresh_token"])

        # Get new tokens
        tokens = refresh_access_token(refresh_token)

        # Calculate new expiry
        expires_at = datetime.now() + timedelta(seconds=tokens["expires_in"])

        # Encrypt new tokens
        new_access_token = encrypt_token(tokens["access_token"])
        new_refresh_token = encrypt_token(tokens.get("refresh_token", refresh_token))

        # Update tokens in database
        database.update_amazon_business_tokens(
            connection["id"], new_access_token, new_refresh_token, expires_at
        )

        return tokens["access_token"]

    return access_token
