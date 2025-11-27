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
            print(f"   🌐 Request: {method} {url}")
            print(f"   🌐 Headers: Authorization=Bearer {self.access_token[:20]}...")
            if 'params' in kwargs:
                print(f"   🌐 Query params: {kwargs['params']}")

            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            json_response = response.json()
            print(f"   🌐 Status: {response.status_code}")
            print(f"   🌐 Response size: {len(str(json_response))} bytes")

            # Log response structure for debugging
            if isinstance(json_response, dict):
                print(f"   🌐 Response keys: {list(json_response.keys())}")
                # Log the structure of top-level response
                for key in list(json_response.keys())[:5]:  # First 5 keys
                    val = json_response[key]
                    if isinstance(val, list):
                        print(f"   🌐   - '{key}': list with {len(val)} items")
                        if val and isinstance(val[0], dict):
                            print(f"   🌐     First item keys: {list(val[0].keys())}")
                    elif isinstance(val, dict):
                        print(f"   🌐   - '{key}': dict with keys {list(val.keys())}")
                    else:
                        print(f"   🌐   - '{key}': {type(val).__name__}")
            elif isinstance(json_response, list):
                print(f"   🌐 Response is direct array with {len(json_response)} items")
                if json_response and isinstance(json_response[0], dict):
                    print(f"   🌐 First item keys: {list(json_response[0].keys())}")

            return json_response
        except requests.RequestException as e:
            print(f"❌ API request failed: {method} {endpoint}")
            print(f"   Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Status code: {e.response.status_code}")
                try:
                    print(f"   Response: {e.response.text}")
                except:
                    pass
            raise

    def get_me(self) -> Dict:
        """Get authenticated user information."""
        return self._make_request('GET', '/data/v1/info')

    def get_accounts(self) -> List[Dict]:
        """
        Get list of connected bank accounts.

        Returns:
            List of account dictionaries
        """
        print(f"   📡 Calling TrueLayer API: GET /data/v1/accounts")
        response = self._make_request('GET', '/data/v1/accounts')
        accounts = response.get('results', [])
        print(f"   📡 API response: {len(accounts)} accounts in 'results' field")
        if response.get('status') or response.get('error'):
            print(f"   ⚠️  Response has status/error: {response.get('status')} / {response.get('error')}")
        print(f"   📡 Full response keys: {list(response.keys())}")
        return accounts

    def get_cards(self) -> List[Dict]:
        """
        Get list of connected credit/debit cards.

        Returns:
            List of card dictionaries
        """
        response = self._make_request('GET', '/data/v1/cards')
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

        # Handle multiple possible response structures
        # Try different keys that TrueLayer API might use
        transactions = None

        if isinstance(response, list):
            # If response is a direct array
            print(f"   ✅ Transaction response is direct array with {len(response)} items")
            transactions = response
        elif isinstance(response, dict):
            # Try common key names for transaction list
            for key in ['results', 'data', 'transactions', 'items']:
                if key in response:
                    transactions = response.get(key, [])
                    print(f"   ✅ Found transactions in '{key}' key: {len(transactions)} items")
                    break

        if transactions is None:
            print(f"⚠️  Could not find transactions in response. Response keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
            print(f"⚠️  Response type: {type(response).__name__}")
            transactions = []

        return transactions

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
            f'/data/v1/accounts/{account_id}/transactions/pending'
        )
        return response.get('results', [])

    def get_card(self, card_id: str) -> Dict:
        """
        Get details for a specific card.

        Args:
            card_id: TrueLayer card ID

        Returns:
            Card details dictionary
        """
        return self._make_request('GET', f'/data/v1/cards/{card_id}')

    def get_card_balance(self, card_id: str) -> Dict:
        """
        Get current balance for a card.

        Args:
            card_id: TrueLayer card ID

        Returns:
            Balance information
        """
        response = self._make_request('GET', f'/data/v1/cards/{card_id}/balance')
        results = response.get('results', [])
        return results[0] if results else {}

    def get_card_transactions(
        self,
        card_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get transactions for a card.

        Args:
            card_id: TrueLayer card ID
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
            f'/data/v1/cards/{card_id}/transactions',
            params=params
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
        # Extract running balance amount if it's a dict, otherwise use as-is
        running_balance = truelayer_txn.get('running_balance')
        if isinstance(running_balance, dict):
            running_balance = running_balance.get('amount')

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
            'running_balance': running_balance,
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

    def normalize_card_transaction(self, truelayer_txn: Dict) -> Dict:
        """
        Normalize TrueLayer card transaction to app format.
        Uses the same structure as account transactions for consistency.

        Args:
            truelayer_txn: Raw transaction from TrueLayer API

        Returns:
            Normalized card transaction dictionary
        """
        # Extract running balance amount if it's a dict, otherwise use as-is
        running_balance = truelayer_txn.get('running_balance')
        if isinstance(running_balance, dict):
            running_balance = running_balance.get('amount')

        return {
            'date': truelayer_txn.get('timestamp', '').split('T')[0],
            'description': truelayer_txn.get('description', ''),
            'merchant_name': truelayer_txn.get('merchant_name'),
            'transaction_type': truelayer_txn.get('transaction_type'),
            'amount': abs(float(truelayer_txn.get('amount', 0))),
            'currency': truelayer_txn.get('currency', 'GBP'),
            'transaction_code': truelayer_txn.get('transaction_code'),
            'transaction_id': truelayer_txn.get('transaction_id'),
            'normalised_provider_id': truelayer_txn.get('normalised_provider_transaction_id'),
            'category': truelayer_txn.get('transaction_category'),
            'running_balance': running_balance,
            'metadata': {
                'provider_id': truelayer_txn.get('provider_id'),
                'provider_transaction_id': truelayer_txn.get('provider_transaction_id'),
                'meta': truelayer_txn.get('meta', {}),
            }
        }

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

        print(f"   📅 Date range: {from_date} to {to_date} ({days_back} days)")

        try:
            print(f"   🔍 Fetching raw transactions from TrueLayer API...")
            raw_transactions = self.get_transactions(account_id, from_date, to_date)
            print(f"   📦 Raw transactions received: {len(raw_transactions)}")

            print(f"   🔄 Normalizing {len(raw_transactions)} transactions...")
            normalized = []
            for idx, txn in enumerate(raw_transactions):
                try:
                    norm_txn = self.normalize_transaction(txn)
                    normalized.append(norm_txn)
                except Exception as e:
                    print(f"     ⚠️  Failed to normalize transaction {idx}: {e}")

            print(f"✅ Fetched and normalized {len(normalized)} transactions for account {account_id}")
            if len(normalized) < len(raw_transactions):
                print(f"   ⚠️  {len(raw_transactions) - len(normalized)} transactions failed normalization")

            return normalized
        except Exception as e:
            print(f"❌ Error fetching transactions: {e}")
            import traceback
            traceback.print_exc()
            return []

    def fetch_all_card_transactions(self, card_id: str, days_back: int = 90) -> List[Dict]:
        """
        Fetch all transactions for a card from the past N days.

        Args:
            card_id: TrueLayer card ID
            days_back: Number of days to fetch (default: 90)

        Returns:
            List of normalized card transactions
        """
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        to_date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            raw_transactions = self.get_card_transactions(card_id, from_date, to_date)
            normalized = [self.normalize_card_transaction(txn) for txn in raw_transactions]
            print(f"✅ Fetched {len(normalized)} transactions for card {card_id}")
            return normalized
        except Exception as e:
            print(f"❌ Error fetching card transactions: {e}")
            return []
