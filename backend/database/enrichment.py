"""
Transaction Enrichment - Database Operations

Handles multi-source transaction enrichment, enrichment status tracking,
and enrichment job management.
"""

from .base import get_db
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


# ============================================================================
# MULTI-SOURCE ENRICHMENT FUNCTIONS
# ============================================================================

def add_enrichment_source(
    transaction_id: int,
    source_type: str,
    description: str,
    source_id: int = None,
    order_id: str = None,
    line_items: list = None,
    confidence: int = 100,
    match_method: str = None,
    is_primary: bool = None
) -> int:
    """
    Add an enrichment source for a transaction.
    Does NOT overwrite existing sources - adds a new one.

    Args:
        transaction_id: TrueLayer transaction ID
        source_type: One of 'amazon', 'amazon_business', 'apple', 'gmail', 'manual'
        description: Product/service description from source
        source_id: FK to source table (amazon_orders.id, etc.)
        order_id: Original order/receipt ID
        line_items: Detailed items [{name, quantity, price}]
        confidence: Match confidence 0-100
        match_method: How the match was determined
        is_primary: If True, set as primary. If None, only set as primary if no other sources exist.

    Returns:
        ID of the created enrichment source, or existing ID if duplicate
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Determine if this should be primary
            if is_primary is None:
                # Check if any sources already exist for this transaction
                cursor.execute('''
                    SELECT COUNT(*) FROM transaction_enrichment_sources
                    WHERE truelayer_transaction_id = %s
                ''', (transaction_id,))
                existing_count = cursor.fetchone()[0]
                is_primary = existing_count == 0

            cursor.execute('''
                INSERT INTO transaction_enrichment_sources
                    (truelayer_transaction_id, source_type, source_id, description,
                     order_id, line_items, match_confidence, match_method, is_primary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (truelayer_transaction_id, source_type, source_id)
                DO UPDATE SET
                    description = EXCLUDED.description,
                    order_id = EXCLUDED.order_id,
                    line_items = EXCLUDED.line_items,
                    match_confidence = EXCLUDED.match_confidence,
                    match_method = EXCLUDED.match_method,
                    updated_at = NOW()
                RETURNING id
            ''', (
                transaction_id,
                source_type,
                source_id,
                description,
                order_id,
                json.dumps(line_items) if line_items else None,
                confidence,
                match_method,
                is_primary
            ))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None


def get_transaction_enrichment_sources(transaction_id: int) -> list:
    """
    Get all enrichment sources for a transaction, ordered by primary then confidence.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        List of enrichment source dicts
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT
                    id, source_type, source_id, description, order_id,
                    line_items, match_confidence, match_method,
                    is_primary, user_verified, created_at
                FROM transaction_enrichment_sources
                WHERE truelayer_transaction_id = %s
                ORDER BY is_primary DESC, match_confidence DESC, created_at ASC
            ''', (transaction_id,))
            return [dict(row) for row in cursor.fetchall()]


def get_all_enrichment_sources_for_transactions(transaction_ids: list) -> dict:
    """
    Batch fetch enrichment sources for multiple transactions.

    Args:
        transaction_ids: List of TrueLayer transaction IDs

    Returns:
        Dict mapping transaction_id -> list of enrichment sources
    """
    if not transaction_ids:
        return {}

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT
                    truelayer_transaction_id, id, source_type, source_id,
                    description, order_id, line_items, match_confidence,
                    match_method, is_primary, user_verified
                FROM transaction_enrichment_sources
                WHERE truelayer_transaction_id = ANY(%s)
                ORDER BY truelayer_transaction_id, is_primary DESC, match_confidence DESC
            ''', (transaction_ids,))

            result = {}
            for row in cursor.fetchall():
                txn_id = row['truelayer_transaction_id']
                if txn_id not in result:
                    result[txn_id] = []
                result[txn_id].append(dict(row))
            return result


def set_primary_enrichment_source(transaction_id: int, source_id: int) -> bool:
    """
    Set a specific enrichment source as primary for a transaction.
    Unsets any other primary source for the same transaction.

    Args:
        transaction_id: TrueLayer transaction ID
        source_id: Enrichment source ID to set as primary

    Returns:
        True if successful, False if source not found
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            # The trigger will handle unsetting other primaries
            cursor.execute('''
                UPDATE transaction_enrichment_sources
                SET is_primary = TRUE
                WHERE id = %s AND truelayer_transaction_id = %s
            ''', (source_id, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def get_primary_enrichment_description(transaction_id: int) -> str:
    """
    Get the primary enrichment description for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Primary description string, or None if no sources
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT description
                FROM transaction_enrichment_sources
                WHERE truelayer_transaction_id = %s
                ORDER BY is_primary DESC, match_confidence DESC
                LIMIT 1
            ''', (transaction_id,))
            row = cursor.fetchone()
            return row[0] if row else None


def get_llm_enrichment_context(transaction_id: int) -> str:
    """
    Get combined context string from all enrichment sources for LLM prompt.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Combined string with all sources labeled, e.g.:
        "Amazon Products: iPhone 15 Pro | Email Receipt: Order #123 confirmed"
    """
    sources = get_transaction_enrichment_sources(transaction_id)
    if not sources:
        return None

    labels = {
        'amazon': 'Amazon Products',
        'amazon_business': 'Amazon Business',
        'apple': 'Apple/App Store',
        'gmail': 'Email Receipt',
        'manual': 'Manual'
    }

    parts = []
    for source in sources:
        label = labels.get(source['source_type'], 'Details')
        parts.append(f"{label}: {source['description']}")

    return ' | '.join(parts)


def get_batch_llm_enrichment_context(transaction_ids: list) -> dict:
    """
    Batch fetch LLM enrichment context for multiple transactions.

    Args:
        transaction_ids: List of TrueLayer transaction IDs

    Returns:
        Dict mapping transaction_id -> combined context string
    """
    all_sources = get_all_enrichment_sources_for_transactions(transaction_ids)

    labels = {
        'amazon': 'Amazon Products',
        'amazon_business': 'Amazon Business',
        'apple': 'Apple/App Store',
        'gmail': 'Email Receipt',
        'manual': 'Manual'
    }

    result = {}
    for txn_id, sources in all_sources.items():
        parts = []
        for source in sources:
            label = labels.get(source['source_type'], 'Details')
            parts.append(f"{label}: {source['description']}")
        result[txn_id] = ' | '.join(parts) if parts else None

    return result


def delete_enrichment_source(source_id: int) -> bool:
    """
    Delete an enrichment source by ID.

    Args:
        source_id: Enrichment source ID

    Returns:
        True if deleted, False if not found
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                DELETE FROM transaction_enrichment_sources WHERE id = %s
            ''', (source_id,))
            conn.commit()
            return cursor.rowcount > 0


def get_enrichment_source_full_details(enrichment_source_id: int) -> dict | None:
    """
    Fetch full details from the source table for an enrichment source.

    Uses the polymorphic FK pattern (source_type + source_id) to query
    the appropriate source table (amazon_orders, apple_transactions, etc.)

    Args:
        enrichment_source_id: ID from transaction_enrichment_sources table

    Returns:
        Dict with enrichment source metadata plus full details from source table,
        or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # First, get the enrichment source record
            cursor.execute('''
                SELECT id, truelayer_transaction_id, source_type, source_id,
                       description, order_id, line_items, match_confidence,
                       match_method, is_primary, user_verified, created_at
                FROM transaction_enrichment_sources
                WHERE id = %s
            ''', (enrichment_source_id,))
            enrichment_source = cursor.fetchone()

            if not enrichment_source:
                return None

            result = dict(enrichment_source)
            source_type = enrichment_source['source_type']
            source_id = enrichment_source['source_id']

            # If no source_id (manual entry), return just the enrichment data
            if source_id is None:
                result['source_details'] = None
                return result

            # Fetch full details from the appropriate source table
            if source_type == 'amazon':
                cursor.execute('''
                    SELECT id, order_id, order_date, website, currency, total_owed,
                           product_names, order_status, shipment_status, source_file,
                           created_at
                    FROM amazon_orders
                    WHERE id = %s
                ''', (source_id,))
                source_details = cursor.fetchone()
                if source_details:
                    # Parse product_names into line items if not already in enrichment
                    source_details = dict(source_details)
                    if source_details.get('product_names'):
                        items = [{'name': name.strip(), 'quantity': 1}
                                 for name in source_details['product_names'].split(',')]
                        source_details['parsed_line_items'] = items

            elif source_type == 'amazon_business':
                cursor.execute('''
                    SELECT id, order_id, order_date, region, purchase_order_number,
                           order_status, buyer_name, buyer_email, subtotal, tax,
                           shipping, net_total, currency, item_count, product_summary,
                           created_at
                    FROM amazon_business_orders
                    WHERE id = %s
                ''', (source_id,))
                source_details = cursor.fetchone()
                if source_details:
                    source_details = dict(source_details)
                    # Also fetch line items
                    cursor.execute('''
                        SELECT line_item_id, asin, title, brand, category,
                               quantity, unit_price, total_price, seller_name
                        FROM amazon_business_line_items
                        WHERE order_id = %s
                        ORDER BY id
                    ''', (source_details['order_id'],))
                    line_items = [dict(row) for row in cursor.fetchall()]
                    source_details['line_items'] = line_items

            elif source_type == 'apple':
                cursor.execute('''
                    SELECT id, order_id, order_date, total_amount, currency,
                           app_names, publishers, item_count, source_file, created_at
                    FROM apple_transactions
                    WHERE id = %s
                ''', (source_id,))
                source_details = cursor.fetchone()
                if source_details:
                    source_details = dict(source_details)
                    # Parse app_names into line items
                    if source_details.get('app_names'):
                        items = [{'name': name.strip(), 'quantity': 1}
                                 for name in source_details['app_names'].split(',')]
                        source_details['parsed_line_items'] = items

            elif source_type == 'gmail':
                cursor.execute('''
                    SELECT id, connection_id, message_id, thread_id, sender_email,
                           sender_name, subject, received_at, merchant_name,
                           merchant_domain, order_id, total_amount, currency_code,
                           receipt_date, line_items, parse_method, parse_confidence,
                           parsing_status, created_at
                    FROM gmail_receipts
                    WHERE id = %s
                ''', (source_id,))
                source_details = cursor.fetchone()
                if source_details:
                    source_details = dict(source_details)
                    # Also fetch PDF attachments if any
                    cursor.execute('''
                        SELECT id, filename, size_bytes, mime_type, object_key, created_at
                        FROM pdf_attachments
                        WHERE gmail_receipt_id = %s
                        ORDER BY created_at
                    ''', (source_id,))
                    pdf_attachments = [dict(row) for row in cursor.fetchall()]
                    source_details['pdf_attachments'] = pdf_attachments

            else:
                source_details = None

            result['source_details'] = source_details
            return result


def clear_amazon_orders():
    """Delete all Amazon orders and matches from database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Count before deletion
            cursor.execute('SELECT COUNT(*) FROM amazon_orders')
            orders_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM amazon_transaction_matches')
            matches_count = cursor.fetchone()[0]

            # Delete matches first (foreign key)
            cursor.execute('DELETE FROM amazon_transaction_matches')

            # Delete orders
            cursor.execute('DELETE FROM amazon_orders')

            conn.commit()
            return (orders_count, matches_count)


# ============================================================================


# ============================================================================
# PRE-ENRICHMENT STATUS FUNCTIONS
# ============================================================================



# ============================================================================
# ENRICHMENT REQUIRED FUNCTIONS
# ============================================================================


def toggle_enrichment_required(transaction_id: int) -> dict:
    """Toggle the enrichment_required flag for a transaction.

    Args:
        transaction_id: ID of the transaction to toggle

    Returns:
        Dict with new state: {id, enrichment_required, enrichment_source}
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Toggle the flag and return new state
            cursor.execute('''
                UPDATE truelayer_transactions
                SET enrichment_required = NOT COALESCE(enrichment_required, FALSE)
                WHERE id = %s
                RETURNING id, enrichment_required,
                    metadata->'enrichment'->>'llm_provider' as enrichment_source
            ''', (transaction_id,))
            result = cursor.fetchone()
            conn.commit()

            if result:
                return dict(result)
            return None


def set_enrichment_required(transaction_id: int, required: bool) -> bool:
    """Set enrichment_required status for a transaction.

    Args:
        transaction_id: ID of the transaction
        required: Whether enrichment is required

    Returns:
        True if updated successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_transactions
                SET enrichment_required = %s
                WHERE id = %s
            ''', (required, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def get_required_unenriched_transactions(limit: int = None) -> list:
    """Get transactions where enrichment_required=TRUE AND not yet enriched.

    Args:
        limit: Optional limit on number of transactions to return

    Returns:
        List of transaction dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT t.*
                FROM truelayer_transactions t
                WHERE t.enrichment_required = TRUE
                  AND (t.metadata->'enrichment' IS NULL
                       OR t.metadata->'enrichment'->>'primary_category' IS NULL)
                ORDER BY t.timestamp DESC
            '''
            if limit:
                query += f' LIMIT {int(limit)}'

            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]


def clear_enrichment_required_after_success(transaction_id: int) -> bool:
    """Clear enrichment_required flag after successful enrichment.

    Called automatically after enrichment completes.

    Args:
        transaction_id: ID of the transaction

    Returns:
        True if updated successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_transactions
                SET enrichment_required = FALSE
                WHERE id = %s
            ''', (transaction_id,))
            conn.commit()
            return cursor.rowcount > 0


# ============================================================================
