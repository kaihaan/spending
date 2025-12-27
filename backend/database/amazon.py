"""
Amazon Integration - Database Operations

Handles all database operations for Amazon orders, returns, and business accounts.
Includes matching logic for linking Amazon purchases to bank transactions.
"""

from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from .base import get_db

# ============================================================================
# AMAZON ORDER MANAGEMENT FUNCTIONS
# ============================================================================


def import_amazon_orders(orders, source_file):
    """Bulk import Amazon orders into database."""
    imported = 0
    duplicates = 0

    with get_db() as conn, conn.cursor() as cursor:
        for order in orders:
            try:
                cursor.execute(
                    """
                        INSERT INTO amazon_orders
                        (order_id, order_date, website, currency, total_owed,
                         product_names, order_status, shipment_status, source_file)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order["order_id"],
                        order["order_date"],
                        order["website"],
                        order["currency"],
                        order["total_owed"],
                        order["product_names"],
                        order.get("order_status"),
                        order.get("shipment_status"),
                        source_file,
                    ),
                )
                imported += 1
            except psycopg2.IntegrityError:
                conn.rollback()  # Reset transaction state before continuing
                duplicates += 1
                continue

        conn.commit()
    return (imported, duplicates)


def get_amazon_orders(date_from=None, date_to=None, website=None):
    """Get Amazon orders with optional filters."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        query = "SELECT * FROM amazon_orders WHERE 1=1"
        params = []

        if date_from:
            query += " AND order_date >= %s"
            params.append(date_from)

        if date_to:
            query += " AND order_date <= %s"
            params.append(date_to)

        if website:
            query += " AND website = %s"
            params.append(website)

        query += " ORDER BY order_date DESC"

        cursor.execute(query, params)
        return cursor.fetchall()


def get_amazon_order_by_id(order_id):
    """Get a single Amazon order by its Amazon order ID."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM amazon_orders WHERE order_id = %s", (order_id,))
        return cursor.fetchone()


def get_unmatched_truelayer_amazon_transactions():
    """Get all TrueLayer transactions with Amazon merchant that haven't been matched."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, account_id, transaction_id, normalised_provider_transaction_id,
                       timestamp as date, description, amount, currency, transaction_type,
                       transaction_category, merchant_name as merchant, running_balance, metadata, created_at
                FROM truelayer_transactions tt
                WHERE (
                    UPPER(merchant_name) LIKE '%AMAZON%'
                    OR UPPER(merchant_name) LIKE '%AMZN%'
                    OR UPPER(description) LIKE '%AMAZON%'
                    OR UPPER(description) LIKE '%AMZN%'
                )
                AND NOT EXISTS (
                    SELECT 1 FROM truelayer_amazon_transaction_matches tatm
                    WHERE tatm.truelayer_transaction_id = tt.id
                )
                ORDER BY timestamp DESC
            """)
            return cursor.fetchall()


def get_truelayer_transaction_for_matching(transaction_id):
    """Get a TrueLayer transaction by ID for matching purposes."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, account_id, transaction_id, normalised_provider_transaction_id,
                       timestamp as date, description, amount, currency, transaction_type,
                       transaction_category, merchant_name as merchant, running_balance, metadata, created_at
                FROM truelayer_transactions
                WHERE id = %s
            """,
                (transaction_id,),
            )
            return cursor.fetchone()


def match_truelayer_amazon_transaction(
    truelayer_transaction_id, amazon_order_db_id, confidence
):
    """
    Record a match between a TrueLayer transaction and an Amazon order.
    Stores in dedicated truelayer_amazon_transaction_matches table
    and adds to transaction_enrichment_sources for multi-source display.

    Args:
        truelayer_transaction_id: TrueLayer transaction ID
        amazon_order_db_id: Amazon order database ID
        confidence: Match confidence score (0-100)

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                # Store the match in legacy table
                cursor.execute(
                    """
                    INSERT INTO truelayer_amazon_transaction_matches
                    (truelayer_transaction_id, amazon_order_id, match_confidence)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (truelayer_transaction_id) DO UPDATE
                    SET amazon_order_id = EXCLUDED.amazon_order_id,
                        match_confidence = EXCLUDED.match_confidence,
                        matched_at = NOW()
                """,
                    (truelayer_transaction_id, amazon_order_db_id, confidence),
                )

                # Get order details for enrichment source
                cursor.execute(
                    """
                    SELECT product_names, order_id FROM amazon_orders WHERE id = %s
                """,
                    (amazon_order_db_id,),
                )
                order_row = cursor.fetchone()

                if order_row and order_row[0]:
                    product_names, order_id = order_row

                    # Add to multi-source enrichment table (Amazon is always primary)
                    cursor.execute(
                        """
                        INSERT INTO transaction_enrichment_sources
                            (truelayer_transaction_id, source_type, source_id, description,
                             order_id, match_confidence, match_method, is_primary)
                        VALUES (%s, 'amazon', %s, %s, %s, %s, 'amount_date_match', TRUE)
                        ON CONFLICT (truelayer_transaction_id, source_type, source_id)
                        DO UPDATE SET
                            description = EXCLUDED.description,
                            order_id = EXCLUDED.order_id,
                            match_confidence = EXCLUDED.match_confidence,
                            updated_at = NOW()
                    """,
                        (
                            truelayer_transaction_id,
                            amazon_order_db_id,
                            product_names,
                            order_id,
                            confidence,
                        ),
                    )

                conn.commit()
                return True
            except Exception as e:
                print(f"Error matching TrueLayer transaction: {e}")
                conn.rollback()
                return False


def get_unmatched_truelayer_apple_transactions():
    """Get TrueLayer transactions with Apple merchant that haven't been matched."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, account_id, transaction_id, timestamp as date,
                       description, amount, currency, merchant_name as merchant, metadata
                FROM truelayer_transactions tt
                WHERE (
                    UPPER(merchant_name) LIKE '%APPLE%'
                    OR UPPER(description) LIKE '%APPLE%'
                )
                AND NOT EXISTS (
                    SELECT 1 FROM truelayer_apple_transaction_matches tatm
                    WHERE tatm.truelayer_transaction_id = tt.id
                )
                ORDER BY timestamp DESC
            """)
            return cursor.fetchall()


def match_truelayer_apple_transaction(
    truelayer_transaction_id, apple_transaction_id, confidence
):
    """
    Record match between TrueLayer transaction and Apple purchase.
    Adds to transaction_enrichment_sources for multi-source display.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                # Store match in legacy table
                cursor.execute(
                    """
                    INSERT INTO truelayer_apple_transaction_matches
                    (truelayer_transaction_id, apple_transaction_id, match_confidence)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (truelayer_transaction_id) DO UPDATE
                    SET apple_transaction_id = EXCLUDED.apple_transaction_id,
                        match_confidence = EXCLUDED.match_confidence,
                        matched_at = NOW()
                """,
                    (truelayer_transaction_id, apple_transaction_id, confidence),
                )

                # Get Apple transaction details for enrichment source
                cursor.execute(
                    """
                    SELECT app_names, publishers, order_id FROM apple_transactions WHERE id = %s
                """,
                    (apple_transaction_id,),
                )
                apple_row = cursor.fetchone()

                if apple_row and apple_row[0]:
                    app_names, publishers, order_id = apple_row
                    description = app_names
                    if publishers:
                        description = f"{app_names} ({publishers})"

                    # Check if Amazon already has primary for this transaction
                    cursor.execute(
                        """
                        SELECT 1 FROM transaction_enrichment_sources
                        WHERE truelayer_transaction_id = %s AND source_type = 'amazon' AND is_primary = TRUE
                    """,
                        (truelayer_transaction_id,),
                    )
                    has_amazon_primary = cursor.fetchone() is not None

                    # Add to multi-source enrichment table
                    cursor.execute(
                        """
                        INSERT INTO transaction_enrichment_sources
                            (truelayer_transaction_id, source_type, source_id, description,
                             order_id, match_confidence, match_method, is_primary)
                        VALUES (%s, 'apple', %s, %s, %s, %s, 'amount_date_match', %s)
                        ON CONFLICT (truelayer_transaction_id, source_type, source_id)
                        DO UPDATE SET
                            description = EXCLUDED.description,
                            order_id = EXCLUDED.order_id,
                            match_confidence = EXCLUDED.match_confidence,
                            updated_at = NOW()
                    """,
                        (
                            truelayer_transaction_id,
                            apple_transaction_id,
                            description,
                            order_id,
                            confidence,
                            not has_amazon_primary,
                        ),
                    )

                conn.commit()
                return True
            except Exception as e:
                print(f"Error matching TrueLayer Apple transaction: {e}")
                conn.rollback()
                return False


def check_amazon_coverage(date_from, date_to):
    """Check if Amazon order data exists for a date range (TrueLayer transactions only)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Count Amazon TrueLayer transactions in range
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM truelayer_transactions
                WHERE timestamp >= %s AND timestamp <= %s
                AND (
                    UPPER(merchant_name) LIKE '%%AMAZON%%'
                    OR UPPER(merchant_name) LIKE '%%AMZN%%'
                    OR UPPER(description) LIKE '%%AMAZON%%'
                    OR UPPER(description) LIKE '%%AMZN%%'
                )
            """,
                (date_from, date_to),
            )
            amazon_txn_count = cursor.fetchone()["count"]

            # Count Amazon orders in range (with ±3 day buffer)
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM amazon_orders
                WHERE order_date >= (%s::date - interval '3 days')
                AND order_date <= (%s::date + interval '3 days')
            """,
                (date_from, date_to),
            )
            amazon_order_count = cursor.fetchone()["count"]

            # Count matched TrueLayer transactions
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM truelayer_transactions tt
                JOIN truelayer_amazon_transaction_matches m ON tt.id = m.truelayer_transaction_id
                WHERE tt.timestamp >= %s AND tt.timestamp <= %s
            """,
                (date_from, date_to),
            )
            matched_count = cursor.fetchone()["count"]

            return {
                "amazon_transactions": amazon_txn_count,
                "amazon_orders_available": amazon_order_count,
                "matched_count": matched_count,
                "has_coverage": amazon_order_count > 0,
                "match_rate": (matched_count / amazon_txn_count * 100)
                if amazon_txn_count > 0
                else 0,
            }


def get_amazon_statistics():
    """Get overall Amazon import and matching statistics (OPTIMIZED - single query)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Single query with subselects for all statistics
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM amazon_orders) as total_orders,
                    (SELECT MIN(order_date) FROM amazon_orders) as min_order_date,
                    (SELECT MAX(order_date) FROM amazon_orders) as max_order_date,
                    (SELECT COUNT(*) FROM truelayer_amazon_transaction_matches) as total_matched,
                    (SELECT COUNT(*) FROM truelayer_transactions tt
                     WHERE (UPPER(merchant_name) LIKE '%AMAZON%'
                            OR UPPER(merchant_name) LIKE '%AMZN%'
                            OR UPPER(description) LIKE '%AMAZON%'
                            OR UPPER(description) LIKE '%AMZN%')
                       AND NOT EXISTS (
                           SELECT 1 FROM truelayer_amazon_transaction_matches tatm
                           WHERE tatm.truelayer_transaction_id = tt.id
                       )
                    ) as total_unmatched
            """)

            result = dict(cursor.fetchone())

            # Format dates as strings for JSON serialization
            if result.get("min_order_date"):
                result["min_order_date"] = result["min_order_date"].isoformat()
            if result.get("max_order_date"):
                result["max_order_date"] = result["max_order_date"].isoformat()

            return result


# ============================================================================


# ============================================================================
# AMAZON RETURNS MANAGEMENT FUNCTIONS
# ============================================================================


def import_amazon_returns(returns, source_file):
    """Bulk import Amazon returns into database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            imported = 0
            duplicates = 0

            for ret in returns:
                try:
                    cursor.execute(
                        """
                        INSERT INTO amazon_returns
                        (order_id, reversal_id, refund_completion_date, currency, amount_refunded,
                         status, disbursement_type, source_file)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            ret["order_id"],
                            ret["reversal_id"],
                            ret["refund_completion_date"],
                            ret["currency"],
                            ret["amount_refunded"],
                            ret.get("status"),
                            ret.get("disbursement_type"),
                            source_file,
                        ),
                    )
                    imported += 1
                except psycopg2.IntegrityError:
                    conn.rollback()  # Reset transaction state before continuing
                    duplicates += 1
                    continue

            conn.commit()
    return (imported, duplicates)


def get_amazon_returns(order_id=None):
    """Get Amazon returns with optional order ID filter."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if order_id:
            cursor.execute(
                "SELECT * FROM amazon_returns WHERE order_id = %s", (order_id,)
            )
        else:
            cursor.execute(
                "SELECT * FROM amazon_returns ORDER BY refund_completion_date DESC"
            )

        return cursor.fetchall()


def link_return_to_transactions(
    return_id, original_transaction_id, refund_transaction_id
):
    """Link a return to its original purchase and refund transactions."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE amazon_returns
                SET original_transaction_id = %s,
                    refund_transaction_id = %s
                WHERE id = %s
            """,
            (original_transaction_id, refund_transaction_id, return_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_returns_statistics():
    """Get overall returns import and matching statistics (OPTIMIZED - single query)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Single query with subselects for all statistics
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM amazon_returns) as total_returns,
                    (SELECT MIN(refund_completion_date) FROM amazon_returns) as min_return_date,
                    (SELECT MAX(refund_completion_date) FROM amazon_returns) as max_return_date,
                    (SELECT COALESCE(SUM(amount_refunded), 0) FROM amazon_returns) as total_refunded,
                    (SELECT COUNT(*) FROM amazon_returns
                     WHERE original_transaction_id IS NOT NULL) as matched_returns,
                    (SELECT COUNT(*) FROM amazon_returns
                     WHERE original_transaction_id IS NULL) as unmatched_returns
            """)

            result = dict(cursor.fetchone())

            # Format dates and round total
            if result.get("min_return_date"):
                result["min_return_date"] = result["min_return_date"].isoformat()
            if result.get("max_return_date"):
                result["max_return_date"] = result["max_return_date"].isoformat()
            if result.get("total_refunded"):
                result["total_refunded"] = round(float(result["total_refunded"]), 2)

            return result


def clear_amazon_returns():
    """Delete all Amazon returns from database. Also removes [RETURNED] labels from transactions."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get all transactions marked as returned
        cursor.execute(
            "SELECT id, description FROM transactions WHERE description LIKE %s",
            ("[RETURNED] %",),
        )
        returned_txns = cursor.fetchall()

        # Remove [RETURNED] prefix
        for txn in returned_txns:
            new_desc = txn["description"].replace("[RETURNED] ", "", 1)
            cursor.execute(
                "UPDATE transactions SET description = %s WHERE id = %s",
                (new_desc, txn["id"]),
            )

        # Count and delete returns
        cursor.execute("SELECT COUNT(*) FROM amazon_returns")
        return_count = cursor.fetchone()[0]

        cursor.execute("DELETE FROM amazon_returns")
        conn.commit()

        return return_count


# ============================================================================


# ============================================================================
# AMAZON BUSINESS FUNCTIONS
# ============================================================================


def save_amazon_business_connection(
    access_token: str,
    refresh_token: str,
    expires_in: int,
    region: str = "UK",
    user_id: int = 1,
    marketplace_id: str = None,
    is_sandbox: bool = True,
) -> int:
    """Save Amazon SP-API OAuth connection.

    Args:
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        expires_in: Token expiry in seconds
        region: Amazon region (UK, US, DE, etc.)
        user_id: User ID (default 1)
        marketplace_id: Amazon marketplace ID (e.g., A1F83G8C2ARO7P for UK)
        is_sandbox: True for sandbox environment, False for production

    Returns:
        Connection ID
    """
    from datetime import timedelta

    expires_at = datetime.now() + timedelta(seconds=expires_in)

    # Set default marketplace ID if not provided
    if marketplace_id is None:
        marketplace_ids = {
            "UK": "A1F83G8C2ARO7P",
            "US": "ATVPDKIKX0DER",
            "DE": "A1PA6795UKMFR9",
        }
        marketplace_id = marketplace_ids.get(region, "A1F83G8C2ARO7P")

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO amazon_business_connections
                (user_id, access_token, refresh_token, token_expires_at, region,
                 marketplace_id, is_sandbox)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
            (
                user_id,
                access_token,
                refresh_token,
                expires_at,
                region,
                marketplace_id,
                is_sandbox,
            ),
        )
        connection_id = cursor.fetchone()[0]
        conn.commit()
        return connection_id


def get_amazon_business_connection(connection_id: int = None, user_id: int = 1) -> dict:
    """Get Amazon SP-API connection details.

    Args:
        connection_id: Specific connection ID, or None for user's active connection
        user_id: User ID (default 1)

    Returns:
        Connection dictionary or None
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if connection_id:
            cursor.execute(
                """
                    SELECT id, user_id, access_token, refresh_token, token_expires_at,
                           region, status, marketplace_id, is_sandbox, last_synced_at,
                           created_at, updated_at
                    FROM amazon_business_connections
                    WHERE id = %s
                """,
                (connection_id,),
            )
        else:
            cursor.execute(
                """
                    SELECT id, user_id, access_token, refresh_token, token_expires_at,
                           region, status, marketplace_id, is_sandbox, last_synced_at,
                           created_at, updated_at
                    FROM amazon_business_connections
                    WHERE user_id = %s AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                """,
                (user_id,),
            )
        return cursor.fetchone()


def update_amazon_business_tokens(
    connection_id: int, access_token: str, refresh_token: str, expires_at
) -> bool:
    """Update Amazon Business OAuth tokens after refresh.

    Args:
        connection_id: Connection ID
        access_token: New access token
        refresh_token: New refresh token (or existing if not changed)
        expires_at: Token expiry datetime

    Returns:
        True if update was successful
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE amazon_business_connections
                SET access_token = %s, refresh_token = %s, token_expires_at = %s,
                    updated_at = NOW()
                WHERE id = %s
            """,
            (access_token, refresh_token, expires_at, connection_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def import_amazon_business_orders(orders: list) -> tuple:
    """Import Amazon Business orders from API response.

    Args:
        orders: List of order dictionaries from Amazon Business API

    Returns:
        Tuple of (imported_count, duplicate_count)
    """
    imported = 0
    duplicates = 0

    with get_db() as conn:
        with conn.cursor() as cursor:
            for order in orders:
                # Extract charge amounts
                charges = order.get("charges", {})
                subtotal = charges.get("SUBTOTAL", {}).get("amount", 0)
                tax = charges.get("TAX", {}).get("amount", 0)
                shipping = charges.get("SHIPPING", {}).get("amount", 0)
                net_total = charges.get("NET_TOTAL", {}).get("amount", 0)

                # Extract buyer info
                buyer = order.get("buyingCustomer", {})
                buyer_name = buyer.get("name", "")
                buyer_email = buyer.get("email", "")

                cursor.execute(
                    """
                    INSERT INTO amazon_business_orders
                    (order_id, order_date, region, purchase_order_number, order_status,
                     buyer_name, buyer_email, subtotal, tax, shipping, net_total, currency)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (order_id) DO NOTHING
                """,
                    (
                        order.get("orderId"),
                        order.get("orderDate"),
                        order.get("region"),
                        order.get("purchaseOrderNumber"),
                        order.get("orderStatus"),
                        buyer_name,
                        buyer_email,
                        subtotal,
                        tax,
                        shipping,
                        net_total,
                        charges.get("NET_TOTAL", {}).get("currency", "GBP"),
                    ),
                )

                if cursor.rowcount > 0:
                    imported += 1
                else:
                    duplicates += 1

            conn.commit()

    return imported, duplicates


def import_amazon_business_line_items(line_items: list) -> int:
    """Import Amazon Business line items from API response.

    Args:
        line_items: List of line item dictionaries from Amazon Business API

    Returns:
        Count of imported line items
    """
    imported = 0

    with get_db() as conn, conn.cursor() as cursor:
        for item in line_items:
            product = item.get("productDetails", {})

            cursor.execute(
                """
                    INSERT INTO amazon_business_line_items
                    (order_id, line_item_id, asin, title, brand, category,
                     quantity, unit_price, total_price, seller_name)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """,
                (
                    item.get("orderId"),
                    item.get("orderLineItemId"),
                    product.get("asin"),
                    product.get("title"),
                    product.get("brand"),
                    product.get("category"),
                    item.get("quantity"),
                    item.get("unitPrice", {}).get("amount"),
                    item.get("totalPrice", {}).get("amount"),
                    item.get("sellerInfo", {}).get("name"),
                ),
            )

            if cursor.rowcount > 0:
                imported += 1

        conn.commit()

        # Update product_summary in orders table
        try:
            cursor.execute("""
                    UPDATE amazon_business_orders o
                    SET product_summary = (
                        SELECT STRING_AGG(title, ', ')
                        FROM amazon_business_line_items li
                        WHERE li.order_id = o.order_id
                    ),
                    item_count = (
                        SELECT COALESCE(SUM(quantity), 0)
                        FROM amazon_business_line_items li
                        WHERE li.order_id = o.order_id
                    )
                """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Warning: Failed to update product summaries: {e}")

    return imported


def get_amazon_business_orders(date_from=None, date_to=None) -> list:
    """Get all Amazon Business orders.

    Args:
        date_from: Optional start date filter
        date_to: Optional end date filter

    Returns:
        List of order dictionaries
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        query = """
                SELECT id, order_id, order_date, region, purchase_order_number,
                       order_status, buyer_name, buyer_email, subtotal, tax,
                       shipping, net_total, currency, item_count, product_summary,
                       created_at
                FROM amazon_business_orders
            """
        params = []

        if date_from or date_to:
            conditions = []
            if date_from:
                conditions.append("order_date >= %s")
                params.append(date_from)
            if date_to:
                conditions.append("order_date <= %s")
                params.append(date_to)
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY order_date DESC"

        cursor.execute(query, params)
        return cursor.fetchall()


def get_amazon_business_statistics() -> dict:
    """Get Amazon Business import and matching statistics.

    Returns:
        Dictionary with counts and date ranges
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM amazon_business_orders) as total_orders,
                    (SELECT MIN(order_date) FROM amazon_business_orders) as min_order_date,
                    (SELECT MAX(order_date) FROM amazon_business_orders) as max_order_date,
                    (SELECT COUNT(*) FROM truelayer_amazon_business_matches) as total_matched,
                    (SELECT COUNT(*) FROM truelayer_transactions tt
                     WHERE (UPPER(merchant_name) LIKE '%AMAZON%'
                            OR UPPER(description) LIKE '%AMAZON%')
                       AND UPPER(description) NOT LIKE '%AMZN MKTP%'
                       AND NOT EXISTS (
                           SELECT 1 FROM truelayer_amazon_business_matches tabm
                           WHERE tabm.truelayer_transaction_id = tt.id
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM truelayer_amazon_transaction_matches tatm
                           WHERE tatm.truelayer_transaction_id = tt.id
                       )
                    ) as total_unmatched
            """)

            result = dict(cursor.fetchone())

            # Format dates for JSON
            if result.get("min_order_date"):
                result["min_order_date"] = result["min_order_date"].isoformat()
            if result.get("max_order_date"):
                result["max_order_date"] = result["max_order_date"].isoformat()

            return result


def get_unmatched_truelayer_amazon_business_transactions() -> list:
    """Get TrueLayer transactions with Amazon merchant that haven't been matched
    to Amazon Business orders (excludes consumer marketplace transactions).

    Returns:
        List of unmatched transaction dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, account_id, transaction_id, normalised_provider_transaction_id,
                       timestamp, description, amount, currency, transaction_type,
                       transaction_category, merchant_name, running_balance, metadata
                FROM truelayer_transactions tt
                WHERE (
                    UPPER(merchant_name) LIKE '%AMAZON%'
                    OR UPPER(description) LIKE '%AMAZON%'
                )
                AND UPPER(description) NOT LIKE '%AMZN MKTP%'
                AND NOT EXISTS (
                    SELECT 1 FROM truelayer_amazon_business_matches tabm
                    WHERE tabm.truelayer_transaction_id = tt.id
                )
                AND NOT EXISTS (
                    SELECT 1 FROM truelayer_amazon_transaction_matches tatm
                    WHERE tatm.truelayer_transaction_id = tt.id
                )
                ORDER BY timestamp DESC
            """)
            return cursor.fetchall()


def match_truelayer_amazon_business_transaction(
    truelayer_transaction_id: int, amazon_business_order_id: int, confidence: int
) -> bool:
    """Record a match between TrueLayer transaction and Amazon Business order.
    Stores in legacy table and adds to transaction_enrichment_sources.

    Args:
        truelayer_transaction_id: TrueLayer transaction ID
        amazon_business_order_id: Amazon Business order database ID
        confidence: Match confidence score (0-100)

    Returns:
        True if match was recorded successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                # Store the match in legacy table
                cursor.execute(
                    """
                    INSERT INTO truelayer_amazon_business_matches
                    (truelayer_transaction_id, amazon_business_order_id, match_confidence)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (truelayer_transaction_id) DO UPDATE
                    SET amazon_business_order_id = EXCLUDED.amazon_business_order_id,
                        match_confidence = EXCLUDED.match_confidence,
                        matched_at = NOW()
                """,
                    (truelayer_transaction_id, amazon_business_order_id, confidence),
                )

                # Get order details for enrichment source
                cursor.execute(
                    """
                    SELECT product_summary, order_id FROM amazon_business_orders WHERE id = %s
                """,
                    (amazon_business_order_id,),
                )
                order_row = cursor.fetchone()

                if order_row and order_row[0]:
                    product_summary, order_id = order_row

                    # Add to multi-source enrichment table
                    cursor.execute(
                        """
                        INSERT INTO transaction_enrichment_sources
                            (truelayer_transaction_id, source_type, source_id, description,
                             order_id, match_confidence, match_method, is_primary)
                        VALUES (%s, 'amazon_business', %s, %s, %s, %s, 'amount_date_match', TRUE)
                        ON CONFLICT (truelayer_transaction_id, source_type, source_id)
                        DO UPDATE SET
                            description = EXCLUDED.description,
                            order_id = EXCLUDED.order_id,
                            match_confidence = EXCLUDED.match_confidence,
                            updated_at = NOW()
                    """,
                        (
                            truelayer_transaction_id,
                            amazon_business_order_id,
                            product_summary,
                            order_id,
                            confidence,
                        ),
                    )

                conn.commit()
                return True
            except Exception as e:
                print(f"Error matching Amazon Business transaction: {e}")
                conn.rollback()
                return False


def delete_amazon_business_connection(connection_id: int) -> bool:
    """Delete an Amazon Business connection.

    Args:
        connection_id: Connection ID to delete

    Returns:
        True if deleted successfully
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE amazon_business_connections
                SET status = 'disconnected', updated_at = NOW()
                WHERE id = %s
            """,
            (connection_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def clear_amazon_business_data() -> dict:
    """Clear all Amazon Business data (for testing/reset).

    Returns:
        Dictionary with counts of deleted records
    """
    with get_db() as conn, conn.cursor() as cursor:
        # Get counts before deletion
        cursor.execute("SELECT COUNT(*) FROM amazon_business_orders")
        orders_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM truelayer_amazon_business_matches")
        matches_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM amazon_business_line_items")
        items_count = cursor.fetchone()[0]

        # Delete in order of foreign key dependencies
        cursor.execute("DELETE FROM truelayer_amazon_business_matches")
        cursor.execute("DELETE FROM amazon_business_line_items")
        cursor.execute("DELETE FROM amazon_business_orders")

        conn.commit()

        return {
            "orders_deleted": orders_count,
            "matches_deleted": matches_count,
            "line_items_deleted": items_count,
        }


def get_amazon_business_order_by_id(order_id: str) -> dict:
    """Get Amazon Business order by order_id for duplicate detection.

    Args:
        order_id: Amazon Order ID (e.g., AmazonOrderId from SP-API)

    Returns:
        Order dictionary or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM amazon_business_orders
                WHERE order_id = %s
            """,
            (order_id,),
        )
        return cursor.fetchone()


def insert_amazon_business_order(order: dict) -> int:
    """Insert a single Amazon Business order.

    Args:
        order: Order dictionary with normalized fields

    Returns:
        Order database ID, or None if duplicate
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO amazon_business_orders
                (order_id, order_date, region, purchase_order_number, order_status,
                 buyer_name, buyer_email, subtotal, tax, shipping, net_total, currency, item_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO NOTHING
                RETURNING id
            """,
                (
                    order.get("order_id"),
                    order.get("order_date"),
                    order.get("region"),
                    order.get("purchase_order_number"),
                    order.get("order_status"),
                    order.get("buyer_name"),
                    order.get("buyer_email"),
                    order.get("subtotal"),
                    order.get("tax", 0),
                    order.get("shipping", 0),
                    order.get("net_total"),
                    order.get("currency", "GBP"),
                    order.get("item_count", 0),
                ),
            )

            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None


def insert_amazon_business_line_item(item: dict) -> int:
    """Insert a single Amazon Business line item.

    Args:
        item: Line item dictionary with normalized fields

    Returns:
        Line item database ID
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO amazon_business_line_items
                (order_id, line_item_id, asin, title, brand, category, quantity, unit_price, total_price, seller_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    item.get("order_id"),
                    item.get("line_item_id"),
                    item.get("asin"),
                    item.get("title"),
                    item.get("brand"),
                    item.get("category"),
                    item.get("quantity", 1),
                    item.get("unit_price", 0),
                    item.get("total_price", 0),
                    item.get("seller_name"),
                ),
            )

            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None


def update_amazon_business_product_summaries() -> int:
    """Update product_summary field by concatenating line items.

    Concatenates all line_items.title for each order into the product_summary field.

    Returns:
        Number of orders updated
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("""
                UPDATE amazon_business_orders o
                SET product_summary = (
                    SELECT string_agg(title, ', ')
                    FROM amazon_business_line_items
                    WHERE order_id = o.order_id
                )
                WHERE product_summary IS NULL OR product_summary = ''
            """)
        conn.commit()
        return cursor.rowcount


# ============================================================================
