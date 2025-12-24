"""
Amazon Business Reporting API Client

Handles API calls to Amazon Business Reporting API v2025-06-09.
Includes pagination, rate limiting, and token refresh handling.

API Reference: https://developer-docs.amazon.com/amazon-business/docs/reporting-api-overview
Rate Limits: 0.5 req/sec sustained, burst 10
"""

import time
import requests
from datetime import datetime, timedelta
from typing import List, Optional
import database_postgres as database
from mcp.amazon_business_auth import get_valid_access_token

# Amazon Business API base URL
# Note: This may need to be updated based on actual Amazon Business API documentation
API_BASE_UK = "https://business-api.amazon.co.uk"
API_BASE_US = "https://business-api.amazon.com"
API_BASE_DE = "https://business-api.amazon.de"

API_VERSION = "2025-06-09"

# Rate limiting: 0.5 requests per second = 1 request every 2 seconds
MIN_REQUEST_INTERVAL = 2.0


class AmazonBusinessClient:
    """Client for Amazon Business Reporting API."""

    def __init__(self, connection_id: int = None, user_id: int = 1):
        """Initialize client with OAuth connection.

        Args:
            connection_id: Specific connection ID, or None for user's active connection
            user_id: User ID for looking up connection (default 1)
        """
        self.connection = database.get_amazon_business_connection(
            connection_id=connection_id,
            user_id=user_id
        )

        if not self.connection:
            raise ValueError("No Amazon Business connection found. Please connect first.")

        # Set API base URL based on region
        self.api_base = self._get_api_base(self.connection.get('region', 'UK'))
        self._last_request_time = 0

    def _get_api_base(self, region: str) -> str:
        """Get API base URL for region."""
        region_map = {
            'UK': API_BASE_UK,
            'US': API_BASE_US,
            'DE': API_BASE_DE
        }
        return region_map.get(region, API_BASE_UK)

    def _get_headers(self) -> dict:
        """Get request headers with valid access token."""
        access_token = get_valid_access_token(self.connection)
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, method: str, endpoint: str, params: dict = None,
                      data: dict = None) -> dict:
        """Make rate-limited API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body for POST

        Returns:
            API response as dictionary

        Raises:
            Exception: If request fails
        """
        self._rate_limit()

        url = f"{self.api_base}{endpoint}"
        headers = self._get_headers()

        print(f"[Amazon Business API] {method} {url}")

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data
        )

        if response.status_code == 401:
            # Token might be invalid, refresh connection and retry
            self.connection = database.get_amazon_business_connection(
                connection_id=self.connection['id']
            )
            headers = self._get_headers()
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data
            )

        if response.status_code == 429:
            # Rate limited, wait and retry
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"[Amazon Business API] Rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            return self._make_request(method, endpoint, params, data)

        if not response.ok:
            error_msg = f"API request failed: {response.status_code} - {response.text}"
            print(f"[Amazon Business API] {error_msg}")
            raise Exception(error_msg)

        return response.json()

    def get_orders(self, start_date: str, end_date: str) -> List[dict]:
        """Fetch orders in date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of order dictionaries
        """
        all_orders = []
        next_token = None

        print(f"[Amazon Business API] Fetching orders from {start_date} to {end_date}")

        while True:
            params = {
                "orderStartDate": start_date,
                "orderEndDate": end_date,
                "region": self.connection.get('region', 'UK')
            }

            if next_token:
                params["nextPageToken"] = next_token

            response = self._make_request(
                "GET",
                f"/reports/{API_VERSION}/orderReports",
                params=params
            )

            orders = response.get('orders', [])
            all_orders.extend(orders)
            print(f"[Amazon Business API] Fetched {len(orders)} orders (total: {len(all_orders)})")

            next_token = response.get('nextPageToken')
            if not next_token:
                break

        return all_orders

    def get_line_items(self, start_date: str, end_date: str) -> List[dict]:
        """Fetch order line items in date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of line item dictionaries
        """
        all_items = []
        next_token = None

        print(f"[Amazon Business API] Fetching line items from {start_date} to {end_date}")

        while True:
            params = {
                "orderStartDate": start_date,
                "orderEndDate": end_date,
                "region": self.connection.get('region', 'UK')
            }

            if next_token:
                params["nextPageToken"] = next_token

            response = self._make_request(
                "GET",
                f"/reports/{API_VERSION}/orderLineItemReports",
                params=params
            )

            items = response.get('lineItems', [])
            all_items.extend(items)
            print(f"[Amazon Business API] Fetched {len(items)} line items (total: {len(all_items)})")

            next_token = response.get('nextPageToken')
            if not next_token:
                break

        return all_items

    def get_order_details(self, order_id: str) -> Optional[dict]:
        """Fetch details for a specific order.

        Args:
            order_id: Amazon order ID

        Returns:
            Order details dictionary or None
        """
        try:
            response = self._make_request(
                "GET",
                f"/reports/{API_VERSION}/orderReports/{order_id}"
            )
            return response.get('order')
        except Exception as e:
            print(f"[Amazon Business API] Error fetching order {order_id}: {e}")
            return None

    def test_connection(self) -> dict:
        """Test API connection by making a minimal request.

        Returns:
            Dictionary with connection status
        """
        try:
            # Try to fetch orders from today only as a test
            today = datetime.now().strftime('%Y-%m-%d')
            self._make_request(
                "GET",
                f"/reports/{API_VERSION}/orderReports",
                params={
                    "orderStartDate": today,
                    "orderEndDate": today,
                    "region": self.connection.get('region', 'UK')
                }
            )
            return {
                "connected": True,
                "region": self.connection.get('region'),
                "status": "active"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }


def import_orders_for_date_range(start_date: str, end_date: str,
                                  connection_id: int = None) -> dict:
    """Import orders and line items for a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        connection_id: Optional specific connection ID

    Returns:
        Dictionary with import statistics
    """
    client = AmazonBusinessClient(connection_id=connection_id)

    # Fetch orders
    orders = client.get_orders(start_date, end_date)
    imported_orders, duplicate_orders = database.import_amazon_business_orders(orders)

    # Fetch line items
    line_items = client.get_line_items(start_date, end_date)
    imported_items = database.import_amazon_business_line_items(line_items)

    return {
        "orders_fetched": len(orders),
        "orders_imported": imported_orders,
        "orders_duplicates": duplicate_orders,
        "line_items_fetched": len(line_items),
        "line_items_imported": imported_items
    }
