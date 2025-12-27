"""
Flask API HTTP Client

Provides HTTP client for MCP server to communicate with Flask backend.

Features:
- GET, POST, DELETE methods
- Automatic retry with exponential backoff
- Detailed error reporting
- Request/response logging (optional)
- Session management for connection pooling
"""

import logging
import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, Timeout

from ..config import config

logger = logging.getLogger(__name__)


class FlaskAPIError(Exception):
    """Exception raised when Flask API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        endpoint: str | None = None,
        details: str | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.endpoint = endpoint
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert error to dict for MCP error responses."""
        return {
            "error": "api_error",
            "message": self.message,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "details": self.details,
            "retry": self.status_code in [408, 429, 500, 502, 503, 504]
            if self.status_code
            else False,
        }


class FlaskAPIClient:
    """
    HTTP client for Flask API communication.

    Handles:
    - GET, POST, DELETE requests
    - Automatic retries with exponential backoff
    - Session management
    - Error handling and reporting
    """

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        """
        Initialize Flask API client.

        Args:
            base_url: Base URL for Flask API (defaults to config.FLASK_API_URL)
            timeout: Request timeout in seconds (defaults to config.FLASK_API_TIMEOUT)
        """
        self.base_url = base_url or config.FLASK_API_URL
        self.timeout = timeout or config.FLASK_API_TIMEOUT
        self.session = requests.Session()

        # Configure session
        self.session.headers.update(
            {"Content-Type": "application/json", "User-Agent": "MCP-Server/1.0"}
        )

        logger.info(f"FlaskAPIClient initialized: {self.base_url}")

    def _log_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ):
        """Log API request (if enabled)."""
        if config.LOG_API_REQUESTS:
            logger.debug(f"API Request: {method} {endpoint}")
            if params:
                logger.debug(f"  Params: {params}")
            if json_data:
                logger.debug(f"  JSON: {json_data}")

    def _log_response(
        self, method: str, endpoint: str, status_code: int, response_time: float
    ):
        """Log API response (if enabled)."""
        if config.LOG_API_REQUESTS:
            logger.debug(
                f"API Response: {method} {endpoint} - {status_code} ({response_time:.2f}s)"
            )

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        retry_count: int = 0,
    ) -> dict[Any, Any]:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint (e.g., '/api/transactions')
            params: Query parameters
            json_data: JSON request body
            retry_count: Current retry attempt

        Returns:
            JSON response as dict

        Raises:
            FlaskAPIError: If request fails after retries
        """
        url = f"{self.base_url}{endpoint}"

        # Log request
        self._log_request(method, endpoint, params, json_data)

        try:
            start_time = time.time()

            # Make request
            if method == "GET":
                response = self.session.get(url, params=params, timeout=self.timeout)
            elif method == "POST":
                response = self.session.post(
                    url, json=json_data, params=params, timeout=self.timeout
                )
            elif method == "DELETE":
                response = self.session.delete(url, params=params, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response_time = time.time() - start_time

            # Log response
            self._log_response(method, endpoint, response.status_code, response_time)

            # Handle response
            if response.status_code >= 400:
                # Extract error details
                try:
                    error_data = response.json()
                    error_message = error_data.get(
                        "error", error_data.get("message", response.text[:200])
                    )
                except Exception:
                    error_message = response.text[:200]

                # Raise error
                raise FlaskAPIError(
                    message=f"Flask API error: {error_message}",
                    status_code=response.status_code,
                    endpoint=endpoint,
                    details=response.text
                    if len(response.text) < 1000
                    else response.text[:1000],
                )

            # Return JSON response
            try:
                return response.json()
            except ValueError:
                # Non-JSON response (e.g., empty response for DELETE)
                return {"success": True}

        except (Timeout, ConnectionError) as e:
            # Retry on timeout or connection errors
            if config.ENABLE_AUTO_RETRY and retry_count < config.MAX_RETRY_ATTEMPTS:
                wait_time = config.RETRY_BACKOFF_MULTIPLIER**retry_count
                logger.warning(
                    f"Request failed ({type(e).__name__}), retrying in {wait_time}s... (attempt {retry_count + 1}/{config.MAX_RETRY_ATTEMPTS})"
                )
                time.sleep(wait_time)
                return self._make_request(
                    method, endpoint, params, json_data, retry_count + 1
                )
            raise FlaskAPIError(
                message=f"Connection error: {str(e)}",
                endpoint=endpoint,
                details=str(e),
            )

        except FlaskAPIError:
            # Re-raise FlaskAPIError
            raise

        except Exception as e:
            # Unexpected error
            logger.exception(f"Unexpected error in API request: {e}")
            raise FlaskAPIError(
                message=f"Unexpected error: {str(e)}", endpoint=endpoint, details=str(e)
            )

    def get(self, endpoint: str, params: dict | None = None) -> dict[Any, Any]:
        """
        GET request to Flask API.

        Args:
            endpoint: API endpoint (e.g., '/api/transactions')
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            FlaskAPIError: If request fails
        """
        return self._make_request("GET", endpoint, params=params)

    def post(
        self, endpoint: str, json: dict | None = None, params: dict | None = None
    ) -> dict[Any, Any]:
        """
        POST request to Flask API.

        Args:
            endpoint: API endpoint (e.g., '/api/gmail/sync')
            json: JSON request body
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            FlaskAPIError: If request fails
        """
        return self._make_request("POST", endpoint, params=params, json_data=json)

    def delete(self, endpoint: str, params: dict | None = None) -> dict[Any, Any]:
        """
        DELETE request to Flask API.

        Args:
            endpoint: API endpoint (e.g., '/api/gmail/receipts/123')
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            FlaskAPIError: If request fails
        """
        return self._make_request("DELETE", endpoint, params=params)

    def health_check(self) -> bool:
        """
        Check if Flask API is reachable and healthy.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = self.get("/api/health")
            return response.get("status") in ["healthy", "ok"]
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def close(self):
        """Close the session and cleanup resources."""
        self.session.close()
        logger.info("FlaskAPIClient session closed")
