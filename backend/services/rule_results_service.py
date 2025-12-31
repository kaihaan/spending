"""
Rule Results Service - Business Logic

Orchestrates rule results viewing and conflict resolution:
- Paginated rule-enriched transaction queries
- Conflict detection and analysis
- Conflict resolution (per-transaction override or priority adjustment)
- Statistics and coverage metrics

Separates business logic from HTTP routing concerns.
"""

from datetime import UTC, datetime

import cache_manager

from database import categories, enrichment, matching, truelayer

# ============================================================================
# Rule Results Queries
# ============================================================================


def get_rule_enriched_transactions(
    page: int = 1,
    page_size: int = 50,
    rule_type: str | None = None,
    category: str | None = None,
    has_conflict: bool | None = None,
) -> dict:
    """
    Get paginated list of rule-enriched transactions.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        rule_type: Filter by 'category_rule', 'merchant_rule', 'direct_debit'
        category: Filter by primary category
        has_conflict: Filter to only transactions with conflicts

    Returns:
        Dict with transactions, pagination info
    """
    # If filtering by conflicts, get conflict transaction IDs first
    conflict_ids = None
    if has_conflict:
        conflict_ids = _get_conflict_transaction_ids()
        if not conflict_ids:
            # No conflicts found, return empty result
            return {
                "transactions": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

    # Get all rule-enriched transactions with their enrichment data
    transactions = enrichment.get_rule_enriched_transactions_paginated(
        page=page,
        page_size=page_size,
        rule_type=rule_type,
        category=category,
        transaction_ids=conflict_ids,
    )

    # Format response
    formatted = []
    for txn in transactions["items"]:
        # Check for conflicts if not already filtering by them
        txn_has_conflict = (
            has_conflict  # If filtering by conflicts, all results are conflicts
        )
        conflict_count = 0

        if not has_conflict:
            # Check this transaction for conflicts
            description = txn.get("description", "")
            if description:
                matching_rules = _find_all_matching_rules(description)
                txn_has_conflict = len(matching_rules) > 1
                conflict_count = len(matching_rules) if txn_has_conflict else 0
        else:
            # Already filtering by conflicts, get the count
            description = txn.get("description", "")
            if description:
                matching_rules = _find_all_matching_rules(description)
                conflict_count = len(matching_rules)

        formatted.append(
            {
                "id": txn["id"],
                "description": txn["description"],
                "amount": float(txn["amount"]) if txn.get("amount") else 0,
                "timestamp": txn["timestamp"].isoformat()
                if hasattr(txn.get("timestamp"), "isoformat")
                else txn.get("timestamp"),
                "rule_enrichment": {
                    "primary_category": txn.get("primary_category"),
                    "subcategory": txn.get("subcategory"),
                    "essential_discretionary": txn.get("essential_discretionary"),
                    "rule_type": txn.get("rule_type"),
                    "matched_rule_id": txn.get("matched_rule_id"),
                    "matched_rule_name": txn.get("matched_rule_name"),
                    "matched_merchant_id": txn.get("matched_merchant_id"),
                    "matched_merchant_name": txn.get("matched_merchant_name"),
                    "merchant_clean_name": txn.get("merchant_clean_name"),
                    "confidence_score": float(txn.get("confidence_score", 1.0)),
                },
                "has_conflict": txn_has_conflict,
                "conflicting_rules_count": conflict_count,
                "conflict_resolved": txn.get("conflict_resolved", False),
            }
        )

    return {
        "transactions": formatted,
        "total": transactions["total"],
        "page": page,
        "page_size": page_size,
        "total_pages": (transactions["total"] + page_size - 1) // page_size,
    }


def get_transaction_with_matching_rules(transaction_id: int) -> dict | None:
    """
    Get a transaction with all rules that could match it.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Transaction details with all matching rules, or None if not found
    """
    # Get transaction by database primary key (not provider ID)
    txn = truelayer.get_truelayer_transaction_by_pk(transaction_id)
    if not txn:
        return None

    # Get current rule enrichment
    current_enrichment = enrichment.get_rule_enrichment(transaction_id)

    # Get all matching rules for this transaction's description
    matching_rules = _find_all_matching_rules(txn.get("description", ""))

    # Mark the winning rule
    for rule in matching_rules:
        rule["is_winner"] = (
            current_enrichment
            and rule["id"] == current_enrichment.get("matched_rule_id")
            and rule["type"] == current_enrichment.get("rule_type")
        )

    return {
        "transaction": {
            "id": txn["id"],
            "description": txn.get("description"),
            "amount": float(txn.get("amount", 0)),
            "timestamp": txn.get("timestamp").isoformat()
            if hasattr(txn.get("timestamp"), "isoformat")
            else txn.get("timestamp"),
            "transaction_type": txn.get("transaction_type"),
        },
        "applied_rule": current_enrichment,
        "all_matching_rules": matching_rules,
        "has_conflict": len(matching_rules) > 1,
    }


# ============================================================================
# Conflict Analysis
# ============================================================================


def analyze_rule_conflicts() -> dict:
    """
    Analyze all rules for conflicts.

    Evaluates all active rules against all transactions to find
    where multiple rules could match the same transaction.

    Returns:
        Conflict analysis results
    """
    # Use existing test_all_rules function which already detects conflicts
    analysis = categories.test_all_rules()

    # Get more detailed conflict info
    conflicts = []
    for conflict in analysis.get("sample_conflicts", []):
        txn_id = conflict.get("transaction_id")
        txn = truelayer.get_truelayer_transaction_by_pk(txn_id)

        if txn:
            matching_rules = []
            for rule_info in conflict.get("matching_rules", []):
                matching_rules.append(
                    {
                        "id": rule_info.get("id"),
                        "type": rule_info.get("type", "category_rule"),
                        "name": rule_info.get("name"),
                        "category": rule_info.get("category"),
                        "priority": rule_info.get("priority", 0),
                    }
                )

            # Determine winning rule (highest priority)
            winning_rule = max(matching_rules, key=lambda r: r.get("priority", 0))

            conflicts.append(
                {
                    "transaction_id": txn_id,
                    "description": txn.get("description"),
                    "amount": float(txn.get("amount", 0)),
                    "matching_rules": matching_rules,
                    "winning_rule": winning_rule,
                }
            )

    return {
        "total_transactions": analysis.get("total_transactions", 0),
        "rule_enriched_count": analysis.get("rules_applied_count", 0),
        "conflicts_count": analysis.get("potential_conflicts_count", 0),
        "conflicts": conflicts,
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


# ============================================================================
# Conflict Resolution
# ============================================================================


def resolve_conflict(
    transaction_id: int,
    winning_rule_id: int,
    winning_rule_type: str,
    resolution_type: str,
    apply_to_similar: bool = False,
) -> dict:
    """
    Resolve a rule conflict for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID
        winning_rule_id: ID of the rule that should win
        winning_rule_type: 'category_rule' or 'merchant_rule'
        resolution_type: 'override_transaction' or 'adjust_priority'
        apply_to_similar: Apply resolution to similar transactions

    Returns:
        Resolution result

    Raises:
        ValueError: If transaction or rule not found
    """
    # Get the transaction
    txn = truelayer.get_truelayer_transaction_by_pk(transaction_id)
    if not txn:
        raise ValueError(f"Transaction {transaction_id} not found")

    # Get the winning rule
    if winning_rule_type == "category_rule":
        all_rules = matching.get_category_rules(active_only=False)
        rule = next((r for r in all_rules if r["id"] == winning_rule_id), None)
    else:
        all_rules = matching.get_merchant_normalizations()
        rule = next((r for r in all_rules if r["id"] == winning_rule_id), None)

    if not rule:
        raise ValueError(f"Rule {winning_rule_id} ({winning_rule_type}) not found")

    transactions_updated = 0
    priority_adjusted = False

    if resolution_type == "override_transaction":
        # Apply this rule's enrichment to the transaction (mark as resolved)
        _apply_rule_to_transaction(txn, rule, winning_rule_type, conflict_resolved=True)
        transactions_updated = 1

        # Optionally apply to similar transactions
        if apply_to_similar:
            similar_txns = _find_similar_transactions(
                txn["description"], rule=rule, rule_type=winning_rule_type
            )
            for similar_txn in similar_txns:
                if similar_txn["id"] != transaction_id:
                    _apply_rule_to_transaction(
                        similar_txn, rule, winning_rule_type, conflict_resolved=True
                    )
                    transactions_updated += 1

    elif resolution_type == "adjust_priority":
        # Find all matching rules and set winning rule's priority higher
        matching_rules = _find_all_matching_rules(txn["description"])
        max_priority = max(r.get("priority", 0) for r in matching_rules)

        # Set winning rule priority to max + 1
        new_priority = max_priority + 1
        if winning_rule_type == "category_rule":
            matching.update_category_rule(winning_rule_id, priority=new_priority)
        else:
            matching.update_merchant_normalization(
                winning_rule_id, priority=new_priority
            )

        priority_adjusted = True

        # Re-apply rules to this transaction (and similar if requested) - mark as resolved
        _apply_rule_to_transaction(txn, rule, winning_rule_type, conflict_resolved=True)
        transactions_updated = 1

        if apply_to_similar:
            similar_txns = _find_similar_transactions(
                txn["description"], rule=rule, rule_type=winning_rule_type
            )
            for similar_txn in similar_txns:
                if similar_txn["id"] != transaction_id:
                    _apply_rule_to_transaction(
                        similar_txn, rule, winning_rule_type, conflict_resolved=True
                    )
                    transactions_updated += 1

    # Invalidate transaction cache
    cache_manager.cache_invalidate_transactions()

    return {
        "success": True,
        "transaction_id": transaction_id,
        "winning_rule": {
            "id": winning_rule_id,
            "type": winning_rule_type,
            "name": rule.get("rule_name") or rule.get("normalized_name"),
        },
        "resolution_type": resolution_type,
        "transactions_updated": transactions_updated,
        "priority_adjusted": priority_adjusted,
    }


# ============================================================================
# Statistics
# ============================================================================


def get_statistics() -> dict:
    """
    Get statistics about rule-enriched transactions.

    Returns:
        Statistics dict
    """
    return enrichment.get_rule_enrichment_statistics()


def delete_enrichments_by_rule(rule_id: int, rule_type: str) -> dict:
    """
    Delete all enrichments from a specific rule.

    Used when disabling a rule to clear its effects.

    Args:
        rule_id: ID of the rule
        rule_type: 'category_rule' or 'merchant_rule'

    Returns:
        Dict with deleted count
    """
    if rule_type not in ["category_rule", "merchant_rule"]:
        raise ValueError("rule_type must be 'category_rule' or 'merchant_rule'")

    deleted_count = enrichment.delete_rule_enrichment_by_rule(rule_id, rule_type)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "rule_id": rule_id,
        "rule_type": rule_type,
    }


def clear_all_rule_enrichments() -> dict:
    """
    Clear all rule enrichment results.

    Used before re-applying all rules from scratch.

    Returns:
        Dict with deleted count
    """
    deleted_count = enrichment.clear_all_rule_enrichments()

    return {
        "success": True,
        "deleted_count": deleted_count,
    }


# ============================================================================
# Helper Functions
# ============================================================================


def _find_all_matching_rules(description: str) -> list:
    """
    Find all rules (category and merchant) that would match a description.

    Args:
        description: Transaction description

    Returns:
        List of matching rules with type, id, name, category, priority
    """

    matching_rules = []
    description_upper = description.upper()

    # Check category rules
    category_rules = matching.get_category_rules(active_only=True)
    for rule in category_rules:
        pattern = rule.get("description_pattern", "")
        pattern_type = rule.get("pattern_type", "contains")

        if _pattern_matches(description_upper, pattern.upper(), pattern_type):
            matching_rules.append(
                {
                    "id": rule["id"],
                    "type": "category_rule",
                    "name": rule.get("rule_name"),
                    "category": rule.get("category"),
                    "subcategory": rule.get("subcategory"),
                    "priority": rule.get("priority", 0),
                    "pattern": pattern,
                    "pattern_type": pattern_type,
                }
            )

    # Check merchant normalization rules (only those with default_category)
    merchant_rules = matching.get_merchant_normalizations(active_only=True)
    for rule in merchant_rules:
        if not rule.get("default_category"):
            continue  # Skip merchant rules without category

        pattern = rule.get("pattern", "")
        pattern_type = rule.get("pattern_type", "contains")

        if _pattern_matches(description_upper, pattern.upper(), pattern_type):
            matching_rules.append(
                {
                    "id": rule["id"],
                    "type": "merchant_rule",
                    "name": rule.get("normalized_name"),
                    "category": rule.get("default_category"),
                    "subcategory": None,
                    "priority": rule.get("priority", 0),
                    "pattern": pattern,
                    "pattern_type": pattern_type,
                }
            )

    # Sort by priority descending
    matching_rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

    return matching_rules


def _pattern_matches(text: str, pattern: str, pattern_type: str) -> bool:
    """Check if text matches pattern based on pattern_type."""
    import re

    if pattern_type == "exact":
        return text == pattern
    if pattern_type == "starts_with":
        return text.startswith(pattern)
    if pattern_type == "regex":
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error:
            return False
    else:  # contains
        return pattern in text


def _find_similar_transactions(
    description: str,
    rule: dict | None = None,
    rule_type: str | None = None,
) -> list:
    """
    Find transactions with similar descriptions.

    If a rule is provided, finds all transactions that match the rule's pattern.
    Otherwise falls back to exact description match.

    Args:
        description: Transaction description (used as fallback)
        rule: The winning rule dict containing pattern info
        rule_type: 'category_rule' or 'merchant_rule'

    Returns:
        List of similar transactions
    """
    all_txns = truelayer.get_all_truelayer_transactions()

    # If no rule provided, fall back to exact match
    if not rule:
        return [t for t in all_txns if t.get("description") == description]

    # Get pattern info from rule based on type
    if rule_type == "category_rule":
        pattern = rule.get("description_pattern", "")
        pattern_type = rule.get("pattern_type", "contains")
    else:  # merchant_rule
        pattern = rule.get("pattern", "")
        pattern_type = rule.get("pattern_type", "contains")

    if not pattern:
        return [t for t in all_txns if t.get("description") == description]

    # Find all transactions matching the rule's pattern
    matching_txns = []
    for txn in all_txns:
        txn_desc = txn.get("description", "")
        if txn_desc and _pattern_matches(
            txn_desc.upper(), pattern.upper(), pattern_type
        ):
            matching_txns.append(txn)

    return matching_txns


def _apply_rule_to_transaction(
    txn: dict, rule: dict, rule_type: str, conflict_resolved: bool = False
) -> None:
    """
    Apply a rule's enrichment to a transaction.

    Args:
        txn: Transaction dict
        rule: Rule dict
        rule_type: 'category_rule' or 'merchant_rule'
        conflict_resolved: Whether this was set by conflict resolution
    """
    if rule_type == "category_rule":
        enrichment.save_rule_enrichment(
            transaction_id=txn["id"],
            primary_category=rule.get("category"),
            rule_type="category_rule",
            subcategory=rule.get("subcategory"),
            matched_rule_id=rule.get("id"),
            matched_rule_name=rule.get("rule_name"),
            conflict_resolved=conflict_resolved,
        )
    else:  # merchant_rule
        enrichment.save_rule_enrichment(
            transaction_id=txn["id"],
            primary_category=rule.get("default_category"),
            rule_type="merchant_rule",
            merchant_clean_name=rule.get("normalized_name"),
            merchant_type=rule.get("merchant_type"),
            matched_merchant_id=rule.get("id"),
            matched_merchant_name=rule.get("normalized_name"),
            conflict_resolved=conflict_resolved,
        )


def _get_conflict_transaction_ids() -> list[int]:
    """
    Get IDs of transactions that have rule conflicts.

    A conflict occurs when multiple rules match the same transaction description.

    Returns:
        List of transaction IDs with conflicts
    """
    # Get all rule-enriched transactions
    all_enriched = enrichment.get_rule_enriched_transactions_paginated(
        page=1,
        page_size=10000,  # Get all for conflict detection
    )

    conflict_ids = []

    # Check each transaction for multiple matching rules
    for txn in all_enriched.get("items", []):
        description = txn.get("description", "")
        if description:
            matching_rules = _find_all_matching_rules(description)
            if len(matching_rules) > 1:
                conflict_ids.append(txn["id"])

    return conflict_ids
