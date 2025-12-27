"""
Input Validation

Validation functions for MCP tool parameters.

All validators raise ValueError with clear error messages on invalid input.
"""

from datetime import datetime


class ValidationError(ValueError):
    """Custom exception for validation errors with structured data."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        provided_value: any | None = None,
        expected: str | None = None,
    ):
        self.message = message
        self.field = field
        self.provided_value = provided_value
        self.expected = expected
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert error to dict for MCP error responses."""
        result = {"error": "validation_error", "message": self.message}

        if self.field:
            result["field"] = self.field

        if self.provided_value is not None:
            result["provided"] = str(self.provided_value)

        if self.expected:
            result["expected"] = self.expected

        return result


def validate_user_id(user_id: int):
    """
    Validate user ID.

    Args:
        user_id: User ID to validate

    Raises:
        ValidationError: If user_id is invalid
    """
    if not isinstance(user_id, int):
        raise ValidationError(
            message="user_id must be an integer",
            field="user_id",
            provided_value=user_id,
            expected="integer",
        )

    if user_id <= 0:
        raise ValidationError(
            message="user_id must be positive",
            field="user_id",
            provided_value=user_id,
            expected="positive integer",
        )


def validate_date_string(date_str: str, field_name: str = "date"):
    """
    Validate ISO date string (YYYY-MM-DD).

    Args:
        date_str: Date string to validate
        field_name: Name of the field (for error messages)

    Raises:
        ValidationError: If date_str is invalid
    """
    if not isinstance(date_str, str):
        raise ValidationError(
            message=f"{field_name} must be a string",
            field=field_name,
            provided_value=date_str,
            expected="string in ISO format (YYYY-MM-DD)",
        )

    try:
        datetime.fromisoformat(date_str)
    except ValueError:
        raise ValidationError(
            message=f"{field_name} must be valid ISO date (YYYY-MM-DD)",
            field=field_name,
            provided_value=date_str,
            expected="ISO format (YYYY-MM-DD)",
        )


def validate_date_range(date_from: str, date_to: str):
    """
    Validate date range (from < to).

    Args:
        date_from: Start date (ISO format)
        date_to: End date (ISO format)

    Raises:
        ValidationError: If date range is invalid
    """
    # Validate individual dates
    validate_date_string(date_from, "date_from")
    validate_date_string(date_to, "date_to")

    # Check from < to
    from_date = datetime.fromisoformat(date_from)
    to_date = datetime.fromisoformat(date_to)

    if from_date >= to_date:
        raise ValidationError(
            message="date_from must be before date_to",
            provided_value={"date_from": date_from, "date_to": date_to},
            expected="date_from < date_to",
        )


def validate_batch_size(batch_size: int):
    """
    Validate batch size for LLM enrichment.

    Args:
        batch_size: Batch size to validate

    Raises:
        ValidationError: If batch_size is invalid
    """
    if not isinstance(batch_size, int):
        raise ValidationError(
            message="batch_size must be an integer",
            field="batch_size",
            provided_value=batch_size,
            expected="integer",
        )

    if batch_size <= 0:
        raise ValidationError(
            message="batch_size must be positive",
            field="batch_size",
            provided_value=batch_size,
            expected="positive integer",
        )

    if batch_size > 100:
        raise ValidationError(
            message="batch_size must be <= 100",
            field="batch_size",
            provided_value=batch_size,
            expected="integer <= 100",
        )


def validate_sync_type(sync_type: str):
    """
    Validate Gmail sync type.

    Args:
        sync_type: Sync type to validate

    Raises:
        ValidationError: If sync_type is invalid
    """
    valid_types = ["full", "incremental", "auto"]

    if sync_type not in valid_types:
        raise ValidationError(
            message=f"sync_type must be one of: {valid_types}",
            field="sync_type",
            provided_value=sync_type,
            expected=f"one of {valid_types}",
        )


def validate_provider(provider: str):
    """
    Validate LLM provider name.

    Args:
        provider: Provider name to validate

    Raises:
        ValidationError: If provider is invalid
    """
    valid_providers = ["anthropic", "openai", "google", "deepseek", "ollama"]

    if provider not in valid_providers:
        raise ValidationError(
            message=f"provider must be one of: {valid_providers}",
            field="provider",
            provided_value=provider,
            expected=f"one of {valid_providers}",
        )


def validate_source_list(sources: list[str]):
    """
    Validate list of enrichment sources.

    Args:
        sources: List of source names

    Raises:
        ValidationError: If sources list is invalid
    """
    if not isinstance(sources, list):
        raise ValidationError(
            message="sources must be a list",
            field="sources",
            provided_value=sources,
            expected="list of strings",
        )

    valid_sources = ["amazon", "apple", "gmail"]

    for source in sources:
        if source not in valid_sources:
            raise ValidationError(
                message=f"Invalid source: {source}. Must be one of: {valid_sources}",
                field="sources",
                provided_value=source,
                expected=f"one of {valid_sources}",
            )


def validate_job_type(job_type: str):
    """
    Validate async job type.

    Args:
        job_type: Job type to validate

    Raises:
        ValidationError: If job_type is invalid
    """
    valid_types = ["gmail_sync", "matching", "enrichment"]

    if job_type not in valid_types:
        raise ValidationError(
            message=f"job_type must be one of: {valid_types}",
            field="job_type",
            provided_value=job_type,
            expected=f"one of {valid_types}",
        )


def validate_timeout(timeout: int):
    """
    Validate timeout value (seconds).

    Args:
        timeout: Timeout in seconds

    Raises:
        ValidationError: If timeout is invalid
    """
    if not isinstance(timeout, int):
        raise ValidationError(
            message="timeout must be an integer",
            field="timeout",
            provided_value=timeout,
            expected="integer (seconds)",
        )

    if timeout <= 0:
        raise ValidationError(
            message="timeout must be positive",
            field="timeout",
            provided_value=timeout,
            expected="positive integer (seconds)",
        )

    if timeout > 3600:  # 1 hour max
        raise ValidationError(
            message="timeout must be <= 3600 seconds (1 hour)",
            field="timeout",
            provided_value=timeout,
            expected="integer <= 3600",
        )


def validate_amount(amount: float, field_name: str = "amount"):
    """
    Validate transaction amount.

    Args:
        amount: Amount to validate
        field_name: Name of the field (for error messages)

    Raises:
        ValidationError: If amount is invalid
    """
    if not isinstance(amount, (int, float)):
        raise ValidationError(
            message=f"{field_name} must be a number",
            field=field_name,
            provided_value=amount,
            expected="number",
        )

    if amount < 0:
        raise ValidationError(
            message=f"{field_name} must be non-negative",
            field=field_name,
            provided_value=amount,
            expected="non-negative number",
        )


def validate_limit_offset(limit: int, offset: int):
    """
    Validate pagination parameters.

    Args:
        limit: Max items to return
        offset: Number of items to skip

    Raises:
        ValidationError: If pagination parameters are invalid
    """
    if not isinstance(limit, int):
        raise ValidationError(
            message="limit must be an integer",
            field="limit",
            provided_value=limit,
            expected="integer",
        )

    if limit <= 0:
        raise ValidationError(
            message="limit must be positive",
            field="limit",
            provided_value=limit,
            expected="positive integer",
        )

    if limit > 1000:
        raise ValidationError(
            message="limit must be <= 1000",
            field="limit",
            provided_value=limit,
            expected="integer <= 1000",
        )

    if not isinstance(offset, int):
        raise ValidationError(
            message="offset must be an integer",
            field="offset",
            provided_value=offset,
            expected="integer",
        )

    if offset < 0:
        raise ValidationError(
            message="offset must be non-negative",
            field="offset",
            provided_value=offset,
            expected="non-negative integer",
        )
