"""
TrueLayer API Client

Wrapper for TrueLayer Data API endpoints.
Handles account information, transaction fetching, and balance queries.
"""

import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (override=True to prefer .env file over shell env)
load_dotenv(override=True)

TRUELAYER_ENV = os.getenv('TRUELAYER_ENVIRONMENT', 'sandbox')

# API URLs
if TRUELAYER_ENV == 'production':
    TRUELAYER_API_URL = 'https://api.truelayer.com'
else:
    TRUELAYER_API_URL = 'https://api.sandbox.truelayer.com'


class TrueLayerClient:
    """Client for TrueLayer Data API."""

    def __init__(self, access_token: str):
        """
        Initialize TrueLayer API client.

        Args:
            access_token: Valid OAuth access token
        """
        self.access_token = access_token
        self.base_url = TRUELAYER_API_URL
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make HTTP request to TrueLayer API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to requests

        Returns:
            JSON response from API
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"❌ API request failed: {method} {endpoint}")
            print(f"   Error: {e}")
            raise

    def get_me(self) -> Dict:
        """Get authenticated user information."""
        return self._make_request('GET', '/data/v1/me')

    def get_accounts(self) -> List[Dict]:
        """
        Get list of connected bank accounts.

        Returns:
            List of account dictionaries
        """
        response = self._make_request('GET', '/data/v1/accounts')
        return response.get('results', [])

    def get_account(self, account_id: str) -> Dict:
        """
        Get details for a specific account.

        Args:
            account_id: TrueLayer account ID

        Returns:
            Account details dictionary
        """
        return self._make_request('GET', f'/data/v1/accounts/{account_id}')

    def get_account_balance(self, account_id: str) -> Dict:
        """
        Get current balance for an account.

        Args:
            account_id: TrueLayer account ID

        Returns:
            Balance information
        """
        response = self._make_request('GET', f'/data/v1/accounts/{account_id}/balance')
        results = response.get('results', [])
        return results[0] if results else {}

    def get_transactions(
        self,
        account_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get transactions for an account.

        Args:
            account_id: TrueLayer account ID
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Maximum transactions to retrieve

        Returns:
            List of transaction dictionaries
        """
        params = {'limit': limit}

        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date

        response = self._make_request(
            'GET',
            f'/data/v1/accounts/{account_id}/transactions',
            params=params
        )
        return response.get('results', [])

    def get_pending_transactions(self, account_id: str) -> List[Dict]:
        """
        Get pending transactions for an account.

        Args:
            account_id: TrueLayer account ID

        Returns:
            List of pending transaction dictionaries
        """
        response = self._make_request(
            'GET',
            f'/data/v1/accounts/{account_id}/pending_transactions'
        )
        return response.get('results', [])

    def normalize_transaction(self, truelayer_txn: Dict) -> Dict:
        """
        Normalize TrueLayer transaction to app format.

        Args:
            truelayer_txn: Raw transaction from TrueLayer API

        Returns:
            Normalized transaction dictionary
        """
        return {
            'date': truelayer_txn.get('timestamp', '').split('T')[0],  # Extract date part
            'description': truelayer_txn.get('description', ''),
            'merchant_name': truelayer_txn.get('merchant_name'),
            'transaction_type': truelayer_txn.get('transaction_type'),  # DEBIT or CREDIT
            'amount': abs(float(truelayer_txn.get('amount', 0))),
            'currency': truelayer_txn.get('currency', 'GBP'),
            'transaction_code': truelayer_txn.get('transaction_code'),
            'transaction_id': truelayer_txn.get('transaction_id'),
            'normalised_provider_id': truelayer_txn.get('normalised_provider_transaction_id'),
            'category': truelayer_txn.get('transaction_category'),  # May be provided by TrueLayer
            'running_balance': truelayer_txn.get('running_balance'),
            'metadata': {
                'provider_id': truelayer_txn.get('provider_id'),
                'provider_transaction_id': truelayer_txn.get('provider_transaction_id'),
                'meta': truelayer_txn.get('meta', {}),
            }
        }

    def get_last_sync_date(self, account_id: str) -> Optional[str]:
        """
        Get the last sync date for an account to avoid re-fetching.

        For production use, this would query the database.
        For now, return None to fetch all transactions.
        """
        # TODO: Query database for last_synced_at for this account
        return None

    def fetch_all_transactions(self, account_id: str, days_back: int = 90) -> List[Dict]:
        """
        Fetch all transactions for an account from the past N days.

        Args:
            account_id: TrueLayer account ID
            days_back: Number of days to fetch (default: 90)

        Returns:
            List of normalized transactions
        """
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        to_date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            raw_transactions = self.get_transactions(account_id, from_date, to_date)
            normalized = [self.normalize_transaction(txn) for txn in raw_transactions]
            print(f"✅ Fetched {len(normalized)} transactions for account {account_id}")
            return normalized
        except Exception as e:
            print(f"❌ Error fetching transactions: {e}")
            return []
