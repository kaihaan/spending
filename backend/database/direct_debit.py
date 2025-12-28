"""
Direct Debit Mapping - Database Operations

Handles mapping between merchant names in bank statements and normalized names
for direct debit transactions.

Migrated to SQLAlchemy from psycopg2.
"""

from sqlalchemy import func

from .base import get_session
from .models.category import MerchantNormalization
from .models.truelayer import TrueLayerTransaction

# ============================================================================
# DIRECT DEBIT MAPPING FUNCTIONS
# ============================================================================


def get_direct_debit_payees() -> list:
    """
    Extract unique payees from DIRECT DEBIT transactions.

    Uses the pattern extractor to parse payee names from transaction descriptions.
    Groups by payee and includes transaction counts and current enrichment status.

    Returns:
        List of payee dictionaries with:
        - payee: Extracted payee name
        - transaction_count: Number of transactions
        - sample_description: Example transaction description
        - current_category: Most common category for this payee
        - current_subcategory: Most common subcategory for this payee
        - mapping_id: ID of existing mapping if configured
    """
    # Import pattern extractor here to avoid circular imports
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    with get_session() as session:
        # Get all direct debit transactions
        txns = (
            session.query(TrueLayerTransaction)
            .filter(TrueLayerTransaction.description.like("DIRECT DEBIT PAYMENT TO%"))
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )

        # Group by extracted payee
        payee_data = {}
        for txn in txns:
            extracted = extract_variables(txn.description)
            payee = extracted.get("payee")

            # Fallback extraction if strict pattern fails
            if not payee:
                extracted = extract_direct_debit_payee_fallback(txn.description)
                payee = extracted.get("payee")

            if payee:
                payee_upper = payee.upper().strip()

                # Extract enrichment data from JSONB metadata
                category = None
                subcategory = None
                if txn.metadata and "enrichment" in txn.metadata:
                    category = txn.metadata["enrichment"].get("primary_category")
                    subcategory = txn.metadata["enrichment"].get("subcategory")

                if payee_upper not in payee_data:
                    payee_data[payee_upper] = {
                        "payee": payee.strip(),
                        "transaction_count": 0,
                        "sample_description": txn.description,
                        "categories": {},
                        "subcategories": {},
                    }
                payee_data[payee_upper]["transaction_count"] += 1

                # Track category frequency
                cat = category or "Uncategorized"
                payee_data[payee_upper]["categories"][cat] = (
                    payee_data[payee_upper]["categories"].get(cat, 0) + 1
                )

                subcat = subcategory or "None"
                payee_data[payee_upper]["subcategories"][subcat] = (
                    payee_data[payee_upper]["subcategories"].get(subcat, 0) + 1
                )

        # Find existing mappings for these payees
        mappings_query = (
            session.query(MerchantNormalization)
            .filter(MerchantNormalization.source == "direct_debit")
            .order_by(MerchantNormalization.priority.desc())
            .all()
        )

        mappings = {
            norm.pattern.upper(): {
                "id": norm.id,
                "pattern": norm.pattern,
                "normalized_name": norm.normalized_name,
                "default_category": norm.default_category,
                "merchant_type": norm.merchant_type,
            }
            for norm in mappings_query
        }

        # Build result list
        result = []
        for payee_upper, data in payee_data.items():
            # Find most common category/subcategory
            most_common_cat = max(
                data["categories"].keys(), key=lambda k: data["categories"][k]
            )
            most_common_subcat = max(
                data["subcategories"].keys(), key=lambda k: data["subcategories"][k]
            )

            payee_info = {
                "payee": data["payee"],
                "transaction_count": data["transaction_count"],
                "sample_description": data["sample_description"],
                "current_category": most_common_cat
                if most_common_cat != "Uncategorized"
                else None,
                "current_subcategory": most_common_subcat
                if most_common_subcat != "None"
                else None,
                "mapping_id": None,
                "mapped_name": None,
                "mapped_category": None,
                "mapped_subcategory": None,
            }

            # Check if there's an existing mapping
            if payee_upper in mappings:
                mapping = mappings[payee_upper]
                payee_info["mapping_id"] = mapping["id"]
                payee_info["mapped_name"] = mapping["normalized_name"]
                payee_info["mapped_category"] = mapping["default_category"]
                payee_info["mapped_subcategory"] = mapping[
                    "normalized_name"
                ]  # Subcategory = normalized name

            result.append(payee_info)

        # Sort alphabetically by payee name
        result.sort(key=lambda x: x["payee"].upper())
        return result


def get_direct_debit_mappings() -> list:
    """
    Fetch merchant normalizations configured for direct debit payees.

    Returns:
        List of mapping dictionaries
    """
    with get_session() as session:
        mappings = (
            session.query(MerchantNormalization)
            .filter(MerchantNormalization.source == "direct_debit")
            .order_by(
                MerchantNormalization.priority.desc(),
                MerchantNormalization.pattern.asc(),
            )
            .all()
        )

        return [
            {
                "id": m.id,
                "pattern": m.pattern,
                "pattern_type": m.pattern_type,
                "normalized_name": m.normalized_name,
                "merchant_type": m.merchant_type,
                "default_category": m.default_category,
                "priority": m.priority,
                "source": m.source,
                "usage_count": m.usage_count,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            }
            for m in mappings
        ]


def save_direct_debit_mapping(
    payee_pattern: str,
    normalized_name: str,
    category: str,
    subcategory: str = None,
    merchant_type: str = None,
) -> int:
    """
    Save a direct debit payee mapping.

    Creates or updates a merchant_normalization entry with source='direct_debit'.

    Args:
        payee_pattern: Pattern to match (the extracted payee name)
        normalized_name: Clean merchant name
        category: Category to assign
        subcategory: Optional subcategory (stored in metadata)
        merchant_type: Optional merchant type

    Returns:
        ID of the created/updated mapping
    """
    from sqlalchemy.dialects.postgresql import insert

    with get_session() as session:
        # Use upsert to create or update
        stmt = (
            insert(MerchantNormalization)
            .values(
                pattern=payee_pattern.upper(),
                pattern_type="exact",
                normalized_name=normalized_name,
                merchant_type=merchant_type,
                default_category=category,
                priority=100,
                source="direct_debit",
            )
            .on_conflict_do_update(
                index_elements=["pattern", "pattern_type"],
                set_={
                    "normalized_name": normalized_name,
                    "merchant_type": merchant_type,
                    "default_category": category,
                    "priority": 100,
                    "source": "direct_debit",
                    "updated_at": func.now(),
                },
            )
            .returning(MerchantNormalization.id)
        )

        result = session.execute(stmt)
        mapping_id = result.scalar_one()
        session.commit()
        return mapping_id


def delete_direct_debit_mapping(mapping_id: int) -> bool:
    """
    Delete a direct debit mapping.

    Args:
        mapping_id: ID of the mapping to delete

    Returns:
        True if deleted successfully
    """
    with get_session() as session:
        deleted = (
            session.query(MerchantNormalization)
            .filter(
                MerchantNormalization.id == mapping_id,
                MerchantNormalization.source == "direct_debit",
            )
            .delete()
        )
        session.commit()
        return deleted > 0


def apply_direct_debit_mappings() -> dict:
    """
    Re-enrich all direct debit transactions using current mappings.

    For each direct debit transaction:
    1. Extract payee using pattern extractor
    2. Match against merchant_normalizations with source='direct_debit'
    3. Apply enrichment data to matching transactions

    Returns:
        Dict with: updated_count, transactions (list of updated IDs)
    """
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    with get_session() as session:
        # Get all direct debit mappings
        mappings_query = (
            session.query(MerchantNormalization)
            .filter(MerchantNormalization.source == "direct_debit")
            .all()
        )

        mappings = {
            norm.pattern.upper(): {
                "id": norm.id,
                "pattern": norm.pattern,
                "normalized_name": norm.normalized_name,
                "merchant_type": norm.merchant_type,
                "default_category": norm.default_category,
            }
            for norm in mappings_query
        }

        if not mappings:
            return {"updated_count": 0, "transactions": []}

        # Get direct debit transactions
        txns = (
            session.query(TrueLayerTransaction)
            .filter(TrueLayerTransaction.description.like("DIRECT DEBIT PAYMENT TO%"))
            .all()
        )

        updated_ids = []
        for txn in txns:
            extracted = extract_variables(txn.description)
            payee = extracted.get("payee")

            # Fallback extraction if strict pattern fails
            if not payee:
                extracted = extract_direct_debit_payee_fallback(txn.description)
                payee = extracted.get("payee")

            if payee and payee.upper() in mappings:
                mapping = mappings[payee.upper()]

                # Build enrichment data
                metadata = txn.metadata or {}
                enrichment = metadata.get("enrichment", {})
                enrichment.update(
                    {
                        "primary_category": mapping["default_category"],
                        "subcategory": mapping[
                            "normalized_name"
                        ],  # Use merchant as subcategory
                        "merchant_clean_name": mapping["normalized_name"],
                        "merchant_type": mapping.get("merchant_type"),
                        "confidence_score": 1.0,
                        "llm_model": "direct_debit_rule",
                        "enrichment_source": "rule",
                    }
                )
                metadata["enrichment"] = enrichment

                # Update transaction metadata
                txn.metadata = metadata
                updated_ids.append(txn.id)

        session.commit()
        return {"updated_count": len(updated_ids), "transactions": updated_ids}


def detect_new_direct_debits() -> dict:
    """
    Detect new direct debit payees that haven't been mapped yet.

    Returns:
        {
            'new_payees': [{'payee': str, 'first_seen': str, 'transaction_count': int, 'mandate_numbers': list}],
            'total_unmapped': int
        }
    """
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    with get_session() as session:
        # Get all mapped payees
        mapped_patterns = (
            session.query(func.upper(MerchantNormalization.pattern))
            .filter(MerchantNormalization.source == "direct_debit")
            .all()
        )
        mapped_payees = {pattern[0] for pattern in mapped_patterns}

        # Get all direct debit transactions
        txns = (
            session.query(
                TrueLayerTransaction.description, TrueLayerTransaction.timestamp
            )
            .filter(TrueLayerTransaction.description.like("DIRECT DEBIT PAYMENT TO%"))
            .order_by(TrueLayerTransaction.timestamp.asc())
            .all()
        )

        # Track payees and their mandates
        payee_info = {}  # payee -> {first_seen, mandates: set(), count}

        for txn in txns:
            extracted = extract_variables(txn.description)
            if not extracted.get("payee"):
                extracted = extract_direct_debit_payee_fallback(txn.description)

            payee = extracted.get("payee")
            if not payee:
                continue

            payee_upper = payee.upper().strip()
            mandate = extracted.get("mandate_number")

            if payee_upper not in payee_info:
                payee_info[payee_upper] = {
                    "payee": payee.strip(),
                    "first_seen": txn.timestamp,
                    "mandates": set(),
                    "count": 0,
                }

            payee_info[payee_upper]["count"] += 1
            if mandate:
                payee_info[payee_upper]["mandates"].add(mandate)

        # Find unmapped payees
        new_payees = []
        for payee_upper, info in payee_info.items():
            if payee_upper not in mapped_payees:
                new_payees.append(
                    {
                        "payee": info["payee"],
                        "first_seen": info["first_seen"].isoformat()
                        if info["first_seen"]
                        else None,
                        "transaction_count": info["count"],
                        "mandate_numbers": list(info["mandates"]),
                    }
                )

        return {
            "new_payees": sorted(new_payees, key=lambda x: x["payee"].upper()),
            "total_unmapped": len(new_payees),
        }


# ============================================================================
