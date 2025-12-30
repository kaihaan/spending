"""
Core Transactions - Database Operations

Handles core transaction operations, Huququllah classification, account mappings,
and general transaction utilities.

Migrated to SQLAlchemy from psycopg2.
"""

import json

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .base import get_session
from .enrichment import (
    get_combined_enrichment,
    is_transaction_enriched_new,
    save_llm_enrichment,
)
from .models.category import Category, CategoryKeyword
from .models.enrichment import EnrichmentCache
from .models.truelayer import TrueLayerTransaction
from .models.user import AccountMapping

# ============================================================================
# CORE TRANSACTION FUNCTIONS
# ============================================================================


def get_all_categories():
    """Get all categories from database."""
    with get_session() as session:
        categories = session.query(Category).all()
        return [
            {
                "id": cat.id,
                "name": cat.name,
                "rule_pattern": cat.rule_pattern,
                "ai_suggested": cat.ai_suggested,
            }
            for cat in categories
        ]


def update_transaction_with_enrichment(
    transaction_id, enrichment_data, enrichment_source="llm"
):
    """
    Update TrueLayer transaction with LLM enrichment data.

    Args:
        transaction_id: ID of TrueLayer transaction to update
        enrichment_data: Dict or object with enrichment fields
        enrichment_source: 'llm' or 'cache'
    """
    # Convert object to dict if needed
    if not isinstance(enrichment_data, dict):
        enrichment_data = {
            "primary_category": getattr(enrichment_data, "primary_category", "Other"),
            "subcategory": getattr(enrichment_data, "subcategory", None),
            "merchant_clean_name": getattr(
                enrichment_data, "merchant_clean_name", None
            ),
            "merchant_type": getattr(enrichment_data, "merchant_type", None),
            "essential_discretionary": getattr(
                enrichment_data, "essential_discretionary", None
            ),
            "payment_method": getattr(enrichment_data, "payment_method", None),
            "payment_method_subtype": getattr(
                enrichment_data, "payment_method_subtype", None
            ),
            "confidence_score": getattr(enrichment_data, "confidence_score", None),
            "llm_model": getattr(enrichment_data, "llm_model", "unknown"),
        }

    with get_session() as session:
        # Extract category from enrichment
        primary_category = enrichment_data.get("primary_category", "Other")

        # Get transaction
        txn = session.get(TrueLayerTransaction, transaction_id)
        if not txn:
            return False

        # Update transaction core fields
        txn.transaction_category = primary_category
        txn.enrichment_required = False

        # Update merchant_name if available
        merchant_clean_name = enrichment_data.get("merchant_clean_name")
        if merchant_clean_name:
            txn.merchant_name = merchant_clean_name

        session.commit()

    # Save LLM enrichment to dedicated table (outside session to avoid nesting)
    save_llm_enrichment(
        transaction_id=transaction_id,
        primary_category=primary_category,
        llm_provider=enrichment_source,
        llm_model=enrichment_data.get("llm_model", "unknown"),
        subcategory=enrichment_data.get("subcategory"),
        essential_discretionary=enrichment_data.get("essential_discretionary"),
        merchant_clean_name=merchant_clean_name,
        merchant_type=enrichment_data.get("merchant_type"),
        payment_method=enrichment_data.get("payment_method"),
        payment_method_subtype=enrichment_data.get("payment_method_subtype"),
        confidence_score=enrichment_data.get("confidence_score"),
        enrichment_source=enrichment_source,
    )

    return True


def is_transaction_enriched(transaction_id):
    """
    Check if a transaction has enrichment data.

    Checks the dedicated enrichment tables:
    - rule_enrichment_results (category rules, merchant rules, direct debit)
    - llm_enrichment_results (LLM-based categorization)
    - transaction_enrichment_sources (external sources: Amazon, Apple, Gmail)

    Args:
        transaction_id: ID of the transaction

    Returns:
        bool: True if transaction has enrichment data from any source
    """
    return is_transaction_enriched_new(transaction_id)


def get_enrichment_from_cache(description, direction):
    """
    Retrieve cached enrichment for a transaction description.

    Args:
        description: Transaction description to look up
        direction: Transaction direction ('in' or 'out')

    Returns:
        Enrichment object or None if not cached
    """
    with get_session() as session:
        cache_entry = (
            session.query(EnrichmentCache)
            .filter(
                EnrichmentCache.transaction_description == description,
                EnrichmentCache.transaction_direction == direction,
            )
            .first()
        )

        if cache_entry and cache_entry.enrichment_data:
            try:
                from mcp.llm_enricher import EnrichmentResult

                data = json.loads(cache_entry.enrichment_data)
                return EnrichmentResult(**data)
            except (json.JSONDecodeError, Exception):
                return None
        return None


def cache_enrichment(description, direction, enrichment, provider, model):
    """
    Cache enrichment result for a transaction description.

    Args:
        description: Transaction description
        direction: Transaction direction ('in' or 'out')
        enrichment: EnrichmentResult object with enrichment data
        provider: LLM provider name
        model: LLM model name
    """
    with get_session() as session:
        try:
            enrichment_json = json.dumps(
                {
                    "primary_category": enrichment.primary_category,
                    "subcategory": enrichment.subcategory,
                    "merchant_clean_name": enrichment.merchant_clean_name,
                    "merchant_type": enrichment.merchant_type,
                    "essential_discretionary": enrichment.essential_discretionary,
                    "payment_method": enrichment.payment_method,
                    "payment_method_subtype": enrichment.payment_method_subtype,
                    "confidence_score": enrichment.confidence_score,
                    "llm_provider": provider,
                    "llm_model": model,
                }
            )

            # Check if exists
            existing = (
                session.query(EnrichmentCache)
                .filter(
                    EnrichmentCache.transaction_description == description,
                    EnrichmentCache.transaction_direction == direction,
                )
                .first()
            )

            if existing:
                existing.enrichment_data = enrichment_json
                existing.cached_at = func.current_timestamp()
            else:
                new_cache = EnrichmentCache(
                    transaction_description=description,
                    transaction_direction=direction,
                    enrichment_data=enrichment_json,
                )
                session.add(new_cache)

            session.commit()
        except Exception:
            # Silently fail on cache errors
            session.rollback()


def log_enrichment_failure(transaction_id, error_message, retry_count=0, **kwargs):
    """
    Log enrichment failure for a transaction.

    NOTE: The llm_enrichment_failures table does not exist in the schema.
    This function exists for API compatibility but will silently fail.

    Args:
        transaction_id: ID of transaction that failed
        error_message: Error message explaining the failure
        retry_count: Number of retry attempts already made
        **kwargs: Additional optional parameters (description, error_type, provider) for compatibility
    """
    # Table doesn't exist - silent no-op for API compatibility


def get_category_keywords():
    """Get all custom keywords from database grouped by category."""
    with get_session() as session:
        keywords = session.query(CategoryKeyword).order_by(
            CategoryKeyword.category_name, CategoryKeyword.keyword
        )

        keywords_by_category = {}
        for kw in keywords:
            category = kw.category_name
            keyword = kw.keyword
            if category not in keywords_by_category:
                keywords_by_category[category] = []
            keywords_by_category[category].append(keyword)

        return keywords_by_category


def add_category_keyword(category_name, keyword):
    """Add a keyword to a category."""
    with get_session() as session:
        try:
            new_keyword = CategoryKeyword(
                category_name=category_name, keyword=keyword.lower()
            )
            session.add(new_keyword)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False


def remove_category_keyword(category_name, keyword):
    """Remove a keyword from a category."""
    with get_session() as session:
        deleted = (
            session.query(CategoryKeyword)
            .filter(
                CategoryKeyword.category_name == category_name,
                CategoryKeyword.keyword == keyword.lower(),
            )
            .delete()
        )
        session.commit()
        return deleted > 0


def create_custom_category(name):
    """Create a new custom category."""
    with get_session() as session:
        try:
            new_category = Category(name=name)
            session.add(new_category)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False


def delete_custom_category(name):
    """Delete a custom category and all its keywords."""
    # Don't allow deletion of default categories
    default_categories = [
        "Groceries",
        "Transport",
        "Dining",
        "Entertainment",
        "Utilities",
        "Shopping",
        "Health",
        "Income",
        "Other",
    ]

    if name in default_categories:
        return False

    with get_session() as session:
        # Delete keywords first
        session.query(CategoryKeyword).filter(
            CategoryKeyword.category_name == name
        ).delete()

        # Delete category
        deleted = session.query(Category).filter(Category.name == name).delete()
        session.commit()
        return deleted > 0


def get_all_account_mappings():
    """Get all account mappings from database."""
    with get_session() as session:
        mappings = session.query(AccountMapping).order_by(AccountMapping.friendly_name)
        return [
            {
                "id": mapping.id,
                "sort_code": mapping.sort_code,
                "account_number": mapping.account_number,
                "friendly_name": mapping.friendly_name,
                "created_at": mapping.created_at,
            }
            for mapping in mappings
        ]


def add_account_mapping(sort_code, account_number, friendly_name):
    """Add a new account mapping."""
    with get_session() as session:
        try:
            new_mapping = AccountMapping(
                sort_code=sort_code,
                account_number=account_number,
                friendly_name=friendly_name,
            )
            session.add(new_mapping)
            session.commit()
            return new_mapping.id
        except IntegrityError:
            session.rollback()
            return None


def update_account_mapping(mapping_id, friendly_name):
    """Update the friendly name for an account mapping."""
    with get_session() as session:
        mapping = session.get(AccountMapping, mapping_id)
        if mapping:
            mapping.friendly_name = friendly_name
            session.commit()
            return True
        return False


def delete_account_mapping(mapping_id):
    """Delete an account mapping."""
    with get_session() as session:
        mapping = session.get(AccountMapping, mapping_id)
        if mapping:
            session.delete(mapping)
            session.commit()
            return True
        return False


def get_account_mapping_by_details(sort_code, account_number):
    """Look up account mapping by sort code and account number."""
    with get_session() as session:
        mapping = (
            session.query(AccountMapping)
            .filter(
                AccountMapping.sort_code == sort_code,
                AccountMapping.account_number == account_number,
            )
            .first()
        )

        if mapping:
            return {
                "id": mapping.id,
                "sort_code": mapping.sort_code,
                "account_number": mapping.account_number,
                "friendly_name": mapping.friendly_name,
                "created_at": mapping.created_at,
            }
        return None


def update_truelayer_transaction_merchant(transaction_id, merchant_name):
    """Update merchant_name for a TrueLayer transaction."""
    with get_session() as session:
        txn = session.get(TrueLayerTransaction, transaction_id)
        if txn:
            txn.merchant_name = merchant_name
            session.commit()
            return True
        return False


def update_transaction_huququllah(transaction_id, classification):
    """Update Huququllah classification for TrueLayer transaction in metadata."""
    with get_session() as session:
        # Get transaction
        txn = session.get(TrueLayerTransaction, transaction_id)
        if not txn:
            return False

        # Update metadata
        if not txn.metadata:
            txn.metadata = {}
        txn.metadata["huququllah_classification"] = classification

        session.commit()
        return True


def get_unclassified_transactions():
    """Get TrueLayer transactions without Huququllah classification."""
    with get_session() as session:
        txns = (
            session.query(TrueLayerTransaction)
            .filter(
                TrueLayerTransaction.transaction_type == "DEBIT",
                TrueLayerTransaction.amount > 0,
            )
            .order_by(TrueLayerTransaction.timestamp.desc())
        )

        results = []
        for txn in txns:
            # Check if has classification in metadata
            classification = None
            if txn.metadata:
                classification = txn.metadata.get("huququllah_classification")

            if not classification:
                results.append(
                    {
                        "id": txn.id,
                        "date": txn.timestamp,
                        "description": txn.description,
                        "amount": txn.amount,
                        "currency": txn.currency,
                        "merchant": txn.merchant_name,
                        "metadata": txn.metadata,
                    }
                )

        return results


def get_huququllah_summary(date_from=None, date_to=None):
    """Calculate Huququllah obligations from TrueLayer transactions."""
    with get_session() as session:
        # Build query
        query = session.query(TrueLayerTransaction).filter(
            TrueLayerTransaction.transaction_type == "DEBIT",
            TrueLayerTransaction.amount > 0,
        )

        if date_from:
            query = query.filter(TrueLayerTransaction.timestamp >= date_from)

        if date_to:
            query = query.filter(TrueLayerTransaction.timestamp <= date_to)

        txns = query.all()

        # Calculate sums
        essential_expenses = 0
        discretionary_expenses = 0
        unclassified_count = 0

        for txn in txns:
            # Get classification from metadata (user override) or enrichment tables
            classification = None
            if txn.metadata:
                classification = txn.metadata.get("huququllah_classification")

            # If no user override, check enrichment tables
            if not classification:
                enrichment = get_combined_enrichment(txn.id)
                if enrichment:
                    essential_discretionary = enrichment.get("essential_discretionary")
                    if essential_discretionary:
                        classification = essential_discretionary.lower()

            if classification == "essential":
                essential_expenses += float(txn.amount)
            elif classification == "discretionary":
                discretionary_expenses += float(txn.amount)
            else:
                unclassified_count += 1

        huququllah = discretionary_expenses * 0.19

        return {
            "essential_expenses": round(essential_expenses, 2),
            "discretionary_expenses": round(discretionary_expenses, 2),
            "huququllah_due": round(huququllah, 2),
            "unclassified_count": unclassified_count,
        }


def get_transaction_by_id(transaction_id):
    """Get a single transaction by ID with computed huququllah_classification."""
    with get_session() as session:
        txn = session.get(TrueLayerTransaction, transaction_id)
        if not txn:
            return None

        # Compute huququllah_classification from metadata (user override) or enrichment tables
        classification = None
        if txn.metadata:
            classification = txn.metadata.get("huququllah_classification")

        # If no user override, check enrichment tables
        if not classification:
            enrichment = get_combined_enrichment(txn.id)
            if enrichment:
                essential_discretionary = enrichment.get("essential_discretionary")
                if essential_discretionary:
                    classification = essential_discretionary.lower()

        return {
            "id": txn.id,
            "timestamp": txn.timestamp,
            "description": txn.description,
            "amount": txn.amount,
            "currency": txn.currency,
            "transaction_type": txn.transaction_type,
            "category": txn.transaction_category,
            "merchant": txn.merchant_name,
            "metadata": txn.metadata,
            "huququllah_classification": classification,
        }


def get_all_transactions():
    """Get all transactions with computed huququllah_classification."""
    with get_session() as session:
        txns = session.query(TrueLayerTransaction).order_by(
            TrueLayerTransaction.timestamp.desc()
        )

        results = []
        for txn in txns:
            # Compute huququllah_classification from metadata (user override) or enrichment tables
            classification = None
            if txn.metadata:
                classification = txn.metadata.get("huququllah_classification")

            # If no user override, check enrichment tables
            if not classification:
                enrichment = get_combined_enrichment(txn.id)
                if enrichment:
                    essential_discretionary = enrichment.get("essential_discretionary")
                    if essential_discretionary:
                        classification = essential_discretionary.lower()

            results.append(
                {
                    "id": txn.id,
                    "timestamp": txn.timestamp,
                    "description": txn.description,
                    "amount": txn.amount,
                    "currency": txn.currency,
                    "transaction_type": txn.transaction_type,
                    "category": txn.transaction_category,
                    "merchant": txn.merchant_name,
                    "metadata": txn.metadata,
                    "huququllah_classification": classification,
                }
            )

        return results


# ============================================================================
