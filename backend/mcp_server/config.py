"""
MCP Server Configuration

Centralized configuration for the MCP server including:
- Flask API connection settings
- Default values for user IDs, date ranges, batch sizes
- Tool enablement flags
- Logging configuration
"""

import os


class MCPServerConfig:
    """Configuration for MCP server operations."""

    # ============================================================================
    # Flask API Connection
    # ============================================================================

    # Flask backend URL
    FLASK_API_URL: str = os.getenv("FLASK_API_URL", "http://localhost:5000")

    # Request timeout in seconds
    FLASK_API_TIMEOUT: int = int(os.getenv("FLASK_API_TIMEOUT", "30"))

    # ============================================================================
    # Default Values
    # ============================================================================

    # Default user ID for operations (most tools assume single user)
    DEFAULT_USER_ID: int = int(os.getenv("DEFAULT_USER_ID", "1"))

    # Default date range for syncs (days back from today)
    DEFAULT_DATE_RANGE_DAYS: int = int(os.getenv("DEFAULT_DATE_RANGE_DAYS", "30"))

    # Default batch size for LLM enrichment
    DEFAULT_BATCH_SIZE: int = int(os.getenv("DEFAULT_BATCH_SIZE", "10"))

    # Default poll interval for async job status checks (seconds)
    DEFAULT_POLL_INTERVAL: int = int(os.getenv("DEFAULT_POLL_INTERVAL", "5"))

    # Default timeout for async jobs (seconds)
    DEFAULT_JOB_TIMEOUT: int = int(os.getenv("DEFAULT_JOB_TIMEOUT", "300"))

    # ============================================================================
    # Tool Settings
    # ============================================================================

    # Enable high-level workflow tools (sync_all_sources, run_full_pipeline, etc.)
    ENABLE_HIGH_LEVEL_TOOLS: bool = (
        os.getenv("ENABLE_HIGH_LEVEL_TOOLS", "true").lower() == "true"
    )

    # Enable low-level operation tools (sync_bank_transactions, sync_gmail_receipts, etc.)
    ENABLE_LOW_LEVEL_TOOLS: bool = (
        os.getenv("ENABLE_LOW_LEVEL_TOOLS", "true").lower() == "true"
    )

    # Enable analytics and monitoring tools
    ENABLE_ANALYTICS_TOOLS: bool = (
        os.getenv("ENABLE_ANALYTICS_TOOLS", "true").lower() == "true"
    )

    # ============================================================================
    # Sync Settings
    # ============================================================================

    # Default Gmail sync type ('full', 'incremental', or 'auto')
    DEFAULT_GMAIL_SYNC_TYPE: str = os.getenv("DEFAULT_GMAIL_SYNC_TYPE", "auto")

    # Staleness threshold for source coverage warnings (days)
    STALENESS_THRESHOLD_DAYS: int = int(os.getenv("STALENESS_THRESHOLD_DAYS", "7"))

    # ============================================================================
    # Logging
    # ============================================================================

    # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Log file path (optional - if not set, logs to stdout only)
    LOG_FILE: str | None = os.getenv("LOG_FILE", None)

    # Enable detailed API request/response logging
    LOG_API_REQUESTS: bool = os.getenv("LOG_API_REQUESTS", "false").lower() == "true"

    # ============================================================================
    # Feature Flags
    # ============================================================================

    # Enable experimental features
    ENABLE_EXPERIMENTAL: bool = (
        os.getenv("ENABLE_EXPERIMENTAL", "false").lower() == "true"
    )

    # Enable auto-retry on API failures
    ENABLE_AUTO_RETRY: bool = os.getenv("ENABLE_AUTO_RETRY", "true").lower() == "true"

    # Maximum retry attempts for API calls
    MAX_RETRY_ATTEMPTS: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))

    # Retry backoff multiplier (exponential backoff)
    RETRY_BACKOFF_MULTIPLIER: float = float(
        os.getenv("RETRY_BACKOFF_MULTIPLIER", "2.0")
    )

    # ============================================================================
    # Helper Methods
    # ============================================================================

    @classmethod
    def get_summary(cls) -> dict:
        """Get configuration summary as dict."""
        return {
            "flask_api_url": cls.FLASK_API_URL,
            "flask_api_timeout": cls.FLASK_API_TIMEOUT,
            "default_user_id": cls.DEFAULT_USER_ID,
            "default_date_range_days": cls.DEFAULT_DATE_RANGE_DAYS,
            "default_batch_size": cls.DEFAULT_BATCH_SIZE,
            "default_poll_interval": cls.DEFAULT_POLL_INTERVAL,
            "default_job_timeout": cls.DEFAULT_JOB_TIMEOUT,
            "tools_enabled": {
                "high_level": cls.ENABLE_HIGH_LEVEL_TOOLS,
                "low_level": cls.ENABLE_LOW_LEVEL_TOOLS,
                "analytics": cls.ENABLE_ANALYTICS_TOOLS,
            },
            "logging": {
                "level": cls.LOG_LEVEL,
                "file": cls.LOG_FILE,
                "api_requests": cls.LOG_API_REQUESTS,
            },
            "features": {
                "experimental": cls.ENABLE_EXPERIMENTAL,
                "auto_retry": cls.ENABLE_AUTO_RETRY,
                "max_retries": cls.MAX_RETRY_ATTEMPTS,
            },
        }

    @classmethod
    def validate(cls) -> tuple[bool, str | None]:
        """
        Validate configuration settings.

        Returns:
            (is_valid, error_message)
        """
        # Validate Flask API URL
        if not cls.FLASK_API_URL:
            return False, "FLASK_API_URL is required"

        if not cls.FLASK_API_URL.startswith(("http://", "https://")):
            return False, "FLASK_API_URL must start with http:// or https://"

        # Validate timeouts
        if cls.FLASK_API_TIMEOUT <= 0:
            return False, "FLASK_API_TIMEOUT must be positive"

        if cls.DEFAULT_JOB_TIMEOUT <= 0:
            return False, "DEFAULT_JOB_TIMEOUT must be positive"

        # Validate poll interval
        if cls.DEFAULT_POLL_INTERVAL <= 0:
            return False, "DEFAULT_POLL_INTERVAL must be positive"

        # Validate date range
        if cls.DEFAULT_DATE_RANGE_DAYS <= 0:
            return False, "DEFAULT_DATE_RANGE_DAYS must be positive"

        # Validate batch size
        if cls.DEFAULT_BATCH_SIZE <= 0:
            return False, "DEFAULT_BATCH_SIZE must be positive"

        # Validate Gmail sync type
        valid_sync_types = ["full", "incremental", "auto"]
        if cls.DEFAULT_GMAIL_SYNC_TYPE not in valid_sync_types:
            return False, f"DEFAULT_GMAIL_SYNC_TYPE must be one of: {valid_sync_types}"

        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if cls.LOG_LEVEL not in valid_log_levels:
            return False, f"LOG_LEVEL must be one of: {valid_log_levels}"

        # Validate retry settings
        if cls.MAX_RETRY_ATTEMPTS < 0:
            return False, "MAX_RETRY_ATTEMPTS must be non-negative"

        if cls.RETRY_BACKOFF_MULTIPLIER <= 0:
            return False, "RETRY_BACKOFF_MULTIPLIER must be positive"

        return True, None


# Singleton instance
config = MCPServerConfig()
