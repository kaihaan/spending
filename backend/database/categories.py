"""
Categories & Rules - Database Operations

Handles all database operations for transaction categorization, category rules,
and category management.

Migrated to SQLAlchemy from psycopg2.

Modules:
- Category promotion (promote_category, demote_category, etc.)
- Normalized categories & subcategories (get_all_categories, get_subcategories, etc.)
- Category rules testing and statistics (test_category_rule, get_rule_statistics, etc.)
"""

import contextlib

import cache_manager
from sqlalchemy import func, text

from .base import get_session
from .enrichment import save_rule_enrichment
from .models.category import (
    Category,
    CategoryRule,
    CustomCategory,
    MerchantNormalization,
    NormalizedCategory,
    NormalizedSubcategory,
    SubcategoryMapping,
)
from .models.enrichment import (
    LLMEnrichmentResult,
    RuleEnrichmentResult,
    TransactionEnrichmentSource,
)
from .models.truelayer import TrueLayerTransaction

# ============================================================================
# CATEGORY PROMOTION FUNCTIONS
# ============================================================================


def get_custom_categories(category_type=None, user_id=1):
    """Get custom categories, optionally filtered by type ('promoted' or 'hidden')."""
    with get_session() as session:
        query = session.query(CustomCategory).filter(CustomCategory.user_id == user_id)

        if category_type:
            query = query.filter(CustomCategory.category_type == category_type)
            query = query.order_by(
                CustomCategory.display_order.asc(), CustomCategory.name.asc()
            )
        else:
            query = query.order_by(
                CustomCategory.category_type.asc(),
                CustomCategory.display_order.asc(),
                CustomCategory.name.asc(),
            )

        categories = query.all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "category_type": c.category_type,
                "display_order": c.display_order,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in categories
        ]


def get_category_spending_summary(date_from=None, date_to=None):
    """Get all categories with spending totals from transactions."""
    with get_session() as session:
        # Build query with optional date filters
        query = session.query(
            func.coalesce(
                TrueLayerTransaction.transaction_category, "Uncategorized"
            ).label("name"),
            func.sum(TrueLayerTransaction.amount).label("total_spend"),
            func.count().label("transaction_count"),
        ).filter(TrueLayerTransaction.transaction_type == "DEBIT")

        if date_from:
            query = query.filter(TrueLayerTransaction.timestamp >= date_from)
        if date_to:
            query = query.filter(TrueLayerTransaction.timestamp <= date_to)

        query = query.group_by(TrueLayerTransaction.transaction_category).order_by(
            text("total_spend DESC")
        )

        results = query.all()

        # Check which are custom categories
        custom_cats = get_custom_categories(category_type="promoted")
        custom_names = {c["name"] for c in custom_cats}

        categories = []
        for row in results:
            categories.append(
                {
                    "name": row.name,
                    "total_spend": float(row.total_spend) if row.total_spend else 0.0,
                    "transaction_count": row.transaction_count,
                    "is_custom": row.name in custom_names,
                }
            )

        return categories


def get_subcategory_spending(category_name, date_from=None, date_to=None):
    """Get subcategories within a category with spending totals.

    Reads subcategory data from dedicated enrichment tables with COALESCE
    priority: Rule > LLM > External.
    """
    with get_session() as session:
        # Build subquery to get subcategory from enrichment tables (coalesced)
        # We use a CASE expression to prioritize: Rule > LLM > External
        subcategory_expr = func.coalesce(
            RuleEnrichmentResult.subcategory,
            LLMEnrichmentResult.subcategory,
            TransactionEnrichmentSource.subcategory,
            "Unknown",
        ).label("name")

        query = (
            session.query(
                subcategory_expr,
                func.sum(TrueLayerTransaction.amount).label("total_spend"),
                func.count().label("transaction_count"),
            )
            .outerjoin(
                RuleEnrichmentResult,
                TrueLayerTransaction.id
                == RuleEnrichmentResult.truelayer_transaction_id,
            )
            .outerjoin(
                LLMEnrichmentResult,
                TrueLayerTransaction.id == LLMEnrichmentResult.truelayer_transaction_id,
            )
            .outerjoin(
                TransactionEnrichmentSource,
                TrueLayerTransaction.id
                == TransactionEnrichmentSource.truelayer_transaction_id,
            )
            .filter(
                TrueLayerTransaction.transaction_type == "DEBIT",
                TrueLayerTransaction.transaction_category == category_name,
            )
        )

        if date_from:
            query = query.filter(TrueLayerTransaction.timestamp >= date_from)
        if date_to:
            query = query.filter(TrueLayerTransaction.timestamp <= date_to)

        query = query.group_by(
            func.coalesce(
                RuleEnrichmentResult.subcategory,
                LLMEnrichmentResult.subcategory,
                TransactionEnrichmentSource.subcategory,
                "Unknown",
            )
        ).order_by(text("total_spend DESC"))

        results = query.all()

        # Get mapped subcategories
        mapped_subcats = session.query(SubcategoryMapping.subcategory_name).all()
        mapped = {row[0] for row in mapped_subcats}

        subcategories = []
        for row in results:
            subcategories.append(
                {
                    "name": row.name,
                    "total_spend": float(row.total_spend) if row.total_spend else 0.0,
                    "transaction_count": row.transaction_count,
                    "already_mapped": row.name in mapped,
                }
            )

        return subcategories


def create_promoted_category(name, subcategories, user_id=1):
    """
    Create a promoted category from subcategories and update all matching transactions.

    Updates transaction_category and primary_category in enrichment tables
    for transactions with matching subcategories.

    Args:
        name: Name of the new category
        subcategories: List of dicts with 'name' and 'original_category' keys
        user_id: User ID (default 1)

    Returns:
        Dict with category_id and transactions_updated count
    """
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy.exc import IntegrityError

    with get_session() as session:
        try:
            # Insert the custom category
            stmt = (
                insert(CustomCategory)
                .values(user_id=user_id, name=name, category_type="promoted")
                .returning(CustomCategory.id)
            )
            result = session.execute(stmt)
            category_id = result.scalar_one()

            # Insert subcategory mappings
            subcategory_names = []
            for sub in subcategories:
                mapping = SubcategoryMapping(
                    custom_category_id=category_id,
                    subcategory_name=sub["name"],
                    original_category=sub.get("original_category"),
                )
                session.add(mapping)
                subcategory_names.append(sub["name"])

            transactions_updated = 0

            if subcategory_names:
                # Find transaction IDs with matching subcategories in enrichment tables
                # Check all three enrichment tables

                # Rule enrichment
                rule_txn_ids = (
                    session.query(RuleEnrichmentResult.truelayer_transaction_id)
                    .filter(RuleEnrichmentResult.subcategory.in_(subcategory_names))
                    .all()
                )

                # LLM enrichment
                llm_txn_ids = (
                    session.query(LLMEnrichmentResult.truelayer_transaction_id)
                    .filter(LLMEnrichmentResult.subcategory.in_(subcategory_names))
                    .all()
                )

                # External enrichment
                ext_txn_ids = (
                    session.query(TransactionEnrichmentSource.truelayer_transaction_id)
                    .filter(
                        TransactionEnrichmentSource.subcategory.in_(subcategory_names)
                    )
                    .all()
                )

                # Combine all transaction IDs
                all_txn_ids = set()
                all_txn_ids.update(t[0] for t in rule_txn_ids)
                all_txn_ids.update(t[0] for t in llm_txn_ids)
                all_txn_ids.update(t[0] for t in ext_txn_ids)

                if all_txn_ids:
                    txn_id_list = list(all_txn_ids)

                    # Update transaction_category on TrueLayerTransaction
                    session.query(TrueLayerTransaction).filter(
                        TrueLayerTransaction.id.in_(txn_id_list)
                    ).update({"transaction_category": name}, synchronize_session=False)

                    # Update primary_category in enrichment tables
                    session.query(RuleEnrichmentResult).filter(
                        RuleEnrichmentResult.truelayer_transaction_id.in_(txn_id_list)
                    ).update({"primary_category": name}, synchronize_session=False)

                    session.query(LLMEnrichmentResult).filter(
                        LLMEnrichmentResult.truelayer_transaction_id.in_(txn_id_list)
                    ).update({"primary_category": name}, synchronize_session=False)

                    session.query(TransactionEnrichmentSource).filter(
                        TransactionEnrichmentSource.truelayer_transaction_id.in_(
                            txn_id_list
                        )
                    ).update({"primary_category": name}, synchronize_session=False)

                    transactions_updated = len(all_txn_ids)

            session.commit()

            # Invalidate transaction cache
            cache_manager.cache_invalidate_transactions()

            return {
                "category_id": category_id,
                "transactions_updated": transactions_updated,
            }

        except IntegrityError as e:
            session.rollback()
            raise ValueError(f"Category '{name}' already exists") from e


def hide_category(name, user_id=1):
    """
    Hide a category and reset its transactions for re-enrichment.

    Deletes enrichment data from dedicated enrichment tables for transactions
    in this category, allowing them to be re-enriched.

    Args:
        name: Name of the category to hide
        user_id: User ID (default 1)

    Returns:
        Dict with category_id and transactions_reset count
    """
    from sqlalchemy.dialects.postgresql import insert

    with get_session() as session:
        # Insert/update the hidden category
        stmt = (
            insert(CustomCategory)
            .values(user_id=user_id, name=name, category_type="hidden")
            .on_conflict_do_update(
                index_elements=["user_id", "name"],
                set_={"category_type": "hidden", "updated_at": func.now()},
            )
            .returning(CustomCategory.id)
        )
        result = session.execute(stmt)
        category_id = result.scalar_one()

        # Get transaction IDs with this category
        transaction_ids = (
            session.query(TrueLayerTransaction.id)
            .filter(TrueLayerTransaction.transaction_category == name)
            .all()
        )
        transaction_ids = [t[0] for t in transaction_ids]

        if transaction_ids:
            # Delete from all enrichment tables for these transactions
            session.query(RuleEnrichmentResult).filter(
                RuleEnrichmentResult.truelayer_transaction_id.in_(transaction_ids)
            ).delete(synchronize_session=False)

            session.query(LLMEnrichmentResult).filter(
                LLMEnrichmentResult.truelayer_transaction_id.in_(transaction_ids)
            ).delete(synchronize_session=False)

            session.query(TransactionEnrichmentSource).filter(
                TransactionEnrichmentSource.truelayer_transaction_id.in_(
                    transaction_ids
                )
            ).delete(synchronize_session=False)

            # Reset transaction_category to NULL
            session.query(TrueLayerTransaction).filter(
                TrueLayerTransaction.id.in_(transaction_ids)
            ).update({"transaction_category": None}, synchronize_session=False)

        transactions_reset = len(transaction_ids)

        session.commit()

        # Invalidate transaction cache
        cache_manager.cache_invalidate_transactions()

        return {
            "category_id": category_id,
            "transactions_reset": transactions_reset,
        }


def unhide_category(name, user_id=1):
    """
    Remove a category from the hidden list.

    Args:
        name: Name of the category to unhide
        user_id: User ID (default 1)

    Returns:
        True if successfully unhidden, False if not found
    """
    with get_session() as session:
        result = (
            session.query(CustomCategory)
            .filter(
                CustomCategory.user_id == user_id,
                CustomCategory.name == name,
                CustomCategory.category_type == "hidden",
            )
            .delete()
        )
        session.commit()
        return result > 0


def get_mapped_subcategories(category_name=None):
    """Get all subcategory mappings, optionally filtered by promoted category name."""
    with get_session() as session:
        query = (
            session.query(
                SubcategoryMapping.id,
                SubcategoryMapping.subcategory_name,
                SubcategoryMapping.original_category,
                CustomCategory.name.label("promoted_category"),
            )
            .join(CustomCategory)
            .filter(CustomCategory.category_type == "promoted")
        )

        if category_name:
            query = query.filter(CustomCategory.name == category_name)

        results = query.all()
        return [
            {
                "id": r.id,
                "subcategory_name": r.subcategory_name,
                "original_category": r.original_category,
                "promoted_category": r.promoted_category,
            }
            for r in results
        ]


# ============================================================================


# ============================================================================
# RULES TESTING AND STATISTICS
# ============================================================================


def test_rule_pattern(pattern: str, pattern_type: str, limit: int = 10) -> dict:
    """
    Test a pattern against all transactions to see what would match.

    Args:
        pattern: The pattern to test
        pattern_type: Type of pattern (contains, starts_with, exact, regex)
        limit: Maximum number of sample transactions to return

    Returns:
        Dict with: match_count, sample_transactions
    """
    import re

    with get_session() as session:
        # Get all transactions
        transactions = (
            session.query(
                TrueLayerTransaction.id,
                TrueLayerTransaction.description,
                TrueLayerTransaction.amount,
                TrueLayerTransaction.timestamp.label("date"),
            )
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )

        matches = []
        pattern_upper = pattern.upper()

        for txn in transactions:
            description = txn.description.upper() if txn.description else ""

            matched = False
            if pattern_type == "contains":
                matched = pattern_upper in description
            elif pattern_type == "starts_with":
                matched = description.startswith(pattern_upper)
            elif pattern_type == "exact":
                matched = description == pattern_upper
            elif pattern_type == "regex":
                try:
                    matched = bool(
                        re.search(pattern, txn.description or "", re.IGNORECASE)
                    )
                except re.error:
                    matched = False

            if matched:
                matches.append(
                    {
                        "id": txn.id,
                        "description": txn.description,
                        "amount": float(txn.amount) if txn.amount else 0,
                        "date": txn.date.isoformat() if txn.date else None,
                    }
                )

        return {"match_count": len(matches), "sample_transactions": matches[:limit]}


def get_rules_statistics() -> dict:
    """
    Get comprehensive rule usage statistics and coverage metrics.

    Returns:
        Dict with:
            - category_rules_count: Total category rules
            - merchant_rules_count: Total merchant normalizations
            - total_usage: Sum of all rule usage counts
            - coverage_percentage: Percent of transactions with rule-based enrichment
            - rules_by_category: Dict mapping category to rule count
            - rules_by_source: Dict mapping source to rule count
            - top_used_rules: List of top 10 most used rules
            - unused_rules: List of rules with usage_count = 0
    """
    from sqlalchemy import literal, union_all

    with get_session() as session:
        # Count category rules
        category_rules_count = (
            session.query(func.count())
            .select_from(CategoryRule)
            .filter(CategoryRule.is_active.is_(True))
            .scalar()
        )

        # Count merchant normalizations
        merchant_rules_count = (
            session.query(func.count()).select_from(MerchantNormalization).scalar()
        )

        # Get total usage
        category_usage = (
            session.query(func.coalesce(func.sum(CategoryRule.usage_count), 0))
            .select_from(CategoryRule)
            .scalar()
        )
        merchant_usage = (
            session.query(func.coalesce(func.sum(MerchantNormalization.usage_count), 0))
            .select_from(MerchantNormalization)
            .scalar()
        )
        total_usage = category_usage + merchant_usage

        # Get coverage: count transactions with rule-based enrichment
        total_transactions = (
            session.query(func.count()).select_from(TrueLayerTransaction).scalar()
        )

        # Count transactions with rule-based enrichment from dedicated table
        covered_transactions = (
            session.query(func.count()).select_from(RuleEnrichmentResult).scalar()
        )

        coverage_percentage = (
            (covered_transactions / total_transactions * 100)
            if total_transactions > 0
            else 0
        )

        # Rules by category
        rules_by_category_query = (
            session.query(CategoryRule.category, func.count().label("count"))
            .filter(CategoryRule.is_active.is_(True))
            .group_by(CategoryRule.category)
            .order_by(func.count().desc())
            .all()
        )
        rules_by_category = {row.category: row.count for row in rules_by_category_query}

        # Rules by source (combine both tables)
        category_sources = session.query(CategoryRule.source.label("source")).filter(
            CategoryRule.is_active.is_(True)
        )
        merchant_sources = session.query(MerchantNormalization.source.label("source"))

        combined_sources = union_all(category_sources, merchant_sources).subquery()

        rules_by_source_query = (
            session.query(combined_sources.c.source, func.count().label("count"))
            .group_by(combined_sources.c.source)
            .order_by(func.count().desc())
            .all()
        )
        rules_by_source = {row.source: row.count for row in rules_by_source_query}

        # Top used rules (combine category rules and merchant normalizations)
        category_rules_query = session.query(
            CategoryRule.rule_name.label("name"),
            CategoryRule.usage_count.label("usage_count"),
            literal("category").label("type"),
        ).filter(CategoryRule.is_active.is_(True))

        merchant_rules_query = session.query(
            MerchantNormalization.pattern.label("name"),
            MerchantNormalization.usage_count.label("usage_count"),
            literal("merchant").label("type"),
        )

        top_rules_combined = union_all(
            category_rules_query, merchant_rules_query
        ).subquery()

        top_used_rules_query = (
            session.query(top_rules_combined)
            .order_by(top_rules_combined.c.usage_count.desc())
            .limit(10)
            .all()
        )
        top_used_rules = [
            {"name": row.name, "count": row.usage_count, "type": row.type}
            for row in top_used_rules_query
        ]

        # Unused rules
        unused_category_rules = session.query(
            CategoryRule.rule_name.label("name"), literal("category").label("type")
        ).filter(CategoryRule.is_active.is_(True), CategoryRule.usage_count == 0)

        unused_merchant_rules = session.query(
            MerchantNormalization.pattern.label("name"),
            literal("merchant").label("type"),
        ).filter(MerchantNormalization.usage_count == 0)

        unused_rules_combined = union_all(
            unused_category_rules, unused_merchant_rules
        ).subquery()

        unused_rules_query = session.query(unused_rules_combined).all()
        unused_rules = [
            {"name": row.name, "type": row.type} for row in unused_rules_query
        ]

        return {
            "category_rules_count": category_rules_count,
            "merchant_rules_count": merchant_rules_count,
            "total_usage": total_usage,
            "total_transactions": total_transactions,
            "covered_transactions": covered_transactions,
            "coverage_percentage": round(coverage_percentage, 1),
            "rules_by_category": rules_by_category,
            "rules_by_source": rules_by_source,
            "top_used_rules": top_used_rules,
            "unused_rules": unused_rules,
            "unused_rules_count": len(unused_rules),
        }


def test_all_rules() -> dict:
    """
    Evaluate all rules against all transactions and return a coverage report.

    Returns detailed breakdown by category, identifies conflicts, and unused rules.
    """
    import re
    from collections import defaultdict

    with get_session() as session:
        # Get all active category rules
        category_rules_orm = (
            session.query(
                CategoryRule.id,
                CategoryRule.rule_name,
                CategoryRule.description_pattern,
                CategoryRule.pattern_type,
                CategoryRule.category,
                CategoryRule.subcategory,
            )
            .filter(CategoryRule.is_active.is_(True))
            .order_by(CategoryRule.priority.desc())
            .all()
        )
        category_rules = [
            {
                "id": r.id,
                "rule_name": r.rule_name,
                "description_pattern": r.description_pattern,
                "pattern_type": r.pattern_type,
                "category": r.category,
                "subcategory": r.subcategory,
            }
            for r in category_rules_orm
        ]

        # Get all merchant normalizations
        merchant_rules_orm = (
            session.query(
                MerchantNormalization.id,
                MerchantNormalization.pattern,
                MerchantNormalization.pattern_type,
                MerchantNormalization.normalized_name,
                MerchantNormalization.default_category,
            )
            .order_by(MerchantNormalization.priority.desc())
            .all()
        )
        merchant_rules = [
            {
                "id": r.id,
                "pattern": r.pattern,
                "pattern_type": r.pattern_type,
                "normalized_name": r.normalized_name,
                "default_category": r.default_category,
            }
            for r in merchant_rules_orm
        ]

        # Get all transactions
        transactions_orm = session.query(
            TrueLayerTransaction.id, TrueLayerTransaction.description
        ).all()
        transactions = [
            {"id": t.id, "description": t.description} for t in transactions_orm
        ]

        # Track matches
        rule_matches = defaultdict(list)  # rule_id -> [txn_ids]
        txn_matches = defaultdict(list)  # txn_id -> [rule_ids]
        category_coverage = defaultdict(int)  # category -> count

        for txn in transactions:
            desc = txn["description"].upper() if txn["description"] else ""

            # Check category rules
            for rule in category_rules:
                pattern = rule["description_pattern"].upper()
                pattern_type = rule["pattern_type"]

                matched = False
                if pattern_type == "contains":
                    matched = pattern in desc
                elif pattern_type == "starts_with":
                    matched = desc.startswith(pattern)
                elif pattern_type == "exact":
                    matched = desc == pattern
                elif pattern_type == "regex":
                    with contextlib.suppress(re.error):
                        matched = bool(
                            re.search(
                                rule["description_pattern"],
                                txn["description"] or "",
                                re.IGNORECASE,
                            )
                        )

                if matched:
                    rule_key = f"cat_{rule['id']}"
                    rule_matches[rule_key].append(txn["id"])
                    txn_matches[txn["id"]].append(rule_key)
                    category_coverage[rule["category"]] += 1

            # Check merchant rules
            for rule in merchant_rules:
                pattern = rule["pattern"].upper()
                pattern_type = rule["pattern_type"]

                matched = False
                if pattern_type == "contains":
                    matched = pattern in desc
                elif pattern_type == "starts_with":
                    matched = desc.startswith(pattern)
                elif pattern_type == "exact":
                    matched = desc == pattern
                elif pattern_type == "regex":
                    with contextlib.suppress(re.error):
                        matched = bool(
                            re.search(
                                rule["pattern"],
                                txn["description"] or "",
                                re.IGNORECASE,
                            )
                        )

                if matched:
                    rule_key = f"mer_{rule['id']}"
                    rule_matches[rule_key].append(txn["id"])
                    txn_matches[txn["id"]].append(rule_key)
                    if rule["default_category"]:
                        category_coverage[rule["default_category"]] += 1

        # Calculate statistics
        total_transactions = len(transactions)
        covered_transactions = len([t for t in txn_matches if txn_matches[t]])
        coverage_percentage = (
            (covered_transactions / total_transactions * 100)
            if total_transactions > 0
            else 0
        )

        # Find unused rules
        unused_category_rules = [
            r for r in category_rules if f"cat_{r['id']}" not in rule_matches
        ]
        unused_merchant_rules = [
            r for r in merchant_rules if f"mer_{r['id']}" not in rule_matches
        ]

        # Find potential conflicts (transactions matching multiple rules)
        conflicts = []
        for txn_id, rules in txn_matches.items():
            if len(rules) > 1:
                conflicts.append({"transaction_id": txn_id, "matching_rules": rules})

        return {
            "total_transactions": total_transactions,
            "covered_transactions": covered_transactions,
            "coverage_percentage": round(coverage_percentage, 1),
            "category_coverage": dict(category_coverage),
            "unused_category_rules": [
                {
                    "id": r["id"],
                    "name": r["rule_name"],
                    "pattern": r["description_pattern"],
                }
                for r in unused_category_rules
            ],
            "unused_merchant_rules": [
                {
                    "id": r["id"],
                    "pattern": r["pattern"],
                    "name": r["normalized_name"],
                }
                for r in unused_merchant_rules
            ],
            "potential_conflicts_count": len(conflicts),
            "sample_conflicts": conflicts[:10],  # Limit to 10 examples
        }


def apply_all_rules_to_transactions() -> dict:
    """
    Re-enrich all transactions using current category rules and merchant normalizations.

    This applies the consistency engine to all transactions, updating enrichment data
    for transactions that match rules.

    Returns:
        Dict with: updated_count, rule_hits (dict of rule_name -> count)
    """
    from mcp.consistency_engine import apply_rules_to_transaction

    with get_session() as session:
        # Get all rules
        category_rules_orm = (
            session.query(CategoryRule)
            .filter(CategoryRule.is_active.is_(True))
            .order_by(CategoryRule.priority.desc())
            .all()
        )
        category_rules = [
            {
                "id": r.id,
                "rule_name": r.rule_name,
                "transaction_type": r.transaction_type,
                "description_pattern": r.description_pattern,
                "pattern_type": r.pattern_type,
                "category": r.category,
                "subcategory": r.subcategory,
                "priority": r.priority,
                "is_active": r.is_active,
                "source": r.source,
                "usage_count": r.usage_count,
                "created_at": r.created_at,
            }
            for r in category_rules_orm
        ]

        merchant_normalizations_orm = (
            session.query(MerchantNormalization)
            .order_by(MerchantNormalization.priority.desc())
            .all()
        )
        merchant_normalizations = [
            {
                "id": r.id,
                "pattern": r.pattern,
                "pattern_type": r.pattern_type,
                "normalized_name": r.normalized_name,
                "merchant_type": r.merchant_type,
                "default_category": r.default_category,
                "priority": r.priority,
                "source": r.source,
                "usage_count": r.usage_count,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in merchant_normalizations_orm
        ]

        # Get all transactions
        transactions_orm = session.query(
            TrueLayerTransaction.id,
            TrueLayerTransaction.description,
            TrueLayerTransaction.amount,
            TrueLayerTransaction.transaction_type,
            TrueLayerTransaction.timestamp,
            TrueLayerTransaction.metadata,
        ).all()

        updated_count = 0
        rule_hits = {}

        for txn in transactions_orm:
            txn_dict = {
                "id": txn.id,
                "description": txn.description,
                "amount": txn.amount,
                "transaction_type": txn.transaction_type,
                "timestamp": txn.timestamp,
                "metadata": txn.metadata,
            }
            result = apply_rules_to_transaction(
                txn_dict, category_rules, merchant_normalizations
            )

            if result and result.get("primary_category"):
                # Determine rule_type from llm_model field
                llm_model = result.get("llm_model", "consistency_rule")
                if llm_model == "direct_debit_rule":
                    rule_type = "direct_debit"
                else:
                    rule_type = "category_rule"

                # Save to dedicated rule_enrichment_results table
                save_rule_enrichment(
                    transaction_id=txn.id,
                    primary_category=result.get("primary_category"),
                    rule_type=rule_type,
                    subcategory=result.get("subcategory"),
                    essential_discretionary=result.get("essential_discretionary"),
                    merchant_clean_name=result.get("merchant_clean_name"),
                    merchant_type=result.get("merchant_type"),
                    matched_rule_name=result.get("matched_rule"),
                    matched_merchant_name=result.get("matched_merchant"),
                    confidence_score=result.get("confidence_score", 1.0),
                )

                updated_count += 1

                # Track rule hits
                matched_rule = result.get("matched_rule", "unknown")
                rule_hits[matched_rule] = rule_hits.get(matched_rule, 0) + 1

        session.commit()

        return {
            "updated_count": updated_count,
            "total_transactions": len(transactions_orm),
            "rule_hits": rule_hits,
        }


# ============================================================================


# ============================================================================
# NORMALIZED CATEGORIES & SUBCATEGORIES FUNCTIONS
# ============================================================================


def get_normalized_categories(active_only: bool = False, include_counts: bool = False):
    """Get all normalized categories.

    Args:
        active_only: If True, only return categories where is_active=TRUE
        include_counts: If True, include transaction and subcategory counts

    Returns:
        List of category dictionaries
    """
    with get_session() as session:
        if include_counts:
            # Transaction counts subquery
            txn_counts_sq = (
                session.query(
                    TrueLayerTransaction.category_id,
                    func.count().label("transaction_count"),
                )
                .filter(TrueLayerTransaction.category_id.is_not(None))
                .group_by(TrueLayerTransaction.category_id)
                .subquery()
            )

            # Subcategory counts subquery
            sub_counts_sq = (
                session.query(
                    NormalizedSubcategory.category_id,
                    func.count().label("subcategory_count"),
                )
                .group_by(NormalizedSubcategory.category_id)
                .subquery()
            )

            # Main query with LEFT JOINs
            query = (
                session.query(
                    NormalizedCategory,
                    func.coalesce(txn_counts_sq.c.transaction_count, 0).label(
                        "transaction_count"
                    ),
                    func.coalesce(sub_counts_sq.c.subcategory_count, 0).label(
                        "subcategory_count"
                    ),
                )
                .outerjoin(
                    txn_counts_sq, NormalizedCategory.id == txn_counts_sq.c.category_id
                )
                .outerjoin(
                    sub_counts_sq, NormalizedCategory.id == sub_counts_sq.c.category_id
                )
            )

            if active_only:
                query = query.filter(NormalizedCategory.is_active.is_(True))

            results = query.order_by(
                NormalizedCategory.display_order, NormalizedCategory.name
            ).all()

            return [
                {
                    "id": r.NormalizedCategory.id,
                    "name": r.NormalizedCategory.name,
                    "description": r.NormalizedCategory.description,
                    "is_system": r.NormalizedCategory.is_system,
                    "is_active": r.NormalizedCategory.is_active,
                    "is_essential": r.NormalizedCategory.is_essential,
                    "display_order": r.NormalizedCategory.display_order,
                    "color": r.NormalizedCategory.color,
                    "created_at": r.NormalizedCategory.created_at,
                    "updated_at": r.NormalizedCategory.updated_at,
                    "transaction_count": r.transaction_count,
                    "subcategory_count": r.subcategory_count,
                }
                for r in results
            ]
        query = session.query(NormalizedCategory)

        if active_only:
            query = query.filter(NormalizedCategory.is_active.is_(True))

        categories = query.order_by(
            NormalizedCategory.display_order, NormalizedCategory.name
        ).all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "is_system": c.is_system,
                "is_active": c.is_active,
                "is_essential": c.is_essential,
                "display_order": c.display_order,
                "color": c.color,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in categories
        ]


def get_normalized_category_by_id(category_id: int):
    """Get a single normalized category by ID with subcategories."""
    with get_session() as session:
        # Transaction counts subquery for category
        txn_counts_sq = (
            session.query(
                TrueLayerTransaction.category_id,
                func.count().label("transaction_count"),
            )
            .filter(TrueLayerTransaction.category_id.is_not(None))
            .group_by(TrueLayerTransaction.category_id)
            .subquery()
        )

        # Get category with transaction count
        result = (
            session.query(
                NormalizedCategory,
                func.coalesce(txn_counts_sq.c.transaction_count, 0).label(
                    "transaction_count"
                ),
            )
            .outerjoin(
                txn_counts_sq, NormalizedCategory.id == txn_counts_sq.c.category_id
            )
            .filter(NormalizedCategory.id == category_id)
            .first()
        )

        if not result:
            return None

        category = {
            "id": result.NormalizedCategory.id,
            "name": result.NormalizedCategory.name,
            "description": result.NormalizedCategory.description,
            "is_system": result.NormalizedCategory.is_system,
            "is_active": result.NormalizedCategory.is_active,
            "is_essential": result.NormalizedCategory.is_essential,
            "display_order": result.NormalizedCategory.display_order,
            "color": result.NormalizedCategory.color,
            "created_at": result.NormalizedCategory.created_at,
            "updated_at": result.NormalizedCategory.updated_at,
            "transaction_count": result.transaction_count,
        }

        # Transaction counts subquery for subcategories
        sub_txn_counts_sq = (
            session.query(
                TrueLayerTransaction.subcategory_id,
                func.count().label("transaction_count"),
            )
            .filter(TrueLayerTransaction.subcategory_id.is_not(None))
            .group_by(TrueLayerTransaction.subcategory_id)
            .subquery()
        )

        # Get subcategories with transaction counts
        subcategory_results = (
            session.query(
                NormalizedSubcategory,
                func.coalesce(sub_txn_counts_sq.c.transaction_count, 0).label(
                    "transaction_count"
                ),
            )
            .outerjoin(
                sub_txn_counts_sq,
                NormalizedSubcategory.id == sub_txn_counts_sq.c.subcategory_id,
            )
            .filter(NormalizedSubcategory.category_id == category_id)
            .order_by(NormalizedSubcategory.display_order, NormalizedSubcategory.name)
            .all()
        )

        category["subcategories"] = [
            {
                "id": r.NormalizedSubcategory.id,
                "category_id": r.NormalizedSubcategory.category_id,
                "name": r.NormalizedSubcategory.name,
                "description": r.NormalizedSubcategory.description,
                "is_active": r.NormalizedSubcategory.is_active,
                "display_order": r.NormalizedSubcategory.display_order,
                "created_at": r.NormalizedSubcategory.created_at,
                "updated_at": r.NormalizedSubcategory.updated_at,
                "transaction_count": r.transaction_count,
            }
            for r in subcategory_results
        ]

        return category


def get_normalized_category_by_name(name: str):
    """Get a normalized category by name."""
    with get_session() as session:
        category = (
            session.query(NormalizedCategory)
            .filter(NormalizedCategory.name == name)
            .first()
        )

        if not category:
            return None

        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "is_system": category.is_system,
            "is_active": category.is_active,
            "is_essential": category.is_essential,
            "display_order": category.display_order,
            "color": category.color,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
        }


def create_normalized_category(
    name: str, description: str = None, is_essential: bool = False, color: str = None
):
    """Create a new normalized category.

    Returns:
        The created category dict, or None if name already exists
    """
    from sqlalchemy.exc import IntegrityError

    with get_session() as session:
        try:
            # Get next display order
            next_order = (
                session.query(
                    func.coalesce(func.max(NormalizedCategory.display_order), 0) + 1
                )
                .select_from(NormalizedCategory)
                .scalar()
            )

            # Create new category
            new_category = NormalizedCategory(
                name=name,
                description=description,
                is_system=False,
                is_essential=is_essential,
                display_order=next_order,
                color=color,
            )
            session.add(new_category)
            session.commit()

            return {
                "id": new_category.id,
                "name": new_category.name,
                "description": new_category.description,
                "is_system": new_category.is_system,
                "is_active": new_category.is_active,
                "is_essential": new_category.is_essential,
                "display_order": new_category.display_order,
                "color": new_category.color,
                "created_at": new_category.created_at,
                "updated_at": new_category.updated_at,
            }
        except IntegrityError:
            session.rollback()
            return None


def update_normalized_category(
    category_id: int,
    name: str = None,
    description: str = None,
    is_active: bool = None,
    is_essential: bool = None,
    color: str = None,
):
    """Update a normalized category and cascade changes if name changed.

    Returns:
        Dict with category and update counts, or None if not found
    """
    with get_session() as session:
        # Get current category
        current = session.get(NormalizedCategory, category_id)
        if not current:
            return None

        old_name = current.name
        new_name = name if name is not None else old_name

        # Track if any updates were made
        has_updates = False

        # Update fields if provided
        if name is not None:
            current.name = name
            has_updates = True
        if description is not None:
            current.description = description
            has_updates = True
        if is_active is not None:
            current.is_active = is_active
            has_updates = True
        if is_essential is not None:
            current.is_essential = is_essential
            has_updates = True
        if color is not None:
            current.color = color
            has_updates = True

        if not has_updates:
            return {
                "category": {
                    "id": current.id,
                    "name": current.name,
                    "description": current.description,
                    "is_system": current.is_system,
                    "is_active": current.is_active,
                    "is_essential": current.is_essential,
                    "display_order": current.display_order,
                    "color": current.color,
                    "created_at": current.created_at,
                    "updated_at": current.updated_at,
                },
                "transactions_updated": 0,
                "rules_updated": 0,
            }

        session.flush()  # Flush to get updated timestamp

        transactions_updated = 0
        rules_updated = 0

        # If name changed, cascade updates
        if name is not None and name != old_name:
            # Update transaction_category VARCHAR (for backwards compatibility)
            result = session.execute(
                text("""
                    UPDATE truelayer_transactions
                    SET transaction_category = :new_name
                    WHERE category_id = :category_id
                """),
                {"new_name": new_name, "category_id": category_id},
            )
            transactions_updated = result.rowcount

            # Update primary_category in enrichment tables
            # Get transaction IDs for this category
            txn_ids = (
                session.query(TrueLayerTransaction.id)
                .filter(TrueLayerTransaction.category_id == category_id)
                .all()
            )
            txn_id_list = [t[0] for t in txn_ids]

            if txn_id_list:
                session.query(RuleEnrichmentResult).filter(
                    RuleEnrichmentResult.truelayer_transaction_id.in_(txn_id_list)
                ).update({"primary_category": new_name}, synchronize_session=False)

                session.query(LLMEnrichmentResult).filter(
                    LLMEnrichmentResult.truelayer_transaction_id.in_(txn_id_list)
                ).update({"primary_category": new_name}, synchronize_session=False)

                session.query(TransactionEnrichmentSource).filter(
                    TransactionEnrichmentSource.truelayer_transaction_id.in_(
                        txn_id_list
                    )
                ).update({"primary_category": new_name}, synchronize_session=False)

            # Update category_rules VARCHAR
            result = session.execute(
                text("""
                    UPDATE category_rules
                    SET category = :new_name
                    WHERE category_id = :category_id
                """),
                {"new_name": new_name, "category_id": category_id},
            )
            rules_updated = result.rowcount

        session.commit()

        # Invalidate cache
        try:
            from cache_manager import cache_invalidate_transactions

            cache_invalidate_transactions()
        except ImportError:
            pass

        return {
            "category": {
                "id": current.id,
                "name": current.name,
                "description": current.description,
                "is_system": current.is_system,
                "is_active": current.is_active,
                "is_essential": current.is_essential,
                "display_order": current.display_order,
                "color": current.color,
                "created_at": current.created_at,
                "updated_at": current.updated_at,
            },
            "transactions_updated": transactions_updated,
            "rules_updated": rules_updated,
            "old_name": old_name,
            "new_name": new_name,
        }


def delete_normalized_category(category_id: int, reassign_to_category_id: int = None):
    """Delete a normalized category.

    System categories cannot be deleted. Transactions are reassigned to 'Other' or specified category.

    Returns:
        Dict with deletion result, or None if not found or is system category
    """
    with get_session() as session:
        # Check if category exists and is not system
        category = session.get(NormalizedCategory, category_id)

        if not category:
            return None
        if category.is_system:
            return {"error": "Cannot delete system category"}

        category_name = category.name

        # Find reassignment target (default to 'Other')
        if reassign_to_category_id:
            target_id = reassign_to_category_id
        else:
            other = (
                session.query(NormalizedCategory)
                .filter(NormalizedCategory.name == "Other")
                .first()
            )
            target_id = other.id if other else None

        # Reassign transactions
        transactions_reassigned = 0
        if target_id:
            result = session.execute(
                text("""
                    UPDATE truelayer_transactions
                    SET category_id = :target_id, subcategory_id = NULL
                    WHERE category_id = :category_id
                """),
                {"target_id": target_id, "category_id": category_id},
            )
            transactions_reassigned = result.rowcount

        # Delete the category (subcategories cascade)
        session.delete(category)
        session.commit()

        return {
            "deleted_category": category_name,
            "transactions_reassigned": transactions_reassigned,
            "reassigned_to_category_id": target_id,
        }


def get_normalized_subcategories(category_id: int = None, include_counts: bool = False):
    """Get normalized subcategories, optionally filtered by category.

    Args:
        category_id: If provided, only return subcategories for this category
        include_counts: If True, include transaction counts
    """
    with get_session() as session:
        if include_counts:
            # Transaction counts subquery
            txn_counts_sq = (
                session.query(
                    TrueLayerTransaction.subcategory_id,
                    func.count().label("transaction_count"),
                )
                .filter(TrueLayerTransaction.subcategory_id.is_not(None))
                .group_by(TrueLayerTransaction.subcategory_id)
                .subquery()
            )

            query = (
                session.query(
                    NormalizedSubcategory,
                    NormalizedCategory.name.label("category_name"),
                    func.coalesce(txn_counts_sq.c.transaction_count, 0).label(
                        "transaction_count"
                    ),
                )
                .join(
                    NormalizedCategory,
                    NormalizedSubcategory.category_id == NormalizedCategory.id,
                )
                .outerjoin(
                    txn_counts_sq,
                    NormalizedSubcategory.id == txn_counts_sq.c.subcategory_id,
                )
            )

            if category_id:
                query = query.filter(NormalizedSubcategory.category_id == category_id)
                query = query.order_by(
                    NormalizedSubcategory.display_order, NormalizedSubcategory.name
                )
            else:
                query = query.order_by(
                    NormalizedCategory.name,
                    NormalizedSubcategory.display_order,
                    NormalizedSubcategory.name,
                )

            results = query.all()

            return [
                {
                    "id": r.NormalizedSubcategory.id,
                    "category_id": r.NormalizedSubcategory.category_id,
                    "name": r.NormalizedSubcategory.name,
                    "description": r.NormalizedSubcategory.description,
                    "is_active": r.NormalizedSubcategory.is_active,
                    "display_order": r.NormalizedSubcategory.display_order,
                    "created_at": r.NormalizedSubcategory.created_at,
                    "updated_at": r.NormalizedSubcategory.updated_at,
                    "category_name": r.category_name,
                    "transaction_count": r.transaction_count,
                }
                for r in results
            ]
        query = session.query(
            NormalizedSubcategory, NormalizedCategory.name.label("category_name")
        ).join(
            NormalizedCategory,
            NormalizedSubcategory.category_id == NormalizedCategory.id,
        )

        if category_id:
            query = query.filter(NormalizedSubcategory.category_id == category_id)
            query = query.order_by(
                NormalizedSubcategory.display_order, NormalizedSubcategory.name
            )
        else:
            query = query.order_by(
                NormalizedCategory.name,
                NormalizedSubcategory.display_order,
                NormalizedSubcategory.name,
            )

        results = query.all()

        return [
            {
                "id": r.NormalizedSubcategory.id,
                "category_id": r.NormalizedSubcategory.category_id,
                "name": r.NormalizedSubcategory.name,
                "description": r.NormalizedSubcategory.description,
                "is_active": r.NormalizedSubcategory.is_active,
                "display_order": r.NormalizedSubcategory.display_order,
                "created_at": r.NormalizedSubcategory.created_at,
                "updated_at": r.NormalizedSubcategory.updated_at,
                "category_name": r.category_name,
            }
            for r in results
        ]


def get_normalized_subcategory_by_id(subcategory_id: int):
    """Get a single normalized subcategory by ID."""
    with get_session() as session:
        # Transaction counts subquery
        txn_counts_sq = (
            session.query(
                TrueLayerTransaction.subcategory_id,
                func.count().label("transaction_count"),
            )
            .filter(TrueLayerTransaction.subcategory_id.is_not(None))
            .group_by(TrueLayerTransaction.subcategory_id)
            .subquery()
        )

        result = (
            session.query(
                NormalizedSubcategory,
                NormalizedCategory.name.label("category_name"),
                func.coalesce(txn_counts_sq.c.transaction_count, 0).label(
                    "transaction_count"
                ),
            )
            .join(
                NormalizedCategory,
                NormalizedSubcategory.category_id == NormalizedCategory.id,
            )
            .outerjoin(
                txn_counts_sq,
                NormalizedSubcategory.id == txn_counts_sq.c.subcategory_id,
            )
            .filter(NormalizedSubcategory.id == subcategory_id)
            .first()
        )

        if not result:
            return None

        return {
            "id": result.NormalizedSubcategory.id,
            "category_id": result.NormalizedSubcategory.category_id,
            "name": result.NormalizedSubcategory.name,
            "description": result.NormalizedSubcategory.description,
            "is_active": result.NormalizedSubcategory.is_active,
            "display_order": result.NormalizedSubcategory.display_order,
            "created_at": result.NormalizedSubcategory.created_at,
            "updated_at": result.NormalizedSubcategory.updated_at,
            "category_name": result.category_name,
            "transaction_count": result.transaction_count,
        }


def create_normalized_subcategory(category_id: int, name: str, description: str = None):
    """Create a new normalized subcategory.

    Returns:
        The created subcategory dict, or None if already exists
    """
    from sqlalchemy.exc import IntegrityError

    with get_session() as session:
        try:
            # Get next display order for this category
            next_order = (
                session.query(
                    func.coalesce(func.max(NormalizedSubcategory.display_order), 0) + 1
                )
                .filter(NormalizedSubcategory.category_id == category_id)
                .scalar()
            )

            # Create new subcategory
            new_subcategory = NormalizedSubcategory(
                category_id=category_id,
                name=name,
                description=description,
                display_order=next_order,
            )
            session.add(new_subcategory)
            session.commit()

            # Get category name
            category = session.get(NormalizedCategory, category_id)

            return {
                "id": new_subcategory.id,
                "category_id": new_subcategory.category_id,
                "name": new_subcategory.name,
                "description": new_subcategory.description,
                "is_active": new_subcategory.is_active,
                "display_order": new_subcategory.display_order,
                "created_at": new_subcategory.created_at,
                "updated_at": new_subcategory.updated_at,
                "category_name": category.name if category else None,
            }
        except IntegrityError:
            session.rollback()
            return None


def update_normalized_subcategory(
    subcategory_id: int,
    name: str = None,
    description: str = None,
    is_active: bool = None,
    category_id: int = None,
):
    """Update a normalized subcategory and cascade changes if name changed.

    Returns:
        Dict with subcategory and update counts, or None if not found
    """
    with get_session() as session:
        # Get current subcategory with category name
        result = (
            session.query(
                NormalizedSubcategory, NormalizedCategory.name.label("category_name")
            )
            .join(
                NormalizedCategory,
                NormalizedSubcategory.category_id == NormalizedCategory.id,
            )
            .filter(NormalizedSubcategory.id == subcategory_id)
            .first()
        )

        if not result:
            return None

        current_subcategory = result.NormalizedSubcategory
        old_name = current_subcategory.name
        new_name = name if name is not None else old_name

        # Track if any updates were made
        has_updates = False

        # Update fields if provided
        if name is not None:
            current_subcategory.name = name
            has_updates = True
        if description is not None:
            current_subcategory.description = description
            has_updates = True
        if is_active is not None:
            current_subcategory.is_active = is_active
            has_updates = True
        if category_id is not None:
            current_subcategory.category_id = category_id
            has_updates = True

        if not has_updates:
            return {
                "subcategory": {
                    "id": current_subcategory.id,
                    "category_id": current_subcategory.category_id,
                    "name": current_subcategory.name,
                    "description": current_subcategory.description,
                    "is_active": current_subcategory.is_active,
                    "display_order": current_subcategory.display_order,
                    "created_at": current_subcategory.created_at,
                    "updated_at": current_subcategory.updated_at,
                    "category_name": result.category_name,
                },
                "transactions_updated": 0,
            }

        session.flush()

        # Get new category name
        new_category = session.get(NormalizedCategory, current_subcategory.category_id)

        transactions_updated = 0

        # If name changed, cascade updates to enrichment tables
        if name is not None and name != old_name:
            # Get transaction IDs for this subcategory
            txn_ids = (
                session.query(TrueLayerTransaction.id)
                .filter(TrueLayerTransaction.subcategory_id == subcategory_id)
                .all()
            )
            txn_id_list = [t[0] for t in txn_ids]

            if txn_id_list:
                session.query(RuleEnrichmentResult).filter(
                    RuleEnrichmentResult.truelayer_transaction_id.in_(txn_id_list)
                ).update({"subcategory": new_name}, synchronize_session=False)

                session.query(LLMEnrichmentResult).filter(
                    LLMEnrichmentResult.truelayer_transaction_id.in_(txn_id_list)
                ).update({"subcategory": new_name}, synchronize_session=False)

                session.query(TransactionEnrichmentSource).filter(
                    TransactionEnrichmentSource.truelayer_transaction_id.in_(
                        txn_id_list
                    )
                ).update({"subcategory": new_name}, synchronize_session=False)

            transactions_updated = len(txn_id_list)

        session.commit()

        # Invalidate cache
        try:
            from cache_manager import cache_invalidate_transactions

            cache_invalidate_transactions()
        except ImportError:
            pass

        return {
            "subcategory": {
                "id": current_subcategory.id,
                "category_id": current_subcategory.category_id,
                "name": current_subcategory.name,
                "description": current_subcategory.description,
                "is_active": current_subcategory.is_active,
                "display_order": current_subcategory.display_order,
                "created_at": current_subcategory.created_at,
                "updated_at": current_subcategory.updated_at,
                "category_name": new_category.name if new_category else None,
            },
            "transactions_updated": transactions_updated,
            "old_name": old_name,
            "new_name": new_name,
        }


def delete_normalized_subcategory(subcategory_id: int):
    """Delete a normalized subcategory.

    Transactions will have their subcategory_id set to NULL.

    Returns:
        Dict with deletion result, or None if not found
    """
    with get_session() as session:
        # Get subcategory with category name
        result = (
            session.query(
                NormalizedSubcategory, NormalizedCategory.name.label("category_name")
            )
            .join(
                NormalizedCategory,
                NormalizedSubcategory.category_id == NormalizedCategory.id,
            )
            .filter(NormalizedSubcategory.id == subcategory_id)
            .first()
        )

        if not result:
            return None

        subcategory_name = result.NormalizedSubcategory.name
        category_name = result.category_name

        # Clear subcategory_id from transactions
        result = session.execute(
            text("""
                UPDATE truelayer_transactions
                SET subcategory_id = NULL
                WHERE subcategory_id = :subcategory_id
            """),
            {"subcategory_id": subcategory_id},
        )
        transactions_cleared = result.rowcount

        # Delete the subcategory
        session.delete(result.NormalizedSubcategory)
        session.commit()

        return {
            "deleted_subcategory": subcategory_name,
            "category_name": category_name,
            "transactions_cleared": transactions_cleared,
        }


def get_essential_category_names():
    """Get list of category names that are marked as essential.

    Used by consistency engine for Essential/Discretionary classification.
    """
    with get_session() as session:
        results = (
            session.query(NormalizedCategory.name)
            .filter(
                NormalizedCategory.is_essential.is_(True),
                NormalizedCategory.is_active.is_(True),
            )
            .all()
        )
        return {row.name for row in results}


# =============================================================================


def get_all_categories():
    """Get all categories from database."""
    with get_session() as session:
        categories = session.query(
            Category.id, Category.name, Category.rule_pattern, Category.ai_suggested
        ).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "rule_pattern": c.rule_pattern,
                "ai_suggested": c.ai_suggested,
            }
            for c in categories
        ]
