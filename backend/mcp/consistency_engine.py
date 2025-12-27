"""
Consistency Engine for Transaction Categorization
Applies rules before LLM enrichment to ensure consistent categorization.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def match_category_rule(
    description: str, transaction_type: str, rules: list[dict]
) -> dict | None:
    """
    Check if a transaction matches any category rule.

    Args:
        description: Transaction description
        transaction_type: 'CREDIT' or 'DEBIT'
        rules: List of rule dictionaries from database

    Returns:
        Matching rule dict or None
    """
    description_upper = description.upper()

    for rule in rules:
        # Check transaction type filter
        rule_type = rule.get("transaction_type")
        if rule_type and rule_type != transaction_type:
            continue

        # Check if rule is active
        if not rule.get("is_active", True):
            continue

        pattern = rule.get("description_pattern", "").upper()
        pattern_type = rule.get("pattern_type", "contains")

        matched = False

        if pattern_type == "contains":
            matched = pattern in description_upper
        elif pattern_type == "starts_with":
            matched = description_upper.startswith(pattern)
        elif pattern_type == "exact":
            matched = description_upper == pattern
        elif pattern_type == "regex":
            try:
                matched = bool(re.search(pattern, description_upper, re.IGNORECASE))
            except re.error:
                logger.warning(
                    f"Invalid regex pattern in rule {rule.get('id')}: {pattern}"
                )
                continue

        if matched:
            logger.debug(
                f"Category rule matched: {rule.get('rule_name')} for '{description[:50]}...'"
            )
            return rule

    return None


def match_merchant_normalization(
    description: str, normalizations: list[dict]
) -> dict | None:
    """
    Check if a transaction matches any merchant normalization pattern.

    Args:
        description: Transaction description
        normalizations: List of normalization dictionaries from database

    Returns:
        Matching normalization dict or None
    """
    description_upper = description.upper()

    for norm in normalizations:
        pattern = norm.get("pattern", "").upper()
        pattern_type = norm.get("pattern_type", "contains")

        matched = False

        if pattern_type == "contains":
            matched = pattern in description_upper
        elif pattern_type == "starts_with":
            matched = description_upper.startswith(pattern)
        elif pattern_type == "exact":
            matched = description_upper == pattern
        elif pattern_type == "regex":
            try:
                matched = bool(re.search(pattern, description_upper, re.IGNORECASE))
            except re.error:
                logger.warning(
                    f"Invalid regex pattern in normalization {norm.get('id')}: {pattern}"
                )
                continue

        if matched:
            logger.debug(
                f"Merchant normalization matched: {norm.get('normalized_name')} for '{description[:50]}...'"
            )
            return norm

    return None


def _match_extracted_payee(payee: str, normalizations: list[dict]) -> dict | None:
    """
    Match an extracted payee against merchant normalizations.

    Used primarily for direct debit transactions where the payee is extracted
    from the description using pattern_extractor.

    Args:
        payee: Extracted payee name (e.g., "EMMANUEL COLL")
        normalizations: List of normalization dictionaries

    Returns:
        Matching normalization dict or None
    """
    if not payee:
        return None

    payee_upper = payee.upper().strip()

    for norm in normalizations:
        pattern = norm.get("pattern", "").upper()
        pattern_type = norm.get("pattern_type", "contains")

        matched = False

        if pattern_type == "exact":
            matched = payee_upper == pattern
        elif pattern_type == "contains":
            matched = pattern in payee_upper or payee_upper in pattern
        elif pattern_type == "starts_with":
            matched = payee_upper.startswith(pattern)
        elif pattern_type == "regex":
            try:
                matched = bool(re.search(pattern, payee_upper, re.IGNORECASE))
            except re.error:
                continue

        if matched:
            logger.debug(
                f"Payee '{payee}' matched normalization: {norm.get('normalized_name')}"
            )
            return norm

    return None


def apply_rules_to_transaction(
    transaction: dict[str, Any],
    category_rules: list[dict],
    merchant_normalizations: list[dict],
) -> dict[str, Any] | None:
    """
    Apply consistency rules to a transaction.

    Priority order:
    1. Extract payee using pattern_extractor, match against direct_debit source normalizations
    2. Match full description against category_rules
    3. Match full description against merchant_normalizations

    Args:
        transaction: Transaction dict with 'description' and 'transaction_type'
        category_rules: List of category rules (sorted by priority desc)
        merchant_normalizations: List of merchant normalizations (sorted by priority desc)

    Returns:
        Enrichment dict if rules matched, None if LLM should be used
    """
    description = transaction.get("description", "")
    transaction_type = transaction.get("transaction_type", "DEBIT")

    # Step 1: Try to extract structured data (payee) from description
    # This is especially useful for direct debits, transfers, etc.
    try:
        from mcp.pattern_extractor import extract_variables

        extracted = extract_variables(description)
        payee = extracted.get("payee")

        if payee:
            # Try to match extracted payee against direct_debit source normalizations first
            # These are user-configured mappings with higher priority
            direct_debit_norms = [
                n for n in merchant_normalizations if n.get("source") == "direct_debit"
            ]
            payee_match = _match_extracted_payee(payee, direct_debit_norms)

            if payee_match and payee_match.get("default_category"):
                # Full enrichment from direct debit mapping
                enrichment = {
                    "primary_category": payee_match.get("default_category"),
                    "subcategory": payee_match.get(
                        "normalized_name"
                    ),  # Use merchant as subcategory
                    "merchant_clean_name": payee_match.get("normalized_name"),
                    "merchant_type": payee_match.get("merchant_type"),
                    "essential_discretionary": _infer_essential_discretionary(
                        payee_match.get("default_category")
                    ),
                    "payment_method": extracted.get("provider"),  # e.g., "Direct Debit"
                    "payment_method_subtype": None,
                    "purchase_date": transaction.get("date"),
                    "confidence_score": 1.0,
                    "llm_model": "direct_debit_rule",
                    "enrichment_source": "rule",
                    "matched_rule": f"Direct Debit: {payee_match.get('pattern')}",
                    "matched_merchant": payee_match.get("normalized_name"),
                }
                logger.info(
                    f"Applied direct debit rule for '{payee}' to transaction: {description[:50]}..."
                )
                return enrichment
    except ImportError:
        logger.warning("pattern_extractor not available, skipping payee extraction")
    except Exception as e:
        logger.warning(f"Error extracting payee: {e}")

    # Step 2: Check category rules
    category_match = match_category_rule(description, transaction_type, category_rules)

    # Step 3: Check merchant normalizations (full description match)
    merchant_match = match_merchant_normalization(description, merchant_normalizations)

    # If we have a category match, we can skip LLM
    if category_match:
        enrichment = {
            "primary_category": category_match.get("category"),
            "subcategory": category_match.get("subcategory"),
            "merchant_clean_name": merchant_match.get("normalized_name")
            if merchant_match
            else None,
            "merchant_type": merchant_match.get("merchant_type")
            if merchant_match
            else None,
            "essential_discretionary": _infer_essential_discretionary(
                category_match.get("category")
            ),
            "payment_method": None,
            "payment_method_subtype": None,
            "purchase_date": transaction.get("date"),
            "confidence_score": 1.0,  # Rules are deterministic
            "llm_model": "consistency_rule",  # Indicates rule-based enrichment
            "enrichment_source": "rule",
            "matched_rule": category_match.get("rule_name"),
            "matched_merchant": merchant_match.get("normalized_name")
            if merchant_match
            else None,
        }

        logger.info(
            f"Applied rule '{category_match.get('rule_name')}' to transaction: {description[:50]}..."
        )
        return enrichment

    # If only merchant matched, return partial info (LLM will still be called)
    if merchant_match:
        return {
            "merchant_hint": {
                "normalized_name": merchant_match.get("normalized_name"),
                "merchant_type": merchant_match.get("merchant_type"),
                "default_category": merchant_match.get("default_category"),
            }
        }

    return None


def _infer_essential_discretionary(category: str) -> str:
    """Infer essential/discretionary based on category.
    Uses is_essential flag from normalized_categories table."""
    try:
        import database_postgres as database

        essential_names = database.get_essential_category_names()
        if category in essential_names:
            return "Essential"
    except Exception:
        # Fallback to hardcoded list if database unavailable
        fallback_essential = {
            "Groceries",
            "Utilities",
            "Healthcare",
            "Transportation",
            "Housing",
            "Insurance",
            "Education",
            "Income",
            "Transfer",
            "Interest",
            "Banking Fees",
            "Taxes",
        }
        if category in fallback_essential:
            return "Essential"

    return "Discretionary"


def get_enrichment_from_rules(
    transactions: list[dict],
    category_rules: list[dict],
    merchant_normalizations: list[dict],
) -> dict[int, dict]:
    """
    Apply rules to multiple transactions and return enrichments.

    Args:
        transactions: List of transaction dicts
        category_rules: Category rules from database
        merchant_normalizations: Merchant normalizations from database

    Returns:
        Dict mapping transaction_id to enrichment dict
    """
    enrichments = {}

    for txn in transactions:
        txn_id = txn.get("id")
        result = apply_rules_to_transaction(
            txn, category_rules, merchant_normalizations
        )

        if result and "primary_category" in result:
            # Full enrichment from rules
            enrichments[txn_id] = result

    return enrichments
