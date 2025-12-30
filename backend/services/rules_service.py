"""
Rules Service - Business Logic

Orchestrates rule-based categorization and merchant normalization:
- Category rules: Pattern-based transaction categorization
- Merchant rules: Merchant name normalization and default categories
- Pattern validation and testing
- Bulk operations and statistics

Supports pattern types: contains, starts_with, exact, regex

Separates business logic from HTTP routing concerns.
"""

import cache_manager

from database import categories, matching
from mcp.pattern_utils import parse_pattern_with_prefix, validate_pattern

# ============================================================================
# Category Rules
# ============================================================================


def get_category_rules(
    active_only: bool = True, category: str = None, source: str = None
) -> list:
    """
    Get all category rules with optional filtering.

    Args:
        active_only: Filter to active rules only (default: True)
        category: Filter by category
        source: Filter by source ('manual', 'learned', 'llm')

    Returns:
        List of category rule dicts
    """
    rules = matching.get_category_rules(active_only=active_only)

    # Apply filters
    if category:
        rules = [r for r in rules if r.get("category") == category]
    if source:
        rules = [r for r in rules if r.get("source") == source]

    return rules


def create_category_rule(
    rule_name: str,
    description_pattern: str,
    category: str,
    pattern_type: str = None,
    transaction_type: str = None,
    subcategory: str = None,
    priority: int = 0,
    source: str = "manual",
) -> dict:
    """
    Create a new category rule.

    Args:
        rule_name: Human-readable name
        description_pattern: Pattern to match
        category: Target category
        pattern_type: 'contains', 'starts_with', 'exact', 'regex' (auto-detect if None)
        transaction_type: 'CREDIT', 'DEBIT', or None for all
        subcategory: Optional subcategory
        priority: Integer priority (default: 0)
        source: Rule source (default: 'manual')

    Returns:
        Created rule dict with ID

    Raises:
        ValueError: If pattern validation fails
    """
    # Parse pattern if it has a prefix
    pattern = description_pattern
    if not pattern_type:
        pattern, pattern_type = parse_pattern_with_prefix(pattern)

    # Validate pattern
    is_valid, error_msg = validate_pattern(pattern, pattern_type)
    if not is_valid:
        raise ValueError(error_msg)

    rule_id = matching.add_category_rule(
        rule_name=rule_name,
        description_pattern=pattern,
        category=category,
        transaction_type=transaction_type,
        subcategory=subcategory,
        pattern_type=pattern_type,
        priority=priority,
        source=source,
    )

    return {"success": True, "id": rule_id, "message": f"Created rule '{rule_name}'"}


def update_category_rule(rule_id: int, **updates) -> bool:
    """
    Update an existing category rule.

    Args:
        rule_id: Rule ID to update
        **updates: Fields to update (rule_name, description_pattern, category, etc.)

    Returns:
        True if updated, False if not found

    Raises:
        ValueError: If pattern validation fails
    """
    # Handle pattern prefix if provided
    if "description_pattern" in updates:
        pattern = updates["description_pattern"]
        pattern_type = updates.get("pattern_type")

        if not pattern_type:
            pattern, pattern_type = parse_pattern_with_prefix(pattern)
            updates["description_pattern"] = pattern
            updates["pattern_type"] = pattern_type

        # Validate pattern
        is_valid, error_msg = validate_pattern(
            updates["description_pattern"], updates.get("pattern_type", "contains")
        )
        if not is_valid:
            raise ValueError(error_msg)

    return matching.update_category_rule(rule_id, **updates)


def delete_category_rule(rule_id: int) -> bool:
    """
    Delete a category rule.

    Args:
        rule_id: Rule ID to delete

    Returns:
        True if deleted, False if not found
    """
    return matching.delete_category_rule(rule_id)


def test_category_rule(rule_id: int, limit: int = 10) -> dict:
    """
    Test an existing category rule against all transactions.

    Args:
        rule_id: Rule ID to test
        limit: Max transactions to return

    Returns:
        Test results with matching transactions

    Raises:
        ValueError: If rule not found
    """
    # Get the rule
    rules = matching.get_category_rules(active_only=False)
    rule = next((r for r in rules if r["id"] == rule_id), None)

    if not rule:
        raise ValueError("Rule not found")

    return matching.test_rule_pattern(
        rule["description_pattern"], rule["pattern_type"], limit=limit
    )


def test_pattern(pattern: str, pattern_type: str = None, limit: int = 10) -> dict:
    """
    Test a pattern against transactions before creating a rule.

    Args:
        pattern: The pattern to test
        pattern_type: 'contains', 'starts_with', 'exact', 'regex' (auto-detect if None)
        limit: Max transactions to return

    Returns:
        Test results with matching transactions

    Raises:
        ValueError: If pattern validation fails
    """
    # Parse pattern if it has a prefix
    if not pattern_type:
        pattern, pattern_type = parse_pattern_with_prefix(pattern)

    # Validate pattern
    is_valid, error_msg = validate_pattern(pattern, pattern_type)
    if not is_valid:
        raise ValueError(error_msg)

    return matching.test_rule_pattern(pattern, pattern_type, limit=limit)


# ============================================================================
# Merchant Normalization Rules
# ============================================================================


def get_merchant_rules(source: str = None, category: str = None) -> list:
    """
    Get all merchant normalizations with optional filtering.

    Args:
        source: Filter by source ('manual', 'learned', 'llm', 'direct_debit')
        category: Filter by default_category

    Returns:
        List of merchant normalization rule dicts
    """
    normalizations = matching.get_merchant_normalizations()

    # Apply filters
    if source:
        normalizations = [n for n in normalizations if n.get("source") == source]
    if category:
        normalizations = [
            n for n in normalizations if n.get("default_category") == category
        ]

    return normalizations


def create_merchant_rule(
    pattern: str,
    normalized_name: str,
    pattern_type: str = None,
    merchant_type: str = None,
    default_category: str = None,
    priority: int = 0,
    source: str = "manual",
) -> dict:
    """
    Create a new merchant normalization rule.

    Args:
        pattern: Pattern to match
        normalized_name: Clean merchant name
        pattern_type: 'contains', 'starts_with', 'exact', 'regex' (auto-detect if None)
        merchant_type: Business type (optional)
        default_category: Category to assign (optional)
        priority: Integer priority (default: 0)
        source: Rule source (default: 'manual')

    Returns:
        Created normalization dict with ID

    Raises:
        ValueError: If pattern validation fails
    """
    # Parse pattern if it has a prefix
    if not pattern_type:
        pattern, pattern_type = parse_pattern_with_prefix(pattern)

    # Validate pattern
    is_valid, error_msg = validate_pattern(pattern, pattern_type)
    if not is_valid:
        raise ValueError(error_msg)

    norm_id = matching.add_merchant_normalization(
        pattern=pattern,
        normalized_name=normalized_name,
        merchant_type=merchant_type,
        default_category=default_category,
        pattern_type=pattern_type,
        priority=priority,
        source=source,
    )

    return {
        "success": True,
        "id": norm_id,
        "message": f"Created merchant normalization for '{pattern}'",
    }


def update_merchant_rule(norm_id: int, **updates) -> bool:
    """
    Update an existing merchant normalization rule.

    Args:
        norm_id: Normalization ID to update
        **updates: Fields to update (pattern, normalized_name, etc.)

    Returns:
        True if updated, False if not found

    Raises:
        ValueError: If pattern validation fails
    """
    # Handle pattern prefix if provided
    if "pattern" in updates:
        pattern = updates["pattern"]
        pattern_type = updates.get("pattern_type")

        if not pattern_type:
            pattern, pattern_type = parse_pattern_with_prefix(pattern)
            updates["pattern"] = pattern
            updates["pattern_type"] = pattern_type

        # Validate pattern
        is_valid, error_msg = validate_pattern(
            updates["pattern"], updates.get("pattern_type", "contains")
        )
        if not is_valid:
            raise ValueError(error_msg)

    return matching.update_merchant_normalization(norm_id, **updates)


def delete_merchant_rule(norm_id: int) -> bool:
    """
    Delete a merchant normalization rule.

    Args:
        norm_id: Normalization ID to delete

    Returns:
        True if deleted, False if not found
    """
    return matching.delete_merchant_normalization(norm_id)


def test_merchant_rule(norm_id: int, limit: int = 10) -> dict:
    """
    Test an existing merchant normalization against all transactions.

    Args:
        norm_id: Normalization ID to test
        limit: Max transactions to return

    Returns:
        Test results with matching transactions

    Raises:
        ValueError: If normalization not found
    """
    normalizations = matching.get_merchant_normalizations()
    norm = next((n for n in normalizations if n["id"] == norm_id), None)

    if not norm:
        raise ValueError("Normalization not found")

    return matching.test_rule_pattern(
        norm["pattern"], norm["pattern_type"], limit=limit
    )


# ============================================================================
# Bulk Operations
# ============================================================================


def get_statistics() -> dict:
    """
    Get comprehensive rule usage statistics and coverage metrics.

    Returns:
        Statistics dict with rule counts and coverage
    """
    return categories.get_rules_statistics()


def test_all_rules() -> dict:
    """
    Evaluate all rules against all transactions.

    Returns detailed coverage report with category breakdown,
    unused rules, and potential conflicts.

    Returns:
        Test results dict with coverage analysis
    """
    return categories.test_all_rules()


def apply_all_rules() -> dict:
    """
    Re-apply all rules to all transactions.

    This re-enriches all transactions using the current rules,
    updating any transactions that match.

    Returns:
        Application results with update counts
    """
    result = categories.apply_all_rules_to_transactions()

    # Invalidate transaction cache
    cache_manager.cache_invalidate_transactions()

    return {
        "success": True,
        "updated_count": result["updated_count"],
        "total_transactions": result["total_transactions"],
        "rule_hits": result["rule_hits"],
        "message": f"Updated {result['updated_count']} of {result['total_transactions']} transactions",
    }
