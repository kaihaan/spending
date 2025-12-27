"""
Response Formatting

Utilities for formatting API responses for MCP tools.

Provides:
- Success response formatting
- Error response formatting
- Timestamp formatting
- Summary generation
"""

from datetime import datetime
from typing import Any


def format_success_response(data: Any, message: str | None = None) -> dict:
    """
    Format successful tool response.

    Args:
        data: Response data (dict, list, or primitive)
        message: Optional success message

    Returns:
        Formatted response dict
    """
    response = {"success": True, "timestamp": datetime.now().isoformat()}

    if message:
        response["message"] = message

    # Add data based on type
    if isinstance(data, dict):
        response.update(data)
    elif isinstance(data, list):
        response["data"] = data
    else:
        response["result"] = data

    return response


def format_error_response(error: Exception, context: dict | None = None) -> dict:
    """
    Format error response for MCP tools.

    Args:
        error: Exception that occurred
        context: Optional context (endpoint, parameters, etc.)

    Returns:
        Formatted error dict
    """
    # Handle custom error types with to_dict() method
    if hasattr(error, "to_dict"):
        return error.to_dict()

    # Generic error formatting
    response = {
        "success": False,
        "error": type(error).__name__,
        "message": str(error),
        "timestamp": datetime.now().isoformat(),
    }

    if context:
        response["context"] = context

    return response


def format_job_status(job_data: dict) -> dict:
    """
    Format job status response.

    Args:
        job_data: Raw job data from API

    Returns:
        Formatted job status
    """
    return {
        "job_id": job_data.get("job_id"),
        "status": job_data.get("status"),
        "type": job_data.get("job_type", job_data.get("type")),
        "created_at": job_data.get("created_at"),
        "completed_at": job_data.get("completed_at"),
        "progress": job_data.get("progress"),
        "result": job_data.get("result"),
        "error": job_data.get("error"),
    }


def format_sync_summary(sync_results: dict, sources: list[str]) -> dict:
    """
    Format sync operation summary.

    Args:
        sync_results: Raw sync results from API
        sources: List of sources that were synced

    Returns:
        Formatted sync summary
    """
    return {
        "status": "completed",
        "sources_synced": sources,
        "results": sync_results,
        "timestamp": datetime.now().isoformat(),
    }


def format_matching_summary(matching_results: dict) -> dict:
    """
    Format matching operation summary.

    Args:
        matching_results: Raw matching results from API

    Returns:
        Formatted matching summary
    """
    return {
        "status": "completed",
        "total_matched": matching_results.get("matched", 0),
        "confidence_avg": matching_results.get("confidence_avg", 0),
        "high_confidence": matching_results.get("high_confidence", 0),
        "medium_confidence": matching_results.get("medium_confidence", 0),
        "low_confidence": matching_results.get("low_confidence", 0),
        "timestamp": datetime.now().isoformat(),
    }


def format_enrichment_summary(enrichment_data: dict) -> dict:
    """
    Format enrichment operation summary.

    Args:
        enrichment_data: Raw enrichment data from API

    Returns:
        Formatted enrichment summary
    """
    return {
        "job_id": enrichment_data.get("job_id"),
        "status": enrichment_data.get("status"),
        "transactions_queued": enrichment_data.get("transactions_queued", 0),
        "estimated_cost": enrichment_data.get("estimated_cost"),
        "provider": enrichment_data.get("provider"),
        "model": enrichment_data.get("model"),
        "timestamp": datetime.now().isoformat(),
    }


def format_connection_status(connection_data: dict, source: str) -> dict:
    """
    Format connection status for a source.

    Args:
        connection_data: Raw connection data from API
        source: Source name (truelayer, gmail, etc.)

    Returns:
        Formatted connection status
    """
    if not connection_data or connection_data.get("connected") is False:
        return {
            "source": source,
            "connected": False,
            "message": f"{source.title()} not connected",
        }

    return {
        "source": source,
        "connected": True,
        "provider": connection_data.get(
            "provider_name", connection_data.get("provider")
        ),
        "account": connection_data.get("email_address", connection_data.get("account")),
        "last_synced": connection_data.get("last_synced"),
        "token_expires_at": connection_data.get("token_expires_at"),
        "warning": connection_data.get("warning"),
    }


def format_analytics_summary(analytics_data: dict, period: str) -> dict:
    """
    Format system analytics summary.

    Args:
        analytics_data: Raw analytics data
        period: Time period ('week', 'month', 'year')

    Returns:
        Formatted analytics summary
    """
    return {
        "period": period,
        "transactions": analytics_data.get("transactions", {}),
        "matching_coverage": analytics_data.get("matching_coverage", {}),
        "enrichment": analytics_data.get("enrichment", {}),
        "spending": analytics_data.get("spending", {}),
        "timestamp": datetime.now().isoformat(),
    }


def format_log_entry(log_data: dict) -> dict:
    """
    Format log entry for display.

    Args:
        log_data: Raw log entry

    Returns:
        Formatted log entry
    """
    return {
        "timestamp": log_data.get("timestamp"),
        "level": log_data.get("level", log_data.get("severity", "INFO")),
        "message": log_data.get("message"),
        "type": log_data.get("type", log_data.get("job_type")),
        "context": log_data.get("context", {}),
        "error": log_data.get("error"),
    }


def format_health_check(health_data: dict) -> dict:
    """
    Format health check response.

    Args:
        health_data: Raw health check data

    Returns:
        Formatted health status
    """
    return {
        "overall_status": health_data.get("status", health_data.get("overall_status")),
        "api_server": health_data.get("api_server", "running"),
        "database": health_data.get("database", "unknown"),
        "redis": health_data.get("redis", "unknown"),
        "celery_workers": health_data.get("celery_workers", {}),
        "endpoint_checks": health_data.get("endpoint_checks", []),
        "issues": health_data.get("issues", []),
        "timestamp": datetime.now().isoformat(),
    }


def format_percentage(value: float, decimals: int = 1) -> str:
    """
    Format percentage value.

    Args:
        value: Percentage value (0-100 or 0-1)
        decimals: Number of decimal places

    Returns:
        Formatted percentage string

    Example:
        >>> format_percentage(0.856)
        '85.6%'
        >>> format_percentage(95.6)
        '95.6%'
    """
    # Detect if value is 0-1 or 0-100
    if value <= 1:
        value = value * 100

    return f"{value:.{decimals}f}%"


def format_currency(amount: float, currency: str = "GBP") -> str:
    """
    Format currency amount.

    Args:
        amount: Amount value
        currency: Currency code

    Returns:
        Formatted currency string

    Example:
        >>> format_currency(1234.56)
        '£1,234.56'
        >>> format_currency(1234.56, 'USD')
        '$1,234.56'
    """
    symbols = {"GBP": "£", "USD": "$", "EUR": "€"}

    symbol = symbols.get(currency, currency)
    formatted_amount = f"{amount:,.2f}"

    return f"{symbol}{formatted_amount}"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to max length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix
