"""
Gmail Debugging & Analysis Tools

Provides 3 MCP tools for debugging Gmail receipt parsing issues:
1. debug_gmail_receipt - Get comprehensive debugging info for a specific receipt
2. search_gmail_receipts - Search receipts by criteria to find parsing issues
3. analyze_parsing_gaps - Generate comprehensive data quality report

These tools enable Claude to diagnose Gmail parsing problems, identify data gaps,
and provide actionable recommendations for parser improvements.
"""

import logging

from ..server import get_flask_client, mcp
from ..utils.defaults import apply_date_range_defaults, apply_user_id_default
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import (
    ValidationError,
    validate_date_range,
    validate_user_id,
)

logger = logging.getLogger(__name__)


@mcp.tool()
async def debug_gmail_receipt(
    receipt_id: int | None = None,
    message_id: str | None = None,
    user_id: int | None = None,
) -> dict:
    """
    Get comprehensive debugging information for a specific Gmail receipt.

    Retrieves full receipt details including parsed data, parsing metadata,
    transaction matches, and line items type debugging. Helps diagnose
    why receipts might be missing product, brand, or match data.

    Args:
        receipt_id: Gmail receipt database ID (provide either this or message_id)
        message_id: Gmail message ID (provide either this or receipt_id)
        user_id: User ID (default: 1)

    Returns:
        Comprehensive receipt debugging information including:
        - Parsed data (merchant, amount, line_items)
        - Parsing metadata (method, confidence, status, errors)
        - Transaction match details (matched transaction, confidence)
        - Line items debugging (type, count, structure)
        - Raw email metadata

    Examples:
        # Debug by receipt ID
        debug_gmail_receipt(receipt_id=123)

        # Debug by Gmail message ID
        debug_gmail_receipt(message_id="18f3a1b2c3d4e5f6")

        # Debug with specific user
        debug_gmail_receipt(receipt_id=123, user_id=1)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        if not receipt_id and not message_id:
            raise ValidationError(
                "Must provide either receipt_id or message_id",
                expected="receipt_id (int) or message_id (str)",
            )

        client = get_flask_client()

        # Get receipt by ID or search by message_id
        if receipt_id:
            logger.info(f"Debugging Gmail receipt: id={receipt_id}, user={user_id}")
            receipt = client.get(f"/api/gmail/receipts/{receipt_id}")

            if not receipt or receipt.get("error"):
                raise ValidationError(f"Receipt {receipt_id} not found")

        else:  # Search by message_id
            logger.info(
                f"Debugging Gmail receipt: message_id={message_id}, user={user_id}"
            )
            all_receipts = client.get(
                "/api/gmail/receipts",
                params={
                    "user_id": user_id,
                    "limit": 1000,  # Get enough to search
                },
            )

            receipt = None
            for r in all_receipts:
                if r.get("message_id") == message_id:
                    receipt = r
                    receipt_id = r.get("id")
                    break

            if not receipt:
                raise ValidationError(
                    f"Receipt with message_id '{message_id}' not found"
                )

        # Analyze line_items structure
        line_items = receipt.get("line_items")
        line_items_debug = {
            "is_null": line_items is None,
            "is_list": isinstance(line_items, list),
            "is_string": isinstance(line_items, str),
            "is_dict": isinstance(line_items, dict),
            "type": str(type(line_items).__name__),
            "count": len(line_items)
            if isinstance(line_items, (list, dict, str))
            else 0,
            "has_data": bool(
                line_items
                and (
                    (isinstance(line_items, list) and len(line_items) > 0)
                    or (isinstance(line_items, dict) and len(line_items) > 0)
                )
            ),
        }

        # Extract sample items if available
        if isinstance(line_items, list) and len(line_items) > 0:
            line_items_debug["sample_items"] = line_items[:3]  # First 3 items
            line_items_debug["sample_structure"] = {
                "has_name": any(
                    item.get("name")
                    for item in line_items[:3]
                    if isinstance(item, dict)
                ),
                "has_price": any(
                    item.get("price")
                    for item in line_items[:3]
                    if isinstance(item, dict)
                ),
                "has_quantity": any(
                    item.get("quantity")
                    for item in line_items[:3]
                    if isinstance(item, dict)
                ),
            }

        # Transaction match analysis
        transaction_match = {
            "has_match": bool(receipt.get("transaction_id")),
            "transaction_id": receipt.get("transaction_id"),
            "match_confidence": receipt.get("match_confidence"),
            "transaction_description": receipt.get("transaction_description"),
            "transaction_amount": receipt.get("transaction_amount"),
        }

        # Parsing metadata analysis
        parsing_info = {
            "status": receipt.get("parsing_status"),
            "method": receipt.get("parse_method"),
            "confidence": receipt.get("parsing_confidence"),
            "error_message": receipt.get("parsing_error"),
            "parsed_at": receipt.get("parsed_at"),
            "vendor_parser_used": receipt.get("parse_method", "").startswith("vendor_"),
            "schema_extraction_used": receipt.get("parse_method")
            == "schema_extraction",
            "pattern_extraction_used": receipt.get("parse_method")
            == "pattern_extraction",
            "llm_enrichment_used": receipt.get("parse_method") == "llm_enrichment",
        }

        # Build comprehensive debug response
        debug_data = {
            "receipt_id": receipt_id,
            "message_id": receipt.get("message_id"),
            "user_id": user_id,
            # Core receipt data
            "merchant_name": receipt.get("merchant_name"),
            "merchant_name_normalized": receipt.get("merchant_name_normalized"),
            "total_amount": receipt.get("total_amount"),
            "currency": receipt.get("currency"),
            "receipt_date": receipt.get("receipt_date"),
            "order_id": receipt.get("order_id"),
            # Line items debugging
            "line_items_debug": line_items_debug,
            # Transaction matching
            "transaction_match": transaction_match,
            # Parsing metadata
            "parsing_info": parsing_info,
            # Email metadata
            "email_metadata": {
                "subject": receipt.get("subject"),
                "from_email": receipt.get("from_email"),
                "received_at": receipt.get("received_at"),
                "has_html_content": bool(receipt.get("html_content")),
                "has_text_content": bool(receipt.get("text_content")),
                "has_attachments": bool(receipt.get("pdf_attachments")),
            },
            # Full receipt data (for deep inspection)
            "full_receipt": receipt,
        }

        # Add diagnostic recommendations
        recommendations = []

        if not line_items_debug["has_data"]:
            recommendations.append(
                "⚠️ Line items missing or empty - check parser for this vendor"
            )

        if not transaction_match["has_match"]:
            recommendations.append(
                "⚠️ No transaction match - run matching or check merchant name normalization"
            )

        if parsing_info["status"] == "failed":
            recommendations.append(
                f"❌ Parsing failed: {parsing_info['error_message']}"
            )

        if parsing_info["status"] == "pending":
            recommendations.append(
                "⏳ Parsing still pending - trigger parser or check async queue"
            )

        if not parsing_info["vendor_parser_used"] and receipt.get("merchant_name"):
            recommendations.append(
                f"💡 No vendor-specific parser for '{receipt.get('merchant_name')}' - "
                f"consider adding one for better accuracy"
            )

        debug_data["recommendations"] = recommendations

        logger.info(
            f"Debug complete for receipt {receipt_id}: "
            f"status={parsing_info['status']}, "
            f"has_items={line_items_debug['has_data']}, "
            f"has_match={transaction_match['has_match']}"
        )

        return format_success_response(debug_data)

    except ValidationError as e:
        logger.error(f"Validation error in debug_gmail_receipt: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in debug_gmail_receipt: {e}")
        return format_error_response(e, {"tool": "debug_gmail_receipt"})


@mcp.tool()
async def search_gmail_receipts(
    user_id: int | None = None,
    merchant: str | None = None,
    parsing_status: str | None = None,
    has_line_items: bool | None = None,
    has_transaction_match: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict:
    """
    Search Gmail receipts by criteria to identify parsing issues.

    Flexible search across Gmail receipts with filtering by merchant,
    parsing status, data completeness, and date range. Helps identify
    patterns in parsing failures and missing data.

    Args:
        user_id: User ID (default: 1)
        merchant: Merchant name (partial match, case-insensitive)
        parsing_status: Filter by status - 'parsed', 'pending', 'failed', 'unparseable'
        has_line_items: Filter by line_items presence (true = has items, false = missing)
        has_transaction_match: Filter by transaction match (true = matched, false = unmatched)
        date_from: Start date (YYYY-MM-DD format, default: 30 days ago)
        date_to: End date (YYYY-MM-DD format, default: today)
        limit: Max results to return (default: 50, max: 200)

    Returns:
        Matching receipts with summary statistics

    Examples:
        # Find receipts missing line items
        search_gmail_receipts(has_line_items=False)

        # Find failed Amazon parses
        search_gmail_receipts(
            merchant="Amazon",
            parsing_status="failed"
        )

        # Find unmatched receipts from last week
        search_gmail_receipts(
            has_transaction_match=False,
            date_from="2024-12-20"
        )

        # Find pending parses
        search_gmail_receipts(parsing_status="pending", limit=100)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        date_from, date_to = apply_date_range_defaults(date_from, date_to)

        # Validate
        validate_user_id(user_id)
        if date_from and date_to:
            validate_date_range(date_from, date_to)

        # Limit bounds
        limit = max(1, min(limit, 200))

        client = get_flask_client()
        logger.info(
            f"Searching Gmail receipts: user={user_id}, merchant={merchant}, "
            f"status={parsing_status}, has_items={has_line_items}, "
            f"has_match={has_transaction_match}, dates={date_from} to {date_to}"
        )

        # Get all receipts (will filter client-side for more flexibility)
        params = {
            "user_id": user_id,
            "limit": 1000,  # Get enough to filter
        }

        if parsing_status:
            params["parsing_status"] = parsing_status

        all_receipts = client.get("/api/gmail/receipts", params=params)

        if not isinstance(all_receipts, list):
            all_receipts = []

        # Apply filters
        filtered = []
        for receipt in all_receipts:
            # Date filter
            receipt_date = receipt.get("received_at", "").split("T")[0]
            if date_from and receipt_date < date_from:
                continue
            if date_to and receipt_date > date_to:
                continue

            # Merchant filter (case-insensitive partial match)
            if merchant:
                merchant_name = receipt.get("merchant_name", "") or ""
                merchant_normalized = receipt.get("merchant_name_normalized", "") or ""
                if (
                    merchant.lower() not in merchant_name.lower()
                    and merchant.lower() not in merchant_normalized.lower()
                ):
                    continue

            # Line items filter
            if has_line_items is not None:
                line_items = receipt.get("line_items")
                has_items = bool(
                    line_items and isinstance(line_items, list) and len(line_items) > 0
                )
                if has_items != has_line_items:
                    continue

            # Transaction match filter
            if has_transaction_match is not None:
                has_match = bool(receipt.get("transaction_id"))
                if has_match != has_transaction_match:
                    continue

            filtered.append(receipt)

        # Sort by date (most recent first)
        filtered.sort(key=lambda x: x.get("received_at", ""), reverse=True)

        # Limit results
        results = filtered[:limit]

        # Calculate summary statistics
        stats = {
            "total_matched": len(filtered),
            "returned": len(results),
            "by_parsing_status": {},
            "with_line_items": 0,
            "without_line_items": 0,
            "with_transaction_match": 0,
            "without_transaction_match": 0,
            "merchants": {},
        }

        for receipt in results:
            # Count by parsing status
            status = receipt.get("parsing_status", "unknown")
            stats["by_parsing_status"][status] = (
                stats["by_parsing_status"].get(status, 0) + 1
            )

            # Count line items
            line_items = receipt.get("line_items")
            if line_items and isinstance(line_items, list) and len(line_items) > 0:
                stats["with_line_items"] += 1
            else:
                stats["without_line_items"] += 1

            # Count transaction matches
            if receipt.get("transaction_id"):
                stats["with_transaction_match"] += 1
            else:
                stats["without_transaction_match"] += 1

            # Count by merchant
            merchant_key = receipt.get("merchant_name_normalized", "unknown")
            stats["merchants"][merchant_key] = (
                stats["merchants"].get(merchant_key, 0) + 1
            )

        logger.info(
            f"Found {len(filtered)} matching receipts (returning {len(results)})"
        )

        return format_success_response(
            {
                "receipts": results,
                "statistics": stats,
                "filters_applied": {
                    "merchant": merchant,
                    "parsing_status": parsing_status,
                    "has_line_items": has_line_items,
                    "has_transaction_match": has_transaction_match,
                    "date_from": date_from,
                    "date_to": date_to,
                },
            }
        )

    except ValidationError as e:
        logger.error(f"Validation error in search_gmail_receipts: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in search_gmail_receipts: {e}")
        return format_error_response(e, {"tool": "search_gmail_receipts"})


@mcp.tool()
async def analyze_parsing_gaps(
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_receipts_threshold: int = 5,
) -> dict:
    """
    Generate comprehensive data quality report for Gmail receipts.

    Analyzes Gmail receipt parsing quality across all merchants and provides
    actionable recommendations for parser improvements. Identifies:
    - Receipts with missing line_items despite 'parsed' status
    - Failed parsing attempts with error patterns
    - Low confidence parses (< 50% confidence)
    - Merchant parsing success rates
    - Parse method effectiveness (vendor vs schema vs pattern)

    Args:
        user_id: User ID (default: 1)
        date_from: Start date for analysis (YYYY-MM-DD, default: 30 days ago)
        date_to: End date for analysis (YYYY-MM-DD, default: today)
        min_receipts_threshold: Min receipts per merchant to include in analysis (default: 5)

    Returns:
        Comprehensive parsing quality report with actionable recommendations

    Examples:
        # Analyze all receipts from last 30 days
        analyze_parsing_gaps()

        # Analyze last 90 days
        analyze_parsing_gaps(date_from="2024-10-01")

        # Analyze with lower threshold for small merchants
        analyze_parsing_gaps(min_receipts_threshold=2)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        date_from, date_to = apply_date_range_defaults(date_from, date_to)

        # Validate
        validate_user_id(user_id)
        if date_from and date_to:
            validate_date_range(date_from, date_to)

        client = get_flask_client()
        logger.info(
            f"Analyzing Gmail parsing gaps: user={user_id}, dates={date_from} to {date_to}"
        )

        # Get all receipts
        all_receipts = client.get(
            "/api/gmail/receipts",
            params={
                "user_id": user_id,
                "limit": 5000,  # Get all receipts
            },
        )

        if not isinstance(all_receipts, list):
            all_receipts = []

        # Filter by date range
        receipts = []
        for receipt in all_receipts:
            receipt_date = receipt.get("received_at", "").split("T")[0]
            if date_from and receipt_date < date_from:
                continue
            if date_to and receipt_date > date_to:
                continue
            receipts.append(receipt)

        # Initialize analysis structures
        total_receipts = len(receipts)
        parsing_status_counts = {}
        parse_method_counts = {}
        merchant_analysis = {}
        issues = []

        # Analyze each receipt
        for receipt in receipts:
            status = receipt.get("parsing_status", "unknown")
            method = receipt.get("parse_method", "unknown")
            merchant = receipt.get("merchant_name_normalized", "unknown")

            # Count by status and method
            parsing_status_counts[status] = parsing_status_counts.get(status, 0) + 1
            parse_method_counts[method] = parse_method_counts.get(method, 0) + 1

            # Initialize merchant stats
            if merchant not in merchant_analysis:
                merchant_analysis[merchant] = {
                    "total": 0,
                    "parsed": 0,
                    "failed": 0,
                    "pending": 0,
                    "with_line_items": 0,
                    "without_line_items": 0,
                    "with_transaction_match": 0,
                    "parse_methods": {},
                    "low_confidence": 0,
                }

            # Update merchant stats
            merchant_stats = merchant_analysis[merchant]
            merchant_stats["total"] += 1

            if status == "parsed":
                merchant_stats["parsed"] += 1
            elif status == "failed":
                merchant_stats["failed"] += 1
            elif status == "pending":
                merchant_stats["pending"] += 1

            # Check line items
            line_items = receipt.get("line_items")
            if line_items and isinstance(line_items, list) and len(line_items) > 0:
                merchant_stats["with_line_items"] += 1
            else:
                merchant_stats["without_line_items"] += 1

                # Issue: Parsed but no line items
                if status == "parsed":
                    issues.append(
                        {
                            "type": "missing_line_items",
                            "severity": "medium",
                            "receipt_id": receipt.get("id"),
                            "merchant": merchant,
                            "message": f"Receipt {receipt.get('id')} marked as 'parsed' but has no line_items",
                        }
                    )

            # Check transaction match
            if receipt.get("transaction_id"):
                merchant_stats["with_transaction_match"] += 1

            # Count parse methods
            merchant_stats["parse_methods"][method] = (
                merchant_stats["parse_methods"].get(method, 0) + 1
            )

            # Check confidence
            confidence = receipt.get("parsing_confidence", 1.0)
            if confidence < 0.5:
                merchant_stats["low_confidence"] += 1
                issues.append(
                    {
                        "type": "low_confidence",
                        "severity": "low",
                        "receipt_id": receipt.get("id"),
                        "merchant": merchant,
                        "confidence": confidence,
                        "message": f"Low confidence parse ({confidence:.1%}) for {merchant}",
                    }
                )

            # Failed parsing
            if status == "failed":
                issues.append(
                    {
                        "type": "parsing_failed",
                        "severity": "high",
                        "receipt_id": receipt.get("id"),
                        "merchant": merchant,
                        "error": receipt.get("parsing_error"),
                        "message": f"Parsing failed for {merchant}: {receipt.get('parsing_error')}",
                    }
                )

        # Calculate merchant success rates
        merchant_summary = []
        for merchant, stats in merchant_analysis.items():
            if stats["total"] >= min_receipts_threshold:
                success_rate = (
                    stats["parsed"] / stats["total"] if stats["total"] > 0 else 0
                )
                line_items_rate = (
                    stats["with_line_items"] / stats["total"]
                    if stats["total"] > 0
                    else 0
                )
                match_rate = (
                    stats["with_transaction_match"] / stats["total"]
                    if stats["total"] > 0
                    else 0
                )

                merchant_summary.append(
                    {
                        "merchant": merchant,
                        "total_receipts": stats["total"],
                        "success_rate": round(success_rate * 100, 1),
                        "line_items_rate": round(line_items_rate * 100, 1),
                        "match_rate": round(match_rate * 100, 1),
                        "failed_count": stats["failed"],
                        "pending_count": stats["pending"],
                        "low_confidence_count": stats["low_confidence"],
                        "primary_parse_method": max(
                            stats["parse_methods"], key=stats["parse_methods"].get
                        )
                        if stats["parse_methods"]
                        else "unknown",
                    }
                )

        # Sort by total receipts (most important merchants first)
        merchant_summary.sort(key=lambda x: x["total_receipts"], reverse=True)

        # Generate recommendations
        recommendations = []

        # Check for merchants with low success rates
        for m in merchant_summary:
            if m["success_rate"] < 80 and m["total_receipts"] >= min_receipts_threshold:
                recommendations.append(
                    {
                        "priority": "high",
                        "category": "parser_improvement",
                        "merchant": m["merchant"],
                        "message": f"Improve parser for '{m['merchant']}' - only {m['success_rate']}% success rate ({m['failed_count']} failures)",
                        "action": "Review failed receipts and add/improve vendor-specific parser",
                    }
                )

        # Check for merchants with low line_items rate
        for m in merchant_summary:
            if (
                m["line_items_rate"] < 50
                and m["total_receipts"] >= min_receipts_threshold
            ):
                recommendations.append(
                    {
                        "priority": "medium",
                        "category": "data_quality",
                        "merchant": m["merchant"],
                        "message": f"'{m['merchant']}' has low line items extraction ({m['line_items_rate']}%)",
                        "action": "Review parser to ensure line_items are being extracted correctly",
                    }
                )

        # Check for merchants with low match rate
        for m in merchant_summary:
            if m["match_rate"] < 30 and m["total_receipts"] >= min_receipts_threshold:
                recommendations.append(
                    {
                        "priority": "medium",
                        "category": "transaction_matching",
                        "merchant": m["merchant"],
                        "message": f"'{m['merchant']}' has low transaction match rate ({m['match_rate']}%)",
                        "action": "Review merchant name normalization and matching rules",
                    }
                )

        # Check parse method effectiveness
        total_parsed = parsing_status_counts.get("parsed", 0)
        if total_parsed > 0:
            vendor_parses = sum(
                count
                for method, count in parse_method_counts.items()
                if method.startswith("vendor_")
            )
            vendor_rate = vendor_parses / total_parsed if total_parsed > 0 else 0

            if vendor_rate < 0.5:
                recommendations.append(
                    {
                        "priority": "low",
                        "category": "parser_coverage",
                        "message": f"Only {vendor_rate:.1%} of parses use vendor-specific parsers",
                        "action": "Consider adding more vendor-specific parsers for common merchants",
                    }
                )

        # Sort recommendations by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 99))

        # Build comprehensive report
        report = {
            "date_range": {"from": date_from, "to": date_to},
            "overall_statistics": {
                "total_receipts": total_receipts,
                "parsing_status": parsing_status_counts,
                "parse_methods": parse_method_counts,
                "total_issues": len(issues),
                "issues_by_severity": {
                    "high": len([i for i in issues if i["severity"] == "high"]),
                    "medium": len([i for i in issues if i["severity"] == "medium"]),
                    "low": len([i for i in issues if i["severity"] == "low"]),
                },
            },
            "merchant_analysis": merchant_summary,
            "issues": issues[:50],  # Limit to 50 most recent issues
            "recommendations": recommendations,
            "summary": {
                "total_merchants": len(merchant_summary),
                "merchants_needing_attention": len(
                    [m for m in merchant_summary if m["success_rate"] < 80]
                ),
                "total_failed_parses": parsing_status_counts.get("failed", 0),
                "total_pending_parses": parsing_status_counts.get("pending", 0),
            },
        }

        logger.info(
            f"Analysis complete: {total_receipts} receipts, {len(merchant_summary)} merchants, "
            f"{len(issues)} issues, {len(recommendations)} recommendations"
        )

        return format_success_response(report)

    except ValidationError as e:
        logger.error(f"Validation error in analyze_parsing_gaps: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in analyze_parsing_gaps: {e}")
        return format_error_response(e, {"tool": "analyze_parsing_gaps"})
