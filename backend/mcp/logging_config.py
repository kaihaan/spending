"""Centralized logging configuration for Gmail workflow.

This module provides structured logging with context fields for Gmail sync operations.
Logs are written to both console (for Docker logs) and rotating files.

Usage:
    from mcp.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Starting sync", extra={'sync_job_id': job_id, 'connection_id': conn_id})
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Log directory from environment or default
# In Docker: /app/.claude/logs (mounted volume)
# In local dev: /home/kaihaan/prj/spending/.claude/logs
LOG_DIR = os.getenv("LOG_DIR", "/app/.claude/logs")


class StructuredFormatter(logging.Formatter):
    """Custom formatter that adds context fields to log records.

    Supports the following context fields via extra={} parameter:
    - sync_job_id: Gmail sync job ID
    - connection_id: Gmail connection ID
    - merchant: Merchant/sender domain
    - parse_method: Parse method used
    """

    def format(self, record):
        """Format log record with context fields."""
        # Add context fields with None defaults if not present
        record.sync_job_id = getattr(record, "sync_job_id", None)
        record.connection_id = getattr(record, "connection_id", None)
        record.merchant = getattr(record, "merchant", None)
        record.parse_method = getattr(record, "parse_method", None)

        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Get configured logger for Gmail operations.

    Creates a logger with:
    - Console handler for Docker logs (INFO level)
    - Rotating file handler for all logs (DEBUG level)
    - Separate error file handler (ERROR level)

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logging.Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing email", extra={'merchant': 'amazon.co.uk'})
    """
    logger = logging.getLogger(name)

    # Skip if already configured (prevents duplicate handlers)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Don't propagate to root logger

    # Ensure log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # ========================================
    # Console Handler (for Docker logs)
    # ========================================
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        StructuredFormatter("[%(levelname)s] [job:%(sync_job_id)s] %(message)s")
    )
    logger.addHandler(console)

    # ========================================
    # File Handler (rotating, all levels)
    # ========================================
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "gmail_sync.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB per file
        backupCount=30,  # Keep 30 backup files
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        StructuredFormatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] "
            "[job:%(sync_job_id)s merchant:%(merchant)s] %(message)s"
        )
    )
    logger.addHandler(file_handler)

    # ========================================
    # Error File Handler (errors only)
    # ========================================
    error_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "gmail_errors.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB per file
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(
        StructuredFormatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] "
            "[job:%(sync_job_id)s merchant:%(merchant)s] %(message)s"
        )
    )
    logger.addHandler(error_handler)

    return logger


def get_log_file_path(filename: str) -> str:
    """Get full path to log file.

    Args:
        filename: Name of log file (e.g., 'gmail_sync.log')

    Returns:
        Full path to log file
    """
    return os.path.join(LOG_DIR, filename)
