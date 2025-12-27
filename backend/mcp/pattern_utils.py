"""
Pattern Utilities for Rule-Based Enrichment

Handles parsing of explicit prefix pattern syntax and validation.
Supports: starts:, contains:, exact:, regex: prefixes
"""

import re


def parse_pattern_with_prefix(pattern: str) -> tuple[str, str]:
    """
    Parse explicit prefix pattern syntax.

    Supported prefixes:
        - starts:PATTERN   → ("PATTERN", "starts_with")
        - contains:PATTERN → ("PATTERN", "contains")
        - exact:PATTERN    → ("PATTERN", "exact")
        - regex:PATTERN    → ("PATTERN", "regex")
        - PATTERN          → ("PATTERN", "contains")  # default

    Args:
        pattern: Pattern string with optional prefix

    Returns:
        Tuple of (cleaned_pattern, pattern_type)

    Examples:
        >>> parse_pattern_with_prefix("starts:AMAZON")
        ("AMAZON", "starts_with")
        >>> parse_pattern_with_prefix("contains:COFFEE")
        ("COFFEE", "contains")
        >>> parse_pattern_with_prefix("exact:TESCO")
        ("TESCO", "exact")
        >>> parse_pattern_with_prefix("regex:^AMZN.*")
        ("^AMZN.*", "regex")
        >>> parse_pattern_with_prefix("UBER")
        ("UBER", "contains")
    """
    if not pattern:
        return ("", "contains")

    pattern = pattern.strip()

    # Check for explicit prefixes
    prefix_map = {
        "starts:": "starts_with",
        "contains:": "contains",
        "exact:": "exact",
        "regex:": "regex",
    }

    for prefix, pattern_type in prefix_map.items():
        if pattern.lower().startswith(prefix):
            cleaned = pattern[len(prefix) :].strip()
            return (cleaned, pattern_type)

    # Default to contains
    return (pattern, "contains")


def format_pattern_with_prefix(pattern: str, pattern_type: str) -> str:
    """
    Convert pattern and type back to prefix syntax for display.

    Args:
        pattern: The raw pattern
        pattern_type: The pattern type (contains, starts_with, exact, regex)

    Returns:
        Pattern with prefix for display

    Examples:
        >>> format_pattern_with_prefix("AMAZON", "starts_with")
        "starts:AMAZON"
        >>> format_pattern_with_prefix("COFFEE", "contains")
        "contains:COFFEE"
    """
    if not pattern:
        return ""

    type_prefix_map = {
        "starts_with": "starts:",
        "contains": "contains:",
        "exact": "exact:",
        "regex": "regex:",
    }

    prefix = type_prefix_map.get(pattern_type, "contains:")
    return f"{prefix}{pattern}"


def validate_pattern(pattern: str, pattern_type: str) -> tuple[bool, str | None]:
    """
    Validate a pattern for the given pattern type.

    Args:
        pattern: The pattern to validate
        pattern_type: The type of pattern (contains, starts_with, exact, regex)

    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid

    Examples:
        >>> validate_pattern("TESCO", "contains")
        (True, None)
        >>> validate_pattern("", "contains")
        (False, "Pattern cannot be empty")
        >>> validate_pattern("[invalid", "regex")
        (False, "Invalid regex pattern: ...")
    """
    if not pattern or not pattern.strip():
        return (False, "Pattern cannot be empty")

    pattern = pattern.strip()

    # Check pattern length
    if len(pattern) > 255:
        return (False, "Pattern cannot exceed 255 characters")

    # For regex patterns, validate the regex syntax
    if pattern_type == "regex":
        try:
            re.compile(pattern)
        except re.error as e:
            return (False, f"Invalid regex pattern: {str(e)}")

    # For other patterns, check for problematic characters
    if pattern_type in ("contains", "starts_with", "exact"):
        # These patterns are matched literally, so most characters are fine
        # Just warn about potential issues
        pass

    return (True, None)


def test_pattern_match(description: str, pattern: str, pattern_type: str) -> bool:
    """
    Test if a transaction description matches a pattern.

    This mirrors the logic in consistency_engine.py for consistency.

    Args:
        description: The transaction description to test
        pattern: The pattern to match
        pattern_type: The type of pattern

    Returns:
        True if the description matches the pattern
    """
    if not description or not pattern:
        return False

    description_upper = description.upper()
    pattern_upper = pattern.upper()

    if pattern_type == "contains":
        return pattern_upper in description_upper
    if pattern_type == "starts_with":
        return description_upper.startswith(pattern_upper)
    if pattern_type == "exact":
        return description_upper == pattern_upper
    if pattern_type == "regex":
        try:
            return bool(re.search(pattern, description, re.IGNORECASE))
        except re.error:
            return False

    return False


def get_pattern_help_text() -> str:
    """
    Return help text explaining the pattern syntax.
    """
    return """
Pattern Syntax:
  starts:PATTERN   - Matches descriptions starting with PATTERN
  contains:PATTERN - Matches descriptions containing PATTERN (default)
  exact:PATTERN    - Matches descriptions exactly equal to PATTERN
  regex:PATTERN    - Uses regex pattern matching (advanced)

Examples:
  starts:AMAZON    → Matches "AMAZON PRIME", "AMAZON.CO.UK"
  contains:COFFEE  → Matches "COSTA COFFEE", "STARBUCKS COFFEE BAR"
  exact:SALARY     → Matches only "SALARY", not "SALARY PAYMENT"
  regex:^AMZN.*    → Matches "AMZN MKTP", "AMZN DIGITAL"

Note: Patterns are case-insensitive.
""".strip()
