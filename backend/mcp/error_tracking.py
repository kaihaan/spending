"""Structured error tracking with automatic classification.

This module provides error tracking for the Gmail sync workflow with:
- Automatic error classification by stage and type
- Database persistence for queryable error history
- Retry tracking and decision support
- Integration with structured logging

Usage:
    from mcp.error_tracking import GmailError, ErrorStage, ErrorType

    # Automatic classification
    try:
        vendor_parser(html, text, subject)
    except Exception as e:
        error = GmailError.from_exception(e, ErrorStage.VENDOR_PARSE,
                                           context={'sender_domain': 'amazon.co.uk'})
        error.log(connection_id=conn_id, sync_job_id=job_id)

    # Manual error creation
    error = GmailError(
        stage=ErrorStage.FETCH,
        error_type=ErrorType.RATE_LIMIT,
        message="Gmail API rate limit exceeded",
        context={'query': 'label:receipts'},
        is_retryable=True
    )
    error.log(connection_id=conn_id)
"""

import traceback
from enum import Enum
from typing import Any

import database_postgres as db

from mcp.logging_config import get_logger

logger = get_logger(__name__)


class ErrorStage(Enum):
    """Error stage classification for Gmail workflow."""

    FETCH = "fetch"  # Gmail API fetch errors
    PARSE = "parse"  # General parsing errors
    VENDOR_PARSE = "vendor_parse"  # Vendor-specific parser errors
    SCHEMA_PARSE = "schema_parse"  # Schema.org extraction errors
    PATTERN_PARSE = "pattern_parse"  # Pattern extraction errors
    LLM_PARSE = "llm_parse"  # LLM enrichment errors
    PDF_PARSE = "pdf_parse"  # PDF processing errors
    STORAGE = "storage"  # Database storage errors
    MATCH = "match"  # Transaction matching errors
    VALIDATION = "validation"  # Data validation errors


class ErrorType(Enum):
    """Error type classification for retry and debugging."""

    API_ERROR = "api_error"  # External API errors
    TIMEOUT = "timeout"  # Timeout errors (retryable)
    PARSE_ERROR = "parse_error"  # Parsing/extraction failures
    VALIDATION = "validation"  # Data validation failures
    DB_ERROR = "db_error"  # Database errors
    NETWORK = "network"  # Network connectivity issues
    RATE_LIMIT = "rate_limit"  # API rate limiting (retryable)
    AUTH_ERROR = "auth_error"  # Authentication failures
    UNKNOWN = "unknown"  # Uncategorized errors


class GmailError:
    """Structured error with logging and database persistence.

    Attributes:
        stage: Error stage (where in workflow error occurred)
        error_type: Error type (for retry and debugging decisions)
        message: Human-readable error message
        exception: Original exception (if any)
        context: Additional context (sender_domain, message_id, etc.)
        is_retryable: Whether error should be retried
        stack_trace: Full stack trace string
    """

    def __init__(
        self,
        stage: ErrorStage,
        error_type: ErrorType,
        message: str,
        exception: Exception | None = None,
        context: dict[str, Any] | None = None,
        is_retryable: bool = False,
    ):
        """Initialize Gmail error.

        Args:
            stage: Error stage from ErrorStage enum
            error_type: Error type from ErrorType enum
            message: Human-readable error description
            exception: Original exception object (optional)
            context: Dict with additional context like message_id, sender_domain
            is_retryable: Whether error is safe to retry
        """
        self.stage = stage
        self.error_type = error_type
        self.message = message
        self.exception = exception
        self.context = context or {}
        self.is_retryable = is_retryable
        self.stack_trace = None

        # Extract stack trace if exception provided
        if exception:
            self.stack_trace = "".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            )

    def log(
        self, connection_id: int | None = None, sync_job_id: int | None = None
    ) -> None:
        """Log error and save to database.

        Args:
            connection_id: Gmail connection ID (optional)
            sync_job_id: Sync job ID (optional)
        """
        # Log to structured logging system
        logger.error(
            f"[{self.stage.value}] {self.message}",
            extra={
                "connection_id": connection_id,
                "sync_job_id": sync_job_id,
                "merchant": self.context.get("sender_domain"),
                "parse_method": self.context.get("parse_method"),
            },
            exc_info=self.exception,
        )

        # Save to database for querying and analytics
        try:
            db.save_gmail_error(
                connection_id=connection_id,
                sync_job_id=sync_job_id,
                message_id=self.context.get("message_id"),
                receipt_id=self.context.get("receipt_id"),
                error_stage=self.stage.value,
                error_type=self.error_type.value,
                error_message=self.message,
                stack_trace=self.stack_trace,
                error_context=self.context,
                is_retryable=self.is_retryable,
            )
        except Exception as e:
            # Don't fail the workflow if error tracking fails
            logger.warning(
                f"Failed to save error to database: {e}",
                extra={"sync_job_id": sync_job_id},
            )

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        stage: ErrorStage,
        context: dict[str, Any] | None = None,
    ) -> "GmailError":
        """Auto-classify error from exception.

        Examines exception type and message to determine error type
        and retry strategy.

        Args:
            exception: Exception object to classify
            stage: Error stage where exception occurred
            context: Additional context dict

        Returns:
            GmailError instance with auto-classified type and retry flag

        Example:
            try:
                response = gmail_api.fetch()
            except Exception as e:
                error = GmailError.from_exception(
                    e, ErrorStage.FETCH,
                    context={'query': 'label:receipts'}
                )
                error.log(connection_id=conn_id)
        """
        error_type = ErrorType.UNKNOWN
        is_retryable = False

        error_str = str(exception).lower()
        exception_name = type(exception).__name__

        # Timeout errors (retryable)
        if "timeout" in error_str or exception_name in ["TimeoutError", "ReadTimeout"]:
            error_type = ErrorType.TIMEOUT
            is_retryable = True

        # Rate limiting (retryable with backoff)
        elif "rate" in error_str or "429" in error_str or "quota" in error_str:
            error_type = ErrorType.RATE_LIMIT
            is_retryable = True

        # Authentication errors (requires user intervention)
        elif "auth" in error_str or "401" in error_str or "unauthorized" in error_str:
            error_type = ErrorType.AUTH_ERROR
            is_retryable = False

        # Network errors (retryable)
        elif (
            "connection" in error_str
            or "network" in error_str
            or exception_name in ["ConnectionError", "ConnectionResetError"]
        ):
            error_type = ErrorType.NETWORK
            is_retryable = True

        # Database errors
        elif (
            "database" in error_str
            or "psycopg2" in error_str
            or "postgres" in error_str
            or "constraint" in error_str
        ):
            error_type = ErrorType.DB_ERROR
            is_retryable = False

        # Validation errors
        elif (
            "validation" in error_str
            or "invalid" in error_str
            or exception_name in ["ValueError", "ValidationError"]
        ):
            error_type = ErrorType.VALIDATION
            is_retryable = False

        # Parse errors (stage-specific)
        elif stage in [
            ErrorStage.PARSE,
            ErrorStage.VENDOR_PARSE,
            ErrorStage.SCHEMA_PARSE,
            ErrorStage.PATTERN_PARSE,
        ]:
            error_type = ErrorType.PARSE_ERROR
            is_retryable = False  # Can't retry parsing same data

        # API errors (general external API failures)
        elif "4" in error_str or "5" in error_str or "api" in error_str:
            error_type = ErrorType.API_ERROR
            is_retryable = True  # Most API errors worth retrying

        return cls(
            stage=stage,
            error_type=error_type,
            message=str(exception),
            exception=exception,
            context=context,
            is_retryable=is_retryable,
        )


def classify_parse_status(parse_result: dict[str, Any] | None) -> str:
    """Classify parsing status for statistics tracking.

    Args:
        parse_result: Dict with parse result or None if failed

    Returns:
        Status string: 'parsed', 'unparseable', 'filtered', or 'failed'
    """
    if not parse_result:
        return "failed"

    if parse_result.get("parsing_status"):
        return parse_result["parsing_status"]

    # Infer status from contents
    if parse_result.get("pre_filter_reject"):
        return "filtered"
    if parse_result.get("total_amount") or parse_result.get("line_items"):
        return "parsed"
    return "unparseable"
