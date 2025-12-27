"""
TrueLayer API Client

Wrapper for TrueLayer Data API endpoints.
Handles account information, transaction fetching, and balance queries.
"""

import os
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

# Load environment variables (Docker env vars take precedence)
load_dotenv(override=False)

TRUELAYER_ENV = os.getenv("TRUELAYER_ENVIRONMENT", "sandbox")

# API URLs
if TRUELAYER_ENV == "production":
    TRUELAYER_API_URL = "https://api.truelayer.com"
else:
    TRUELAYER_API_URL = "https://api.sandbox.truelayer.com"


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
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """
        Make HTTP request to TrueLayer API with automatic retry on rate limits.

        Implements exponential backoff for 429 (rate limit) errors to handle:
        - Provider-level rate limits (EU banks)
        - TrueLayer unattended call limits

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to requests

        Returns:
            JSON response from API

        Raises:
            requests.RequestException: After max retries or for non-retryable errors
        """
        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        retry_delay = 2  # Start with 2 seconds

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"   🔄 Retry attempt {attempt + 1}/{max_retries}")

                print(f"   🌐 Request: {method} {url}")
                print(
                    f"   🌐 Headers: Authorization=Bearer {self.access_token[:20]}..."
                )
                if "params" in kwargs:
                    print(f"   🌐 Query params: {kwargs['params']}")

                response = requests.request(
                    method, url, headers=self.headers, timeout=10, **kwargs
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
                                print(
                                    f"   🌐     First item keys: {list(val[0].keys())}"
                                )
                        elif isinstance(val, dict):
                            print(
                                f"   🌐   - '{key}': dict with keys {list(val.keys())}"
                            )
                        else:
                            print(f"   🌐   - '{key}': {type(val).__name__}")
                elif isinstance(json_response, list):
                    print(
                        f"   🌐 Response is direct array with {len(json_response)} items"
                    )
                    if json_response and isinstance(json_response[0], dict):
                        print(f"   🌐 First item keys: {list(json_response[0].keys())}")

                return json_response

            except requests.HTTPError as e:
                # Handle rate limiting (429) with exponential backoff
                if e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        # Exponential backoff: 2s, 4s, 8s
                        wait_time = retry_delay * (2**attempt)
                        error_type = "provider_too_many_requests"  # Default

                        # Try to parse error type from response
                        try:
                            error_data = e.response.json()
                            error_type = error_data.get(
                                "error", "provider_too_many_requests"
                            )
                        except Exception:  # Fixed: was bare except
                            pass

                        print(
                            f"⚠️  Rate limited (429: {error_type}), retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue  # Retry
                    # Max retries exceeded
                    print(
                        f"❌ Rate limit persists after {max_retries} attempts, giving up"
                    )
                    print(f"   Status code: {e.response.status_code}")
                    try:
                        print(f"   Response: {e.response.text}")
                    except Exception:  # Fixed: was bare except
                        pass
                    raise  # Re-raise to caller

                # Non-retryable error (not 429)
                print(f"❌ API request failed: {method} {endpoint}")
                print(f"   Error: {e}")
                print(f"   Status code: {e.response.status_code}")
                try:
                    print(f"   Response: {e.response.text}")
                except Exception:  # Fixed: was bare except
                    pass
                raise

            except requests.RequestException as e:
                # Network errors, timeouts, etc.
                print(f"❌ API request failed: {method} {endpoint}")
                print(f"   Error: {e}")
                if hasattr(e, "response") and e.response is not None:
                    print(f"   Status code: {e.response.status_code}")
                    try:
                        print(f"   Response: {e.response.text}")
                    except Exception:  # Fixed: was bare except
                        pass
                raise

        # This should never be reached, but just in case
        raise requests.RequestException(f"Failed after {max_retries} attempts")

    def get_me(self) -> dict:
        """Get authenticated user information."""
        return self._make_request("GET", "/data/v1/info")

    def get_accounts(self) -> list[dict]:
        """
        Get list of connected bank accounts.

        Returns:
            List of account dictionaries
        """
        print("   📡 Calling TrueLayer API: GET /data/v1/accounts")
        response = self._make_request("GET", "/data/v1/accounts")
        accounts = response.get("results", [])
        print(f"   📡 API response: {len(accounts)} accounts in 'results' field")
        if response.get("status") or response.get("error"):
            print(
                f"   ⚠️  Response has status/error: {response.get('status')} / {response.get('error')}"
            )
        print(f"   📡 Full response keys: {list(response.keys())}")
        return accounts

    def get_cards(self) -> list[dict]:
        """
        Get list of connected credit/debit cards.

        Returns:
            List of card dictionaries
        """
        response = self._make_request("GET", "/data/v1/cards")
        return response.get("results", [])

    def get_account(self, account_id: str) -> dict:
        """
        Get details for a specific account.

        Args:
            account_id: TrueLayer account ID

        Returns:
            Account details dictionary
        """
        return self._make_request("GET", f"/data/v1/accounts/{account_id}")

    def get_account_balance(self, account_id: str) -> dict:
        """
        Get current balance for an account.

        Args:
            account_id: TrueLayer account ID

        Returns:
            Balance information
        """
        response = self._make_request("GET", f"/data/v1/accounts/{account_id}/balance")
        results = response.get("results", [])
        return results[0] if results else {}

    def get_transactions(
        self,
        account_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get transactions for an account with automatic pagination.

        Args:
            account_id: TrueLayer account ID
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Page size (default: 100, max per request)

        Returns:
            List of ALL transaction dictionaries (paginated automatically)
        """
        all_transactions = []
        page = 1
        max_pages = 50  # Safety limit to prevent infinite loops

        while page <= max_pages:
            params = {"limit": limit}

            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date

            # Add cursor for pagination (if we have one from previous page)
            if page > 1 and hasattr(self, "_last_cursor") and self._last_cursor:
                params["cursor"] = self._last_cursor

            try:
                response = self._make_request(
                    "GET", f"/data/v1/accounts/{account_id}/transactions", params=params
                )

                # Handle multiple possible response structures
                transactions = None
                next_cursor = None

                if isinstance(response, list):
                    # If response is a direct array
                    transactions = response
                elif isinstance(response, dict):
                    # Try common key names for transaction list
                    for key in ["results", "data", "transactions", "items"]:
                        if key in response:
                            transactions = response.get(key, [])
                            break

                    # Check for pagination cursor/token
                    next_cursor = (
                        response.get("next_cursor")
                        or response.get("cursor")
                        or response.get("next")
                    )

                if transactions is None:
                    print(f"⚠️  Could not find transactions in response page {page}")
                    break

                if len(transactions) == 0:
                    print(f"   ✅ Page {page}: No more transactions")
                    break

                print(f"   ✅ Page {page}: Fetched {len(transactions)} transactions")
                all_transactions.extend(transactions)

                # Check if there are more pages
                if len(transactions) < limit and not next_cursor:
                    # Less than full page and no cursor = end of results
                    break

                if next_cursor:
                    self._last_cursor = next_cursor
                    page += 1
                elif len(transactions) == limit:
                    # Full page but no cursor - try one more page with offset
                    # (some APIs use offset instead of cursor)
                    page += 1
                else:
                    # Partial page and no cursor - we're done
                    break

            except Exception as e:
                print(f"❌ Error fetching transactions page {page}: {e}")
                break

        print(
            f"   📦 Total transactions fetched: {len(all_transactions)} (across {page} page(s))"
        )
        return all_transactions

    def get_pending_transactions(self, account_id: str) -> list[dict]:
        """
        Get pending transactions for an account.

        Args:
            account_id: TrueLayer account ID

        Returns:
            List of pending transaction dictionaries
        """
        response = self._make_request(
            "GET", f"/data/v1/accounts/{account_id}/transactions/pending"
        )
        return response.get("results", [])

    def get_card(self, card_id: str) -> dict:
        """
        Get details for a specific card.

        Args:
            card_id: TrueLayer card ID

        Returns:
            Card details dictionary
        """
        return self._make_request("GET", f"/data/v1/cards/{card_id}")

    def get_card_balance(self, card_id: str) -> dict:
        """
        Get current balance for a card.

        Args:
            card_id: TrueLayer card ID

        Returns:
            Balance information
        """
        response = self._make_request("GET", f"/data/v1/cards/{card_id}/balance")
        results = response.get("results", [])
        return results[0] if results else {}

    def get_card_transactions(
        self,
        card_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
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
        params = {"limit": limit}

        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        response = self._make_request(
            "GET", f"/data/v1/cards/{card_id}/transactions", params=params
        )
        return response.get("results", [])

    def normalize_transaction(self, truelayer_txn: dict) -> dict:
        """
        Normalize TrueLayer transaction to app format.

        Args:
            truelayer_txn: Raw transaction from TrueLayer API

        Returns:
            Normalized transaction dictionary
        """
        # Extract running balance amount if it's a dict, otherwise use as-is
        running_balance = truelayer_txn.get("running_balance")
        if isinstance(running_balance, dict):
            running_balance = running_balance.get("amount")

        return {
            "date": truelayer_txn.get("timestamp", "").split("T")[
                0
            ],  # Extract date part
            "description": truelayer_txn.get("description", ""),
            "merchant_name": truelayer_txn.get("merchant_name"),
            "transaction_type": truelayer_txn.get(
                "transaction_type"
            ),  # DEBIT or CREDIT
            "amount": abs(float(truelayer_txn.get("amount", 0))),
            "currency": truelayer_txn.get("currency", "GBP"),
            "transaction_code": truelayer_txn.get("transaction_code"),
            "transaction_id": truelayer_txn.get("transaction_id"),
            "normalised_provider_id": truelayer_txn.get(
                "normalised_provider_transaction_id"
            ),
            "category": truelayer_txn.get(
                "transaction_category"
            ),  # May be provided by TrueLayer
            "running_balance": running_balance,
            "metadata": {
                "provider_id": truelayer_txn.get("provider_id"),
                "provider_transaction_id": truelayer_txn.get("provider_transaction_id"),
                "meta": truelayer_txn.get("meta", {}),
            },
        }

    def get_last_sync_date(self, account_id: str) -> str | None:
        """
        Get the last sync date for an account to avoid re-fetching.

        For production use, this would query the database.
        For now, return None to fetch all transactions.
        """
        # TODO: Query database for last_synced_at for this account
        return None

    def normalize_card_transaction(self, truelayer_txn: dict) -> dict:
        """
        Normalize TrueLayer card transaction to app format.
        Uses the same structure as account transactions for consistency.

        Args:
            truelayer_txn: Raw transaction from TrueLayer API

        Returns:
            Normalized card transaction dictionary
        """
        # Extract running balance amount if it's a dict, otherwise use as-is
        running_balance = truelayer_txn.get("running_balance")
        if isinstance(running_balance, dict):
            running_balance = running_balance.get("amount")

        return {
            "date": truelayer_txn.get("timestamp", "").split("T")[0],
            "description": truelayer_txn.get("description", ""),
            "merchant_name": truelayer_txn.get("merchant_name"),
            "transaction_type": truelayer_txn.get("transaction_type"),
            "amount": abs(float(truelayer_txn.get("amount", 0))),
            "currency": truelayer_txn.get("currency", "GBP"),
            "transaction_code": truelayer_txn.get("transaction_code"),
            "transaction_id": truelayer_txn.get("transaction_id"),
            "normalised_provider_id": truelayer_txn.get(
                "normalised_provider_transaction_id"
            ),
            "category": truelayer_txn.get("transaction_category"),
            "running_balance": running_balance,
            "metadata": {
                "provider_id": truelayer_txn.get("provider_id"),
                "provider_transaction_id": truelayer_txn.get("provider_transaction_id"),
                "meta": truelayer_txn.get("meta", {}),
            },
        }

    def fetch_all_transactions(
        self, account_id: str, days_back: int = 90
    ) -> list[dict]:
        """
        Fetch all transactions for an account from the past N days.

        Args:
            account_id: TrueLayer account ID
            days_back: Number of days to fetch (default: 90)

        Returns:
            List of normalized transactions
        """
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

        print(f"   📅 Date range: {from_date} to {to_date} ({days_back} days)")

        try:
            print("   🔍 Fetching raw transactions from TrueLayer API...")
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

            print(
                f"✅ Fetched and normalized {len(normalized)} transactions for account {account_id}"
            )
            if len(normalized) < len(raw_transactions):
                print(
                    f"   ⚠️  {len(raw_transactions) - len(normalized)} transactions failed normalization"
                )

            return normalized
        except Exception as e:
            print(f"❌ Error fetching transactions: {e}")
            import traceback

            traceback.print_exc()
            return []

    def fetch_all_card_transactions(
        self, card_id: str, days_back: int = 90
    ) -> list[dict]:
        """
        Fetch all transactions for a card from the past N days.

        Args:
            card_id: TrueLayer card ID
            days_back: Number of days to fetch (default: 90)

        Returns:
            List of normalized card transactions
        """
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

        try:
            raw_transactions = self.get_card_transactions(card_id, from_date, to_date)
            normalized = [
                self.normalize_card_transaction(txn) for txn in raw_transactions
            ]
            print(f"✅ Fetched {len(normalized)} transactions for card {card_id}")
            return normalized
        except Exception as e:
            print(f"❌ Error fetching card transactions: {e}")
            return []
