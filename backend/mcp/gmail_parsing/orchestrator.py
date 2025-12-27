"""
Gmail Parser Orchestrator

Main parsing coordination and database update logic.
Orchestrates the parsing flow: pre-filter → vendor → schema → pattern → LLM
"""

import json
from datetime import datetime

import database_postgres as database

from mcp.gmail_parsers.base import get_vendor_parser
from mcp.logging_config import get_logger

from .filtering import (
    has_schema_order_markup,
    is_likely_receipt,
)
from .llm_extraction import extract_with_llm
from .pattern_extraction import extract_with_patterns
from .schema_extraction import extract_schema_org
from .utilities import (
    compute_receipt_hash,
    html_to_text,
    is_valid_merchant_name,
)

# Initialize logger
logger = get_logger(__name__)


def parse_receipt(receipt_id: int) -> dict:
    """
    Main entry point for parsing a receipt.

    Flow (IMPORTANT - pre-filter runs BEFORE extraction):
    1. Check Schema.org Order markup (definitive receipt)
    2. Pre-filter to reject marketing emails
    3. Schema.org extraction
    4. Vendor-specific parsing
    5. Pattern-based extraction
    6. LLM fallback

    Args:
        receipt_id: Database ID of the receipt to parse

    Returns:
        Dictionary with parsed data and status
    """
    receipt = database.get_gmail_receipt_by_id(receipt_id)
    if not receipt:
        return {"error": "Receipt not found", "receipt_id": receipt_id}

    raw_data = receipt.get("raw_schema_data") or {}
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = {}

    html_body = raw_data.get("body_html", "")
    text_body = raw_data.get("body_text", "")
    subject = receipt.get("subject", "")
    sender_email = receipt.get("sender_email", "")
    sender_name = receipt.get("sender_name", "")
    sender_domain = receipt.get("merchant_domain", "")
    list_unsubscribe = raw_data.get("list_unsubscribe", "")
    received_at = receipt.get("received_at")  # Get timestamp for date fallback

    # Prepare text for filtering
    text_body_cleaned = text_body or html_to_text(html_body)

    # STEP 1: Check for Schema.org Order markup (definitive receipt signal)
    has_order_markup = has_schema_order_markup(html_body)

    # STEP 2: PRE-FILTER - Run BEFORE any extraction to reject marketing emails
    is_receipt, filter_reason, filter_confidence = is_likely_receipt(
        subject=subject,
        body_text=text_body_cleaned,
        sender_email=sender_email,
        sender_domain=sender_domain,
        list_unsubscribe=list_unsubscribe,
        has_schema_order=has_order_markup,
    )

    if not is_receipt:
        logger.debug(
            f"Pre-filter rejected: {filter_reason}", extra={"receipt_id": receipt_id}
        )
        return mark_receipt_unparseable(receipt_id, f"Pre-filtered: {filter_reason}")

    logger.debug(
        f"Pre-filter passed: {filter_reason}", extra={"receipt_id": receipt_id}
    )

    # STEP 3: Try Schema.org extraction (highest confidence)
    if html_body:
        schema_result = extract_schema_org(html_body)
        if schema_result and schema_result.get("merchant_name"):
            # Fallback: use email received_at timestamp if no date was parsed
            if not schema_result.get("receipt_date") and received_at:
                schema_result["receipt_date"] = (
                    received_at.strftime("%Y-%m-%d")
                    if hasattr(received_at, "strftime")
                    else str(received_at)
                )
                schema_result["date_source"] = "email_received"
            logger.info(
                "Schema.org parsing succeeded",
                extra={"receipt_id": receipt_id, "parse_method": "schema_org"},
            )
            return update_receipt_with_parsed_data(receipt_id, schema_result)

    # STEP 4: Try vendor-specific parser (high confidence for known formats)
    vendor_parser = get_vendor_parser(sender_domain)
    if vendor_parser:
        vendor_result = vendor_parser(html_body, text_body, subject)
        # Accept vendor result if it has amount OR at least identified the merchant
        # (e.g., Amazon "Ordered:" emails may not have parseable amounts)
        if vendor_result and (
            vendor_result.get("total_amount")
            or vendor_result.get("merchant_name_normalized")
        ):
            # Fallback: use email received_at timestamp if no date was parsed
            if not vendor_result.get("receipt_date") and received_at:
                vendor_result["receipt_date"] = (
                    received_at.strftime("%Y-%m-%d")
                    if hasattr(received_at, "strftime")
                    else str(received_at)
                )
                vendor_result["date_source"] = "email_received"
            logger.info(
                f"Vendor parsing succeeded: {vendor_result.get('parse_method')}",
                extra={
                    "receipt_id": receipt_id,
                    "parse_method": vendor_result.get("parse_method"),
                },
            )
            return update_receipt_with_parsed_data(receipt_id, vendor_result)

    # STEP 5: Try pattern-based extraction
    pattern_result = extract_with_patterns(
        subject=subject,
        body_text=text_body_cleaned,
        sender_domain=sender_domain,
        sender_email=sender_email,
        sender_name=sender_name,
    )

    # Validate pattern result before accepting
    if pattern_result and pattern_result.get("total_amount"):
        merchant = pattern_result.get("merchant_name", "")
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get("receipt_date") and received_at:
                pattern_result["receipt_date"] = (
                    received_at.strftime("%Y-%m-%d")
                    if hasattr(received_at, "strftime")
                    else str(received_at)
                )
                pattern_result["date_source"] = "email_received"
            logger.info(
                "Pattern parsing succeeded",
                extra={"receipt_id": receipt_id, "parse_method": "pattern"},
            )
            return update_receipt_with_parsed_data(receipt_id, pattern_result)
        logger.warning(
            f"Pattern found invalid merchant name: '{merchant}'",
            extra={"receipt_id": receipt_id},
        )
        pattern_result["merchant_name"] = None  # Clear invalid merchant

    # STEP 6: Try LLM extraction as fallback
    llm_result = extract_with_llm(
        subject=subject, sender=sender_email, body_text=text_body_cleaned
    )
    if llm_result and llm_result.get("total_amount"):
        # Fallback: use email received_at timestamp if no date was parsed
        if not llm_result.get("receipt_date") and received_at:
            llm_result["receipt_date"] = (
                received_at.strftime("%Y-%m-%d")
                if hasattr(received_at, "strftime")
                else str(received_at)
            )
            llm_result["date_source"] = "email_received"
        logger.info(
            "LLM parsing succeeded",
            extra={"receipt_id": receipt_id, "parse_method": "llm"},
        )
        return update_receipt_with_parsed_data(receipt_id, llm_result)

    # Fall back to pattern data if we have VALID merchant at least
    if pattern_result and pattern_result.get("merchant_name"):
        merchant = pattern_result.get("merchant_name", "")
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get("receipt_date") and received_at:
                pattern_result["receipt_date"] = (
                    received_at.strftime("%Y-%m-%d")
                    if hasattr(received_at, "strftime")
                    else str(received_at)
                )
                pattern_result["date_source"] = "email_received"
            pattern_result["parse_confidence"] = 50
            pattern_result["parsing_status"] = "parsed"
            return update_receipt_with_parsed_data(receipt_id, pattern_result)
        logger.warning(
            f"Fallback rejected invalid merchant name: '{merchant}'",
            extra={"receipt_id": receipt_id},
        )

    # Mark as unparseable
    return mark_receipt_unparseable(
        receipt_id, "No structured data, patterns, or LLM extraction succeeded"
    )


def parse_receipt_content(
    html_body: str,
    text_body: str,
    subject: str,
    sender_email: str,
    sender_domain: str = None,
    sender_name: str = None,
    list_unsubscribe: str = None,
    skip_llm: bool = True,
    received_at: datetime = None,
) -> dict:
    """
    Parse email content directly (without database).

    Used during sync to parse emails before storing.
    Returns parsed data dictionary that can be stored directly.

    Flow:
    1. Pre-filter to reject marketing emails
    2. Vendor-specific parsing (highest priority - tailored to known formats)
    3. Schema.org extraction (fallback for vendors without custom parsers)
    4. Pattern-based extraction
    5. LLM fallback (optional, disabled by default during sync)

    Args:
        html_body: HTML body of email
        text_body: Plain text body of email
        subject: Email subject
        sender_email: Sender email address
        sender_domain: Sender domain (extracted from email if not provided)
        sender_name: Sender display name from email header
        list_unsubscribe: List-Unsubscribe header value
        skip_llm: Skip LLM extraction (faster, no cost)
        received_at: Email received timestamp (fallback for receipt_date if not parsed)

    Returns:
        Dictionary with parsed data:
        - merchant_name, merchant_name_normalized
        - total_amount, currency_code
        - order_id, receipt_date (falls back to received_at if not parsed from body)
        - date_source ('email_body' or 'email_received' to track date origin)
        - line_items (list)
        - parse_method, parse_confidence
        - parsing_status ('parsed' or 'unparseable')
        - parsing_error (if unparseable)
    """
    # Extract domain if not provided
    if not sender_domain and sender_email:
        if "@" in sender_email:
            sender_domain = sender_email.split("@")[-1].lower()

    # Prepare text for filtering
    text_body_cleaned = text_body or html_to_text(html_body)

    # STEP 1: Check for Schema.org Order markup (definitive receipt signal)
    has_order_markup = has_schema_order_markup(html_body) if html_body else False

    # STEP 2: PRE-FILTER - Run BEFORE any extraction to reject marketing emails
    is_receipt, filter_reason, filter_confidence = is_likely_receipt(
        subject=subject,
        body_text=text_body_cleaned,
        sender_email=sender_email,
        sender_domain=sender_domain,
        list_unsubscribe=list_unsubscribe,
        has_schema_order=has_order_markup,
    )

    if not is_receipt:
        return {
            "parsing_status": "unparseable",
            "parsing_error": f"Pre-filtered: {filter_reason}",
            "parse_confidence": 0,
            "parse_method": "pre_filter",
        }

    # STEP 3: Try vendor-specific parser FIRST (highest confidence for known formats)
    # Vendor parsers are tailored to specific email formats and should take priority
    vendor_parser = get_vendor_parser(sender_domain)
    if vendor_parser:
        try:
            vendor_result = vendor_parser(html_body or "", text_body or "", subject)
            # Accept vendor result if it has amount, order_id, OR identified the merchant
            if vendor_result and (
                vendor_result.get("total_amount")
                or vendor_result.get("order_id")
                or vendor_result.get("merchant_name_normalized")
            ):
                # Fallback: use email received_at timestamp if no date was parsed from body
                if not vendor_result.get("receipt_date") and received_at:
                    vendor_result["receipt_date"] = received_at.strftime("%Y-%m-%d")
                    vendor_result["date_source"] = (
                        "email_received"  # Track where date came from
                    )
                vendor_result["parsing_status"] = "parsed"
                return vendor_result
        except Exception as e:
            # CRITICAL FIX: Vendor parser crashes should not kill entire sync
            # Log error and fall through to next parser instead
            from mcp.error_tracking import ErrorStage, GmailError
            from mcp.logging_config import get_logger

            logger = get_logger(__name__)
            logger.error(
                f"Vendor parser failed for {sender_domain}: {e}",
                extra={"merchant": sender_domain},
                exc_info=True,
            )

            # Track error for statistics (don't let error tracking itself crash sync)
            try:
                error = GmailError.from_exception(
                    e, ErrorStage.VENDOR_PARSE, context={"sender_domain": sender_domain}
                )
                # Note: connection_id and sync_job_id not available at this level
                # Error will be logged but not linked to specific job
                error.log()
            except Exception:  # Fixed: was bare except
                pass  # Silently ignore error tracking failures

            # Fall through to next parser (schema.org, pattern, etc.)

    # STEP 4: Try Schema.org extraction (fallback for vendors without custom parsers)
    if html_body:
        schema_result = extract_schema_org(html_body)
        if schema_result and schema_result.get("merchant_name"):
            # Fallback: use email received_at timestamp if no date was parsed
            if not schema_result.get("receipt_date") and received_at:
                schema_result["receipt_date"] = received_at.strftime("%Y-%m-%d")
                schema_result["date_source"] = "email_received"
            schema_result["parsing_status"] = "parsed"
            return schema_result

    # STEP 5: Try pattern-based extraction
    pattern_result = extract_with_patterns(
        subject=subject,
        body_text=text_body_cleaned,
        sender_domain=sender_domain,
        sender_email=sender_email,
        sender_name=sender_name,
    )

    # Validate pattern result before accepting
    if pattern_result and pattern_result.get("total_amount"):
        merchant = pattern_result.get("merchant_name", "")
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get("receipt_date") and received_at:
                pattern_result["receipt_date"] = received_at.strftime("%Y-%m-%d")
                pattern_result["date_source"] = "email_received"
            pattern_result["parsing_status"] = "parsed"
            return pattern_result

    # STEP 6: Try LLM extraction as fallback (if enabled)
    if not skip_llm:
        llm_result = extract_with_llm(
            subject=subject, sender=sender_email, body_text=text_body_cleaned
        )
        if llm_result and llm_result.get("total_amount"):
            # Fallback: use email received_at timestamp if no date was parsed
            if not llm_result.get("receipt_date") and received_at:
                llm_result["receipt_date"] = received_at.strftime("%Y-%m-%d")
                llm_result["date_source"] = "email_received"
            llm_result["parsing_status"] = "parsed"
            return llm_result

    # Fall back to pattern data if we have VALID merchant at least
    if pattern_result and pattern_result.get("merchant_name"):
        merchant = pattern_result.get("merchant_name", "")
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get("receipt_date") and received_at:
                pattern_result["receipt_date"] = received_at.strftime("%Y-%m-%d")
                pattern_result["date_source"] = "email_received"
            pattern_result["parse_confidence"] = 50
            pattern_result["parsing_status"] = "parsed"
            return pattern_result

    # Mark as unparseable - still return basic info for tracking
    return {
        "parsing_status": "unparseable",
        "parsing_error": "No structured data or patterns found",
        "parse_confidence": 0,
        "parse_method": "none",
        "merchant_name": sender_domain,  # Use domain as fallback merchant
        "merchant_name_normalized": sender_domain.replace(".", "_")
        if sender_domain
        else None,
    }


def update_receipt_with_parsed_data(receipt_id: int, parsed_data: dict) -> dict:
    """
    Update receipt in database with parsed data.

    Args:
        receipt_id: Database receipt ID
        parsed_data: Parsed receipt data

    Returns:
        Updated receipt dictionary
    """
    # Compute receipt hash for deduplication
    receipt_hash = compute_receipt_hash(
        parsed_data.get("merchant_name_normalized"),
        parsed_data.get("total_amount"),
        parsed_data.get("receipt_date"),
        parsed_data.get("order_id"),
    )

    # Update database
    database.update_gmail_receipt_parsed(
        receipt_id=receipt_id,
        merchant_name=parsed_data.get("merchant_name"),
        merchant_name_normalized=parsed_data.get("merchant_name_normalized"),
        order_id=parsed_data.get("order_id"),
        total_amount=parsed_data.get("total_amount"),
        currency_code=parsed_data.get("currency_code", "GBP"),
        receipt_date=parsed_data.get("receipt_date"),
        line_items=parsed_data.get("line_items"),
        receipt_hash=receipt_hash,
        parse_method=parsed_data.get("parse_method"),
        parse_confidence=parsed_data.get("parse_confidence"),
        parsing_status=parsed_data.get("parsing_status", "parsed"),
        llm_cost_cents=parsed_data.get("llm_cost_cents"),
    )

    return {
        "status": "parsed",
        "receipt_id": receipt_id,
        "parse_method": parsed_data.get("parse_method"),
        "parse_confidence": parsed_data.get("parse_confidence"),
        "merchant_name": parsed_data.get("merchant_name"),
        "total_amount": parsed_data.get("total_amount"),
    }


def mark_receipt_unparseable(receipt_id: int, error: str) -> dict:
    """
    Mark receipt as unparseable.

    Args:
        receipt_id: Database receipt ID
        error: Error message

    Returns:
        Status dictionary
    """
    database.update_gmail_receipt_status(
        receipt_id=receipt_id, parsing_status="unparseable", parsing_error=error
    )

    return {
        "status": "unparseable",
        "receipt_id": receipt_id,
        "error": error,
    }


def parse_pending_receipts(connection_id: int, limit: int = 100) -> dict:
    """
    Parse all pending receipts for a connection.

    Args:
        connection_id: Database connection ID
        limit: Maximum receipts to process

    Returns:
        Summary dictionary
    """
    pending = database.get_pending_gmail_receipts(connection_id, limit)

    results = {
        "total": len(pending),
        "parsed": 0,
        "failed": 0,
        "by_method": {"schema_org": 0, "pattern": 0, "llm": 0},
    }

    for receipt in pending:
        try:
            result = parse_receipt(receipt["id"])

            if result.get("status") == "parsed":
                results["parsed"] += 1
                method = result.get("parse_method", "unknown")
                if method in results["by_method"]:
                    results["by_method"][method] += 1
            else:
                results["failed"] += 1

        except Exception as e:
            logger.error(
                f"Failed to parse receipt {receipt['id']}: {e}",
                extra={"receipt_id": receipt["id"]},
                exc_info=True,
            )
            results["failed"] += 1

    return results
