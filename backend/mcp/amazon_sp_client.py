"""
Amazon Business Reporting API Client

Handles API calls to Amazon Business Reporting API v2021-01-08 for BUYER purchase history.
Includes pagination, rate limiting, and token refresh handling.

CRITICAL: This is for BUYERS accessing their own purchase orders, NOT for sellers.

Key Features:
1. Uses 'Authorization: Bearer' header (standard OAuth)
2. Regional base URLs (eu.business-api.amazon.com for UK/Europe)
3. Rate limit: 0.5 requests/second (2 second intervals)
4. Includes line items in single request via includeLineItems parameter
5. Reporting API v2021-01-08 endpoint structure

API Reference: https://developer-docs.amazon.com/amazon-business/docs/reporting-api-v1-reference-1
Data Model: https://developer-docs.amazon.com/amazon-business/docs/reporting-api-v1-model
"""

import os
import time
from datetime import datetime

import requests

import database
from mcp.amazon_sp_auth import get_valid_access_token

# Regional API base URLs for Amazon Business
REGION_API_BASES = {
    "UK": "https://eu.business-api.amazon.com",
    "DE": "https://eu.business-api.amazon.com",
    "FR": "https://eu.business-api.amazon.com",
    "ES": "https://eu.business-api.amazon.com",
    "IT": "https://eu.business-api.amazon.com",
    "IN": "https://eu.business-api.amazon.com",
    "US": "https://na.business-api.amazon.com",
    "CA": "https://na.business-api.amazon.com",
    "MX": "https://na.business-api.amazon.com",
    "JP": "https://jp.business-api.amazon.com",
    "AU": "https://jp.business-api.amazon.com",
}

# Rate limiting (Amazon Business Reporting API)
# 0.5 requests/second = 1 request per 2 seconds
MIN_REQUEST_INTERVAL = 2.0


class AmazonBusinessClient:
    """Client for Amazon Business Reporting API v2021-01-08."""

    def __init__(self, connection_id: int = None, user_id: int = 1):
        """Initialize Amazon Business API client with OAuth connection.

        Args:
            connection_id: Specific connection ID, or None for user's active connection
            user_id: User ID for looking up connection (default 1)
        """
        self.connection = database.get_amazon_business_connection(
            connection_id=connection_id, user_id=user_id
        )

        if not self.connection:
            raise ValueError(
                "No Amazon Business API connection found. Please connect first."
            )

        # Determine environment and region
        self.is_sandbox = self.connection.get("is_sandbox", True)
        self.region = self.connection.get("region", "UK")

        # Set API base URL (from env or region mapping)
        self.api_base = self._get_api_base()

        # Rate limiting tracking
        self._last_request_time = 0

    def _get_api_base(self) -> str:
        """Get Amazon Business API base URL based on environment and region.

        Returns:
            Base URL for Amazon Business API
        """
        # Check for explicit base URL in environment
        env_base = os.getenv("AMAZON_BUSINESS_API_BASE")
        if env_base:
            return env_base.rstrip("/")

        # Use regional mapping
        return REGION_API_BASES.get(self.region, REGION_API_BASES["UK"])

    def _get_headers(self) -> dict:
        """Get request headers with valid access token.

        Amazon Business API uses standard OAuth 'Authorization: Bearer' header.

        Returns:
            Dictionary of HTTP headers
        """
        access_token = get_valid_access_token(self.connection)
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _rate_limit(self):
        """Ensure we don't exceed rate limits (0.5 req/sec = 2 second intervals)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            sleep_time = MIN_REQUEST_INTERVAL - elapsed
            print(f"[Amazon Business API] Rate limiting: waiting {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _make_request(
        self, method: str, endpoint: str, params: dict = None, data: dict = None
    ) -> dict:
        """Make rate-limited API request to Amazon Business API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., '/reports/2021-01-08/orders')
            params: Query parameters
            data: Request body for POST

        Returns:
            API response as dictionary

        Raises:
            Exception: If request fails
        """
        # Apply rate limiting
        self._rate_limit()

        url = f"{self.api_base}{endpoint}"
        headers = self._get_headers()

        print(f"[Amazon Business API] {method} {url}")
        if params:
            print(f"[Amazon Business API] Params: {params}")

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data,
            timeout=30,
        )

        # Handle token expiry
        if response.status_code == 401:
            print(
                "[Amazon Business API] 401 Unauthorized - token might be invalid, refreshing connection"
            )
            # Refresh connection from database
            self.connection = database.get_amazon_business_connection(
                connection_id=self.connection["id"]
            )
            headers = self._get_headers()

            # Retry request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
                timeout=30,
            )

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            print(
                f"[Amazon Business API] Rate limited (429), waiting {retry_after}s..."
            )
            time.sleep(retry_after)
            return self._make_request(method, endpoint, params, data)

        # Handle errors
        if not response.ok:
            error_msg = f"Amazon Business API request failed: {response.status_code}"
            try:
                error_data = response.json()
                if "errors" in error_data:
                    error_details = ", ".join(
                        [e.get("message", "") for e in error_data["errors"]]
                    )
                    error_msg += f" - {error_details}"
                elif "message" in error_data:
                    error_msg += f" - {error_data['message']}"
                else:
                    error_msg += f" - {response.text}"
            except Exception:  # Fixed: was bare except
                error_msg += f" - {response.text}"

            print(f"[Amazon Business API] {error_msg}")
            raise Exception(error_msg)

        return response.json()

    def get_orders(
        self,
        start_date: str,
        end_date: str,
        include_line_items: bool = True,
        include_shipments: bool = False,
        include_charges: bool = False,
    ) -> list[dict]:
        """Fetch buyer's purchase orders in date range using Reporting API v2021-01-08.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            include_line_items: Include line item details (default True)
            include_shipments: Include shipment tracking (default False)
            include_charges: Include charge breakdown (default False)

        Returns:
            List of order dictionaries in Amazon Business API format
        """
        all_orders = []
        next_page_token = None

        print(f"[Amazon Business API] Fetching orders from {start_date} to {end_date}")
        print(
            f"[Amazon Business API] Environment: {'SANDBOX' if self.is_sandbox else 'PRODUCTION'}"
        )
        print(f"[Amazon Business API] Region: {self.region}")
        print(f"[Amazon Business API] Base URL: {self.api_base}")

        while True:
            # Build query parameters
            params = {
                "startDate": start_date + "T00:00:00Z",  # ISO 8601 format
                "endDate": end_date + "T23:59:59Z",
                "includeLineItems": str(include_line_items).lower(),
                "includeShipments": str(include_shipments).lower(),
                "includeCharges": str(include_charges).lower(),
            }

            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = self._make_request(
                "GET", "/reports/2021-01-08/orders", params=params
            )

            # Extract orders from response
            orders = response.get("orders", [])
            all_orders.extend(orders)

            print(
                f"[Amazon Business API] Fetched {len(orders)} orders (total: {len(all_orders)})"
            )

            # Check for next page
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return all_orders

    def _normalize_order(self, order: dict) -> dict:
        """Convert Amazon Business API order format to database schema.

        Args:
            order: Order dictionary from Amazon Business API

        Returns:
            Normalized order dictionary for database insertion
        """
        # Extract financial data (Money objects with amount and currencyCode)
        subtotal = order.get("orderSubTotal", {})
        shipping = order.get("orderShippingAndHandling", {})
        tax = order.get("orderTax", {})
        net_total = order.get("orderNetTotal", {})

        # Extract buyer info
        buyer = order.get("buyingCustomer", {})

        return {
            "order_id": order.get("orderId"),
            "order_date": order.get("orderDate", "").split("T")[0],  # Extract date only
            "region": self.region,
            "purchase_order_number": order.get("purchaseOrderNumber"),
            "order_status": order.get("orderStatus"),
            "buyer_name": buyer.get("name"),
            "buyer_email": buyer.get("email"),
            "subtotal": float(subtotal.get("amount", 0)) if subtotal else 0,
            "tax": float(tax.get("amount", 0)) if tax else 0,
            "shipping": float(shipping.get("amount", 0)) if shipping else 0,
            "net_total": float(net_total.get("amount", 0)) if net_total else 0,
            "currency": net_total.get("currencyCode", "GBP") if net_total else "GBP",
            "item_count": len(order.get("lineItems", [])),
        }

    def _normalize_order_item(self, item: dict, order_id: str) -> dict:
        """Convert Amazon Business API line item format to database schema.

        Args:
            item: Line item dictionary from Amazon Business API
            order_id: Parent order ID

        Returns:
            Normalized item dictionary for database insertion
        """
        # Extract pricing (Money objects)
        unit_price = item.get("purchasedPricePerUnit", {})
        total_price = item.get("itemNetTotal", {})
        quantity = item.get("itemQuantity", 1)

        # Extract seller info
        seller = item.get("seller", {})

        return {
            "order_id": order_id,
            "line_item_id": None,  # Amazon Business API doesn't provide line item ID
            "asin": item.get("asin"),
            "title": item.get("title"),
            "brand": None,  # Not directly provided in API response
            "category": item.get("productCategory"),
            "quantity": quantity,
            "unit_price": float(unit_price.get("amount", 0)) if unit_price else 0,
            "total_price": float(total_price.get("amount", 0)) if total_price else 0,
            "seller_name": seller.get("name") if seller else None,
        }

    def test_connection(self) -> dict:
        """Test Amazon Business API connection by making a minimal request.

        Returns:
            Dictionary with connection status
        """
        try:
            # Try to fetch orders from today only as a test
            today = datetime.now().strftime("%Y-%m-%d")
            self._make_request(
                "GET",
                "/reports/2021-01-08/orders",
                params={
                    "startDate": today + "T00:00:00Z",
                    "endDate": today + "T23:59:59Z",
                    "includeLineItems": "false",
                },
            )

            return {
                "connected": True,
                "region": self.region,
                "api_base": self.api_base,
                "environment": "sandbox" if self.is_sandbox else "production",
                "status": "active",
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "environment": "sandbox" if self.is_sandbox else "production",
            }
