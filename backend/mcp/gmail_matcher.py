"""
Gmail Receipt Transaction Matcher

Matches parsed Gmail receipts to TrueLayer bank transactions.
Uses fuzzy matching with configurable confidence thresholds.

Confidence scoring:
- 100: Exact amount + same day + merchant match
- 90: Exact amount + ±3 days + merchant match
- 80: Amount within 2% + ±7 days + merchant match
- 70: Amount within 2% + ±7 days + no merchant
- <70: Requires user confirmation
"""

from datetime import UTC, datetime, timedelta

import database
from mcp.logging_config import get_logger

# Initialize logger
logger = get_logger(__name__)


def normalize_datetime(dt: datetime) -> datetime:
    """Normalize datetime to naive UTC for consistent comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convert to UTC and strip timezone
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


# Matching configuration
AUTO_MATCH_THRESHOLD = 70  # Auto-match if confidence >= 70
CONFIRMATION_THRESHOLD = 60  # Suggest match if confidence >= 60
AMOUNT_TOLERANCE_PERCENT = 2.0  # 2% tolerance for fuzzy amount match
# Optimized date tolerances (Phase 3 - based on benchmarking showing receipts often 1-2 days before txn)
DATE_TOLERANCE_SAME_DAY = 2  # ±2 days (increased from ±1)
DATE_TOLERANCE_CLOSE = 4  # ±4 days (increased from ±3)
DATE_TOLERANCE_WIDE = 10  # ±10 days (increased from ±7)
DATE_PREFERENCE_BEFORE = (
    5  # Bonus for receipts 1-4 days BEFORE transaction (common pattern)
)


def match_all_gmail_receipts(user_id: int = 1) -> dict:
    """
    Match all unmatched parsed Gmail receipts to transactions.
    Stores ALL matches (not just best) in transaction_enrichment_sources.
    Best match is also stored in legacy table for backward compatibility.

    Args:
        user_id: User ID to match receipts for

    Returns:
        Dictionary with matching statistics
    """
    # Get unmatched parsed receipts
    unmatched_receipts = database.get_unmatched_gmail_receipts(user_id)

    if not unmatched_receipts:
        return {
            "total_processed": 0,
            "matched": 0,
            "suggested": 0,
            "unmatched": 0,
            "total_sources_added": 0,
            "matches": [],
            "note": "No unmatched parsed receipts found",
        }

    # Get TrueLayer transactions for matching
    # Expand date range to cover all possible matches
    min_date = None
    max_date = None

    for receipt in unmatched_receipts:
        # Fallback to received_at (email timestamp) if receipt_date is NULL
        receipt_date = parse_receipt_date(
            receipt.get("receipt_date")
        ) or parse_receipt_date(receipt.get("received_at"))
        if receipt_date:
            if min_date is None or receipt_date < min_date:
                min_date = receipt_date
            if max_date is None or receipt_date > max_date:
                max_date = receipt_date

    # Expand range by date tolerance
    if min_date:
        min_date = min_date - timedelta(days=DATE_TOLERANCE_WIDE)
    if max_date:
        max_date = max_date + timedelta(days=DATE_TOLERANCE_WIDE)

    transactions = database.get_transactions_for_matching(
        user_id=user_id, from_date=min_date, to_date=max_date
    )

    matched_count = 0
    suggested_count = 0
    total_sources_added = 0
    matches_details = []

    for receipt in unmatched_receipts:
        # Find ALL matching transactions above CONFIRMATION_THRESHOLD
        all_matches = find_matching_transactions(receipt, transactions)

        if all_matches:
            best_match = all_matches[0]  # Highest confidence match

            if best_match["confidence"] >= AUTO_MATCH_THRESHOLD:
                # Auto-match with high confidence - store in legacy table
                success = save_match(
                    receipt["id"],
                    best_match["transaction_id"],
                    best_match["confidence"],
                    best_match["match_method"],
                    user_confirmed=False,
                    currency_converted=best_match.get("currency_converted", False),
                    conversion_rate=best_match.get("conversion_rate"),
                )

                if success:
                    matched_count += 1

                    # Store ALL matches in transaction_enrichment_sources
                    # Deduplicate by transaction_id to avoid CardinalityViolation
                    # (same receipt can't match same transaction twice)
                    seen_txn_ids = set()
                    unique_matches = []
                    for match in all_matches:
                        if (
                            match["transaction_id"] not in seen_txn_ids
                            and match["confidence"] >= AUTO_MATCH_THRESHOLD
                        ):
                            unique_matches.append(match)
                            seen_txn_ids.add(match["transaction_id"])

                    for i, match in enumerate(unique_matches):
                        is_primary = (
                            i == 0
                        )  # First match (highest confidence) is primary
                        # Build description from receipt data
                        description = (
                            receipt.get("subject")
                            or receipt.get("merchant_name")
                            or "Email Receipt"
                        )
                        try:
                            database.add_enrichment_source(
                                transaction_id=match["transaction_id"],
                                source_type="gmail",
                                source_id=receipt["id"],
                                description=description,
                                order_id=receipt.get("order_id"),
                                line_items=receipt.get("line_items"),
                                confidence=match["confidence"],
                                match_method=match["match_method"],
                                is_primary=is_primary,
                            )
                            total_sources_added += 1
                        except Exception as e:
                            # CRITICAL FIX: Only skip actual duplicates, log real errors
                            error_msg = str(e).lower()
                            if (
                                "duplicate" in error_msg
                                or "unique constraint" in error_msg
                            ):
                                # This is a genuine duplicate - safe to skip
                                logger.debug("Skipping duplicate enrichment source")
                            else:
                                # This is a real error (FK violation, connection error, etc.)
                                logger.error(
                                    f"Failed to add enrichment source: {e}",
                                    extra={
                                        "receipt_id": receipt.get("id"),
                                        "transaction_id": match.get("transaction_id"),
                                    },
                                    exc_info=True,
                                )

                                # Track error for statistics
                                try:
                                    from mcp.error_tracking import (
                                        ErrorStage,
                                        GmailError,
                                    )

                                    error = GmailError.from_exception(
                                        e,
                                        ErrorStage.MATCH,
                                        context={
                                            "receipt_id": receipt["id"],
                                            "transaction_id": match["transaction_id"],
                                        },
                                    )
                                    error.log()  # connection_id/sync_job_id not available here
                                except Exception:  # Fixed: was bare except
                                    pass  # Don't let error tracking crash matching

                    matches_details.append(
                        {
                            "receipt_id": receipt["id"],
                            "transaction_id": best_match["transaction_id"],
                            "confidence": best_match["confidence"],
                            "match_method": best_match["match_method"],
                            "auto_matched": True,
                            "total_matches": len(
                                [
                                    m
                                    for m in all_matches
                                    if m["confidence"] >= AUTO_MATCH_THRESHOLD
                                ]
                            ),
                        }
                    )

            elif best_match["confidence"] >= CONFIRMATION_THRESHOLD:
                # Save as suggestion requiring confirmation (legacy table only)
                success = save_match(
                    receipt["id"],
                    best_match["transaction_id"],
                    best_match["confidence"],
                    best_match["match_method"],
                    user_confirmed=False,
                    currency_converted=best_match.get("currency_converted", False),
                    conversion_rate=best_match.get("conversion_rate"),
                )

                if success:
                    suggested_count += 1
                    matches_details.append(
                        {
                            "receipt_id": receipt["id"],
                            "transaction_id": best_match["transaction_id"],
                            "confidence": best_match["confidence"],
                            "match_method": best_match["match_method"],
                            "auto_matched": False,
                            "needs_confirmation": True,
                        }
                    )

    return {
        "total_processed": len(unmatched_receipts),
        "matched": matched_count,
        "suggested": suggested_count,
        "unmatched": len(unmatched_receipts) - matched_count - suggested_count,
        "total_sources_added": total_sources_added,
        "matches": matches_details,
    }


def find_matching_transactions(receipt: dict, transactions: list) -> list[dict]:
    """
    Find transactions that match a receipt.

    Args:
        receipt: Parsed Gmail receipt
        transactions: List of TrueLayer transactions

    Returns:
        List of match dictionaries sorted by confidence (highest first)
    """
    matches = []

    receipt_amount = receipt.get("total_amount")
    # Fallback to received_at (email timestamp) if receipt_date is NULL
    receipt_date = parse_receipt_date(
        receipt.get("receipt_date")
    ) or parse_receipt_date(receipt.get("received_at"))
    receipt_merchant = receipt.get("merchant_name_normalized")
    receipt_currency = receipt.get("currency_code", "GBP")  # Default to GBP

    if not receipt_amount or not receipt_date:
        return []

    for txn in transactions:
        confidence, match_method, conversion_rate = calculate_match_confidence(
            receipt_amount=receipt_amount,
            receipt_date=receipt_date,
            receipt_merchant=receipt_merchant,
            txn_amount=abs(float(txn.get("amount", 0))),
            txn_date=parse_transaction_date(txn.get("date") or txn.get("timestamp")),
            txn_description=txn.get("description", ""),
            txn_merchant=txn.get("merchant_name", ""),
            receipt_currency=receipt_currency,
        )

        if confidence >= CONFIRMATION_THRESHOLD:
            matches.append(
                {
                    "transaction_id": txn["id"],
                    "confidence": confidence,
                    "match_method": match_method,
                    "conversion_rate": conversion_rate,
                    "currency_converted": conversion_rate is not None,
                    "transaction_amount": abs(float(txn.get("amount", 0))),
                    "transaction_date": str(txn.get("date")),
                    "transaction_description": txn.get("description"),
                }
            )

    # Sort by confidence (highest first)
    matches.sort(key=lambda x: x["confidence"], reverse=True)

    return matches


def calculate_match_confidence(
    receipt_amount: float,
    receipt_date: datetime,
    receipt_merchant: str,
    txn_amount: float,
    txn_date: datetime,
    txn_description: str,
    txn_merchant: str,
    receipt_currency: str = "GBP",
) -> tuple[int, str, float | None]:
    """
    Calculate match confidence score with multi-currency support.

    Args:
        receipt_amount: Receipt total amount
        receipt_date: Receipt date
        receipt_merchant: Normalized receipt merchant name
        txn_amount: Transaction amount (absolute, in GBP)
        txn_date: Transaction date
        txn_description: Transaction description
        txn_merchant: Transaction merchant name
        receipt_currency: Receipt currency code (default: GBP)

    Returns:
        Tuple of (confidence score 0-100, match method string, conversion_rate or None)
    """
    if not txn_date:
        return 0, None, None

    # Check for multi-currency transaction
    conversion_rate = None
    compare_amount = txn_amount  # Default to GBP amount

    if receipt_currency != "GBP":
        # Try to extract foreign currency amount from transaction description
        foreign_amount, extracted_rate = extract_foreign_currency_amount(
            txn_description, receipt_currency
        )

        if foreign_amount is not None:
            # Found foreign currency in transaction - compare in that currency
            compare_amount = foreign_amount
            conversion_rate = extracted_rate
            logger.debug(
                f"Multi-currency match: Receipt {receipt_amount} {receipt_currency} vs "
                f"Transaction {foreign_amount} {receipt_currency} (GBP: £{txn_amount}, rate: {extracted_rate})"
            )

    # Amount matching (using appropriate currency)
    amount_exact = is_amount_exact_match(receipt_amount, compare_amount)
    amount_fuzzy = is_amount_fuzzy_match(receipt_amount, compare_amount)

    if not amount_exact and not amount_fuzzy:
        return 0, None, None

    # Date matching (keep sign to detect early receipts)
    date_diff_days = (receipt_date - txn_date).days  # Negative = receipt before txn
    date_diff_abs = abs(date_diff_days)

    if date_diff_abs > DATE_TOLERANCE_WIDE:
        return 0, None, None

    # Merchant matching
    merchant_match = is_merchant_match(receipt_merchant, txn_merchant, txn_description)

    # Calculate confidence
    confidence = 0
    match_method = None

    if amount_exact and date_diff_abs <= DATE_TOLERANCE_SAME_DAY and merchant_match:
        confidence = 100
        match_method = "exact_amount_date_merchant"

    elif amount_exact and date_diff_abs <= DATE_TOLERANCE_CLOSE and merchant_match:
        confidence = 95
        match_method = "exact_amount_close_date_merchant"

    elif amount_exact and date_diff_abs <= DATE_TOLERANCE_CLOSE:
        confidence = 85
        match_method = "exact_amount_close_date"

    elif amount_exact and date_diff_abs <= DATE_TOLERANCE_WIDE and merchant_match:
        confidence = 90
        match_method = "exact_amount_wide_date_merchant"

    elif amount_exact and date_diff_abs <= DATE_TOLERANCE_WIDE:
        confidence = 75
        match_method = "exact_amount_wide_date"

    elif amount_fuzzy and date_diff_abs <= DATE_TOLERANCE_WIDE and merchant_match:
        confidence = 80
        match_method = "fuzzy_amount_wide_date_merchant"

    elif amount_fuzzy and date_diff_abs <= DATE_TOLERANCE_WIDE:
        confidence = 70
        match_method = "fuzzy_amount_wide_date"

    elif amount_fuzzy and merchant_match:
        confidence = 65
        match_method = "fuzzy_amount_merchant"

    # BONUS: Receipt 1-4 days BEFORE transaction (common pattern from benchmarking)
    if confidence > 0 and -4 <= date_diff_days <= -1:
        confidence = min(100, confidence + DATE_PREFERENCE_BEFORE)
        match_method += "_early_receipt"

    return confidence, match_method, conversion_rate


def is_amount_exact_match(receipt_amount: float, txn_amount: float) -> bool:
    """
    Check if amounts match exactly (within rounding).
    Phase 3 optimization: Higher tolerance for small amounts to account for fees/rounding.
    """
    diff = abs(float(receipt_amount) - float(txn_amount))

    # Small amounts (< £5): ±£0.50 tolerance for fees/rounding
    # Large amounts: ±£0.01 (original behavior)
    threshold = 0.50 if receipt_amount < 5.0 else 0.01

    return diff < threshold


def is_amount_fuzzy_match(receipt_amount: float, txn_amount: float) -> bool:
    """Check if amounts match within tolerance."""
    receipt_amount = float(receipt_amount)
    txn_amount = float(txn_amount)
    if receipt_amount == 0:
        return False

    diff_percent = abs(receipt_amount - txn_amount) / receipt_amount * 100
    return diff_percent <= AMOUNT_TOLERANCE_PERCENT


def is_merchant_match(
    receipt_merchant: str, txn_merchant: str, txn_description: str
) -> bool:
    """
    Check if merchant names match.

    Uses merchant aliases and fuzzy matching.
    """
    if not receipt_merchant:
        return False

    receipt_merchant_lower = receipt_merchant.lower()

    # Direct match with transaction merchant
    if txn_merchant:
        txn_merchant_normalized = normalize_bank_merchant(txn_merchant)
        if (
            txn_merchant_normalized
            and receipt_merchant_lower in txn_merchant_normalized
        ):
            return True
        if (
            txn_merchant_normalized
            and txn_merchant_normalized in receipt_merchant_lower
        ):
            return True

    # Match in description
    if txn_description:
        desc_normalized = normalize_bank_merchant(txn_description)
        if desc_normalized and receipt_merchant_lower in desc_normalized:
            return True

        # Check aliases
        alias = database.get_gmail_merchant_alias(receipt_merchant_lower)
        if alias:
            bank_name = alias.get("bank_name", "").lower()
            if bank_name and bank_name in desc_normalized:
                return True

    return False


def extract_foreign_currency_amount(
    txn_description: str, receipt_currency: str = "USD"
) -> tuple[float | None, float | None]:
    """
    Extract foreign currency amount and conversion rate from bank transaction description.

    Handles patterns like:
    - "CARD PAYMENT TO ANTHROPIC ,240.00 USD, RATE 0.7521/GBP ON 27-10-2025"
    - "CARD PAYMENT TO MERCHANT ,30.00 USD, RATE 0.7406/GBP ON 07-06-2025"

    Args:
        txn_description: Bank transaction description
        receipt_currency: Expected currency code (default: USD)

    Returns:
        Tuple of (foreign_amount, conversion_rate) or (None, None) if not found
    """
    if not txn_description:
        return None, None

    import re

    # Pattern: ",240.00 USD, RATE 0.7521/GBP"
    # Captures: amount and rate
    pattern = rf",(\d+\.\d{{2}})\s+{receipt_currency},\s+RATE\s+([\d.]+)/GBP"

    match = re.search(pattern, txn_description, re.IGNORECASE)
    if match:
        try:
            foreign_amount = float(match.group(1))
            conversion_rate = float(match.group(2))
            return foreign_amount, conversion_rate
        except (ValueError, IndexError):
            return None, None

    return None, None


def normalize_bank_merchant(text: str) -> str:
    """
    Normalize bank merchant name/description for matching.

    Handles common bank statement abbreviations and patterns.
    """
    if not text:
        return ""

    normalized = text.lower()

    # Remove common prefixes
    prefixes = ["payment to ", "card payment ", "direct debit ", "debit card "]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]

    # Remove common suffixes
    suffixes = [" gb", " uk", " london", " www."]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]

    # Remove special characters
    import re

    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def parse_receipt_date(date_value) -> datetime | None:
    """Parse receipt date to datetime (normalized to naive UTC)."""
    if not date_value:
        return None

    if isinstance(date_value, datetime):
        return normalize_datetime(date_value)

    if hasattr(date_value, "isoformat"):
        # It's a date object
        return datetime.combine(date_value, datetime.min.time())

    try:
        date_str = str(date_value).strip()

        # Handle ISO format
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return normalize_datetime(dt)

        # Handle date-only format
        return datetime.strptime(date_str[:10], "%Y-%m-%d")

    except (ValueError, TypeError):
        return None


def parse_transaction_date(date_value) -> datetime | None:
    """Parse transaction date to datetime (normalized to naive UTC)."""
    if not date_value:
        return None

    if isinstance(date_value, datetime):
        return normalize_datetime(date_value)

    if hasattr(date_value, "isoformat"):
        # It's a date object
        return datetime.combine(date_value, datetime.min.time())

    try:
        date_str = str(date_value).strip()

        # Handle PostgreSQL timestamp format
        if " " in date_str:
            date_part = date_str.split(" ")[0]
            return datetime.strptime(date_part, "%Y-%m-%d")

        # Handle ISO format
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return normalize_datetime(dt)

        # Handle date-only format
        return datetime.strptime(date_str[:10], "%Y-%m-%d")

    except (ValueError, TypeError):
        return None


def save_match(
    receipt_id: int,
    transaction_id: int,
    confidence: int,
    match_method: str,
    user_confirmed: bool = False,
    currency_converted: bool = False,
    conversion_rate: float = None,
) -> bool:
    """
    Save a match to the database.

    Args:
        receipt_id: Gmail receipt ID
        transaction_id: TrueLayer transaction ID
        confidence: Match confidence score
        match_method: Method used for matching
        user_confirmed: Whether user has confirmed the match
        currency_converted: Whether currency conversion was used
        conversion_rate: Exchange rate used (if applicable)

    Returns:
        True if saved successfully
    """
    try:
        database.save_gmail_match(
            truelayer_transaction_id=transaction_id,
            gmail_receipt_id=receipt_id,
            confidence=confidence,
            match_method=match_method,
            currency_converted=currency_converted,
            conversion_rate=conversion_rate,
        )

        # Match is now recorded in gmail_transaction_matches table
        # parsing_status remains 'parsed' - matching is an independent dimension

        return True

    except Exception as e:
        logger.error(
            f"Failed to save match: {e}",
            extra={"transaction_id": transaction_id, "receipt_id": receipt_id},
            exc_info=True,
        )
        return False


def get_match_suggestions(user_id: int, limit: int = 50) -> list:
    """
    Get low-confidence matches that need user confirmation.

    Args:
        user_id: User ID
        limit: Maximum suggestions to return

    Returns:
        List of match suggestions with receipt and transaction details
    """
    return database.get_gmail_matches(
        user_id=user_id, unconfirmed_only=True, limit=limit
    )


def match_single_receipt(receipt_id: int, user_id: int = 1) -> dict:
    """
    Find matches for a single receipt.

    Args:
        receipt_id: Receipt ID to match
        user_id: User ID

    Returns:
        Dictionary with match results
    """
    receipt = database.get_gmail_receipt_by_id(receipt_id)
    if not receipt:
        return {"error": "Receipt not found"}

    if receipt.get("parsing_status") != "parsed":
        return {"error": "Receipt not yet parsed"}

    # Get date range for transaction search (fallback to received_at if no receipt_date)
    receipt_date = parse_receipt_date(
        receipt.get("receipt_date")
    ) or parse_receipt_date(receipt.get("received_at"))
    if not receipt_date:
        return {"error": "Receipt has no date or received_at timestamp"}

    from_date = receipt_date - timedelta(days=DATE_TOLERANCE_WIDE)
    to_date = receipt_date + timedelta(days=DATE_TOLERANCE_WIDE)

    # Get transactions
    transactions = database.get_transactions_for_matching(
        user_id=user_id, from_date=from_date, to_date=to_date
    )

    # Find matches
    matches = find_matching_transactions(receipt, transactions)

    return {
        "receipt_id": receipt_id,
        "matches_found": len(matches),
        "matches": matches[:10],  # Return top 10
    }
