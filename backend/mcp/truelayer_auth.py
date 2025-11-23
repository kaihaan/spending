"""
TrueLayer OAuth 2.0 Authentication Module

Handles OAuth 2.0 authorization code flow for connecting to TrueLayer API.
Manages token storage, refresh, and encryption.
"""

import os
import secrets
import base64
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import database_init as database

# Load environment variables (override=True to prefer .env file over shell env)
load_dotenv(override=True)

# TrueLayer Configuration
TRUELAYER_CLIENT_ID = os.getenv('TRUELAYER_CLIENT_ID')
TRUELAYER_CLIENT_SECRET = os.getenv('TRUELAYER_CLIENT_SECRET')
TRUELAYER_REDIRECT_URI = os.getenv('TRUELAYER_REDIRECT_URI', 'http://localhost:5000/api/truelayer/callback')
TRUELAYER_ENV = os.getenv('TRUELAYER_ENVIRONMENT', 'sandbox')

# API URLs
if TRUELAYER_ENV == 'production':
    TRUELAYER_AUTH_URL = 'https://auth.truelayer.com/'
    TRUELAYER_TOKEN_URL = 'https://auth.truelayer.com/connect/token'
    TRUELAYER_API_URL = 'https://api.truelayer.com'
else:
    # Sandbox environment uses sandbox-specific domains
    TRUELAYER_AUTH_URL = 'https://auth.truelayer-sandbox.com/'
    TRUELAYER_TOKEN_URL = 'https://auth.truelayer-sandbox.com/connect/token'
    TRUELAYER_API_URL = 'https://api.sandbox.truelayer.com'

# Encryption key for storing tokens
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
cipher = Fernet(ENCRYPTION_KEY) if ENCRYPTION_KEY else None


def generate_state() -> str:
    """Generate a random state parameter for OAuth security."""
    return secrets.token_urlsafe(32)


def generate_pkce_challenge() -> tuple:
    """Generate PKCE code_verifier and code_challenge."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        __import__('hashlib').sha256(code_verifier.encode()).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


def get_authorization_url(user_id: int) -> dict:
    """
    Generate TrueLayer OAuth authorization URL.

    Returns:
        Dictionary with 'auth_url', 'state', and 'code_verifier'
    """
    state = generate_state()
    code_verifier, code_challenge = generate_pkce_challenge()

    # Store state and verifier in database for later validation
    # (In a production app, you'd store these temporarily in Redis or similar)
    # For now, we'll return them to the frontend

    params = {
        'client_id': TRUELAYER_CLIENT_ID,
        'redirect_uri': TRUELAYER_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'info accounts balance cards transactions direct_debits standing_orders offline_access',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'providers': 'uk-cs-mock uk-ob-all uk-oauth-all',
    }

    from urllib.parse import urlencode
    auth_url = f"{TRUELAYER_AUTH_URL}?{urlencode(params)}"

    return {
        'auth_url': auth_url,
        'state': state,
        'code_verifier': code_verifier
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
    data = {
        'grant_type': 'authorization_code',
        'client_id': TRUELAYER_CLIENT_ID,
        'client_secret': TRUELAYER_CLIENT_SECRET,
        'redirect_uri': TRUELAYER_REDIRECT_URI,
        'code': authorization_code,
        'code_verifier': code_verifier,
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        response = requests.post(TRUELAYER_TOKEN_URL, data=data, headers=headers, timeout=10)
        response.raise_for_status()

        token_data = response.json()

        # Calculate expiration time
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        return {
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token'),
            'expires_at': expires_at.isoformat(),
            'token_type': token_data.get('token_type', 'Bearer'),
            'scope': token_data.get('scope', 'accounts transactions balance'),
            'provider_id': 'truelayer',  # Default provider ID
        }
    except requests.RequestException as e:
        print(f"❌ Token exchange failed: {e}")
        raise


def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh an expired access token.

    Args:
        refresh_token: Refresh token from previous authentication

    Returns:
        Dictionary with new 'access_token', 'expires_at', etc.
    """
    data = {
        'grant_type': 'refresh_token',
        'client_id': TRUELAYER_CLIENT_ID,
        'client_secret': TRUELAYER_CLIENT_SECRET,
        'refresh_token': refresh_token,
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        response = requests.post(TRUELAYER_TOKEN_URL, data=data, headers=headers, timeout=10)
        response.raise_for_status()

        token_data = response.json()

        # Calculate expiration time
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        return {
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token', refresh_token),  # Use old if not provided
            'expires_at': expires_at.isoformat(),
            'token_type': token_data.get('token_type', 'Bearer'),
        }
    except requests.RequestException as e:
        print(f"❌ Token refresh failed: {e}")
        raise


def encrypt_token(token: str) -> str:
    """Encrypt sensitive token for storage."""
    if not cipher:
        print("⚠️  Warning: ENCRYPTION_KEY not set. Storing token unencrypted (NOT recommended for production)")
        return token
    return cipher.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored token."""
    if not cipher:
        return encrypted_token
    return cipher.decrypt(encrypted_token.encode()).decode()


def save_bank_connection(user_id: int, connection_data: dict) -> dict:
    """
    Save bank connection to database.

    Args:
        user_id: User ID
        connection_data: Dictionary with tokens and connection info

    Returns:
        Dictionary with connection_id and status
    """
    try:
        # Encrypt sensitive tokens
        encrypted_access = encrypt_token(connection_data['access_token'])
        encrypted_refresh = encrypt_token(connection_data['refresh_token']) if connection_data.get('refresh_token') else None

        # Insert into database
        connection_id = database.save_bank_connection(
            user_id=user_id,
            provider_id=connection_data.get('provider_id'),
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            expires_at=connection_data.get('expires_at')
        )

        return {
            'connection_id': connection_id,
            'status': 'connected',
            'provider_id': connection_data.get('provider_id'),
            'expires_at': connection_data.get('expires_at'),
        }
    except Exception as e:
        print(f"❌ Error saving connection: {e}")
        raise


def validate_authorization_state(state: str, stored_state: str) -> bool:
    """Validate OAuth state parameter to prevent CSRF attacks."""
    return secrets.compare_digest(state, stored_state)


def get_connection_status(connection_id: int) -> dict:
    """Get the current status of a bank connection."""
    # This would query the database for real implementation
    return {
        'connection_id': connection_id,
        'status': 'active',  # or 'expired', 'authorization_required'
        'last_synced_at': None,
    }


def discover_and_save_accounts(connection_id: int, access_token: str) -> dict:
    """
    Fetch accounts from TrueLayer API and save them to database.

    Args:
        connection_id: Database connection ID
        access_token: Valid access token for TrueLayer API

    Returns:
        Dictionary with discovered accounts count and details
    """
    try:
        from .truelayer_client import TrueLayerClient

        # Initialize client and fetch accounts
        client = TrueLayerClient(access_token)
        accounts = client.get_accounts()

        # Save each account to database
        saved_accounts = []
        for account in accounts:
            account_id = account.get('account_id')
            display_name = account.get('display_name', 'Unknown Account')
            account_type = account.get('account_type', 'TRANSACTION')
            currency = account.get('currency', 'GBP')

            # Save to database
            db_account_id = database.save_connection_account(
                connection_id=connection_id,
                account_id=account_id,
                display_name=display_name,
                account_type=account_type,
                currency=currency
            )

            saved_accounts.append({
                'account_id': account_id,
                'display_name': display_name,
                'account_type': account_type,
                'currency': currency,
                'db_id': db_account_id
            })

        return {
            'accounts_discovered': len(accounts),
            'accounts_saved': len(saved_accounts),
            'accounts': saved_accounts
        }
    except Exception as e:
        print(f"❌ Error discovering accounts: {e}")
        raise
