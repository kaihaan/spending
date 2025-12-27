"""Real-time statistics tracking for Gmail sync operations.

This module provides comprehensive statistics collection during Gmail sync:
- Per-parse-method success/failure counts (vendor_amazon, schema_org, etc.)
- Per-merchant success/failure counts
- Datapoint extraction tracking (merchant, brand, amount, date, order_id, line_items)
- Error type aggregation
- Performance metrics (parse duration, LLM costs)

Usage:
    from mcp.statistics_tracker import GmailSyncStatistics

    # Initialize at start of sync
    stats = GmailSyncStatistics(connection_id=1, sync_job_id=123)

    # Record each parse attempt
    stats.record_parse_attempt(
        message_id='msg123',
        sender_domain='amazon.co.uk',
        parse_result={'total_amount': 45.99, 'merchant_name': 'Amazon', ...},
        duration_ms=150
    )

    # Flush aggregated stats to database at end of sync
    stats.flush()
"""

from collections import defaultdict
from typing import Any

import database as db
from mcp.logging_config import get_logger

logger = get_logger(__name__)


class GmailSyncStatistics:
    """Tracks detailed statistics during Gmail sync workflow.

    Attributes:
        connection_id: Gmail connection ID
        sync_job_id: Sync job ID
        by_parse_method: Dict of {method: {parsed: N, failed: N}}
        by_merchant: Dict of {merchant: {parsed: N, failed: N}}
        datapoint_extraction: Nested dict tracking field extraction success
        errors: Dict of {error_type: count}
        parse_durations: List of parse durations in ms
        total_llm_cost_cents: Total LLM cost across all parses
    """

    def __init__(self, connection_id: int, sync_job_id: int):
        """Initialize statistics tracker.

        Args:
            connection_id: Gmail connection ID
            sync_job_id: Sync job ID for this sync operation
        """
        self.connection_id = connection_id
        self.sync_job_id = sync_job_id

        # Counters by parse method (user requirement)
        # Example: {'vendor_amazon': {'parsed': 45, 'failed': 2}}
        self.by_parse_method = defaultdict(lambda: {"parsed": 0, "failed": 0})

        # Counters by merchant (user requirement)
        # Example: {'amazon.co.uk': {'parsed': 45, 'failed': 2}}
        self.by_merchant = defaultdict(lambda: {"parsed": 0, "failed": 0})

        # Datapoint extraction tracking (user requirement)
        # Tracks attempted and successful extractions for each field
        self.datapoint_extraction = {
            "merchant": {"attempted": 0, "success": 0},
            "brand": {"attempted": 0, "success": 0},
            "amount": {"attempted": 0, "success": 0},
            "date": {"attempted": 0, "success": 0},
            "order_id": {"attempted": 0, "success": 0},
            "line_items": {"attempted": 0, "success": 0},
        }

        # Error tracking by type
        self.errors = defaultdict(int)

        # Performance tracking
        self.parse_durations = []
        self.total_llm_cost_cents = 0

    def record_parse_attempt(
        self,
        message_id: str,
        sender_domain: str,
        parse_result: dict[str, Any],
        duration_ms: int | None = None,
        llm_cost_cents: int | None = None,
    ) -> None:
        """Record parsing attempt with all datapoints.

        Args:
            message_id: Gmail message ID
            sender_domain: Email sender domain
            parse_result: Dict with parse result (may be None if failed)
            duration_ms: Parse duration in milliseconds (optional)
            llm_cost_cents: LLM cost in cents if LLM was used (optional)

        Example parse_result:
            {
                'parse_method': 'vendor_amazon',
                'merchant_name': 'Amazon',
                'merchant_name_normalized': 'amazon',
                'brand': 'Amazon Fresh',
                'total_amount': 45.99,
                'receipt_date': '2025-12-26',
                'order_id': 'AB123',
                'line_items': [...],
                'parsing_status': 'parsed'
            }
        """
        # Determine parse method and status
        parse_method = (
            parse_result.get("parse_method", "unknown") if parse_result else "unknown"
        )
        merchant = (
            parse_result.get("merchant_name_normalized", sender_domain)
            if parse_result
            else sender_domain
        )
        status = self._get_parsing_status(parse_result)

        # Update parse method counters
        if status == "parsed":
            self.by_parse_method[parse_method]["parsed"] += 1
            self.by_merchant[merchant]["parsed"] += 1
        else:
            self.by_parse_method[parse_method]["failed"] += 1
            self.by_merchant[merchant]["failed"] += 1

        # Track datapoint extraction (user requirement)
        if parse_result:
            datapoints = self._extract_datapoint_flags(parse_result)

            for field, extracted in datapoints.items():
                self.datapoint_extraction[field]["attempted"] += 1
                if extracted:
                    self.datapoint_extraction[field]["success"] += 1

        # Track performance
        if duration_ms is not None:
            self.parse_durations.append(duration_ms)

        if llm_cost_cents is not None:
            self.total_llm_cost_cents += llm_cost_cents

        # Save detailed statistics to database for message-level analytics
        try:
            db.save_gmail_parse_statistic(
                connection_id=self.connection_id,
                sync_job_id=self.sync_job_id,
                message_id=message_id,
                sender_domain=sender_domain,
                merchant_normalized=merchant,
                parse_method=parse_method,
                merchant_extracted=datapoints.get("merchant", False)
                if parse_result
                else False,
                brand_extracted=datapoints.get("brand", False)
                if parse_result
                else False,
                amount_extracted=datapoints.get("amount", False)
                if parse_result
                else False,
                date_extracted=datapoints.get("date", False) if parse_result else False,
                order_id_extracted=datapoints.get("order_id", False)
                if parse_result
                else False,
                line_items_extracted=datapoints.get("line_items", False)
                if parse_result
                else False,
                parse_duration_ms=duration_ms,
                llm_cost_cents=llm_cost_cents,
                parsing_status=status,
                parsing_error=parse_result.get("parsing_error")
                if parse_result
                else "Parse failed",
            )
        except Exception as e:
            # Don't let statistics tracking crash sync
            logger.warning(
                f"Failed to save parse statistic: {e}",
                extra={"sync_job_id": self.sync_job_id, "message_id": message_id},
            )

    def record_error(self, error_type: str) -> None:
        """Record an error by type.

        Args:
            error_type: Error type (api_error, timeout, parse_error, etc.)
        """
        self.errors[error_type] += 1

    def to_dict(self) -> dict[str, Any]:
        """Export statistics for JSON storage in sync_jobs.stats.

        Returns:
            Dictionary with aggregated statistics:
            {
                "by_parse_method": {"vendor_amazon": {"parsed": 45, "failed": 2}},
                "by_merchant": {"amazon.co.uk": {"parsed": 45, "failed": 2}},
                "datapoint_extraction": {
                    "merchant": {"attempted": 100, "success": 95},
                    "amount": {"attempted": 100, "success": 88}
                },
                "errors": {"api_error": 3, "parse_error": 5},
                "performance": {
                    "avg_parse_duration_ms": 150,
                    "total_llm_cost_cents": 25
                }
            }
        """
        # Calculate average parse duration
        avg_parse_duration_ms = None
        if self.parse_durations:
            avg_parse_duration_ms = int(
                sum(self.parse_durations) / len(self.parse_durations)
            )

        return {
            "by_parse_method": dict(self.by_parse_method),
            "by_merchant": dict(self.by_merchant),
            "datapoint_extraction": self.datapoint_extraction,
            "errors": dict(self.errors),
            "performance": {
                "avg_parse_duration_ms": avg_parse_duration_ms,
                "total_llm_cost_cents": self.total_llm_cost_cents,
            },
        }

    def flush(self) -> None:
        """Save aggregated statistics to sync job.

        Should be called at the end of sync to persist all collected stats.
        """
        try:
            stats_dict = self.to_dict()
            db.update_gmail_sync_job_stats(self.sync_job_id, stats_dict)

            logger.info(
                f"Flushed sync statistics: {len(self.by_parse_method)} parse methods, "
                f"{len(self.by_merchant)} merchants",
                extra={"sync_job_id": self.sync_job_id},
            )
        except Exception as e:
            logger.error(
                f"Failed to flush sync statistics: {e}",
                extra={"sync_job_id": self.sync_job_id},
                exc_info=True,
            )

    def _get_parsing_status(self, parse_result: dict[str, Any] | None) -> str:
        """Determine parsing status from result.

        Args:
            parse_result: Parse result dict or None

        Returns:
            Status string: 'parsed', 'unparseable', 'filtered', or 'failed'
        """
        if not parse_result:
            return "failed"

        if parse_result.get("parsing_status"):
            return parse_result["parsing_status"]

        # Infer status from contents
        if parse_result.get("pre_filter_reject"):
            return "filtered"
        if parse_result.get("total_amount") or parse_result.get("line_items"):
            return "parsed"
        return "unparseable"

    def _extract_datapoint_flags(self, parse_result: dict[str, Any]) -> dict[str, bool]:
        """Extract boolean flags for datapoint extraction success.

        Args:
            parse_result: Parse result dict

        Returns:
            Dict with boolean flags for each datapoint:
            {
                'merchant': True,
                'brand': False,
                'amount': True,
                ...
            }
        """
        return {
            "merchant": parse_result.get("merchant_name") is not None,
            "brand": parse_result.get("brand") is not None,
            "amount": parse_result.get("total_amount") is not None,
            "date": parse_result.get("receipt_date") is not None,
            "order_id": parse_result.get("order_id") is not None,
            "line_items": bool(parse_result.get("line_items")),
        }

    def get_summary(self) -> str:
        """Get human-readable summary of statistics.

        Returns:
            Summary string for logging/display
        """
        total_parsed = sum(method["parsed"] for method in self.by_parse_method.values())
        total_failed = sum(method["failed"] for method in self.by_parse_method.values())
        total_attempts = total_parsed + total_failed

        if total_attempts == 0:
            return "No parse attempts recorded"

        success_rate = (
            (total_parsed / total_attempts * 100) if total_attempts > 0 else 0
        )

        lines = [
            f"Parse Success: {total_parsed}/{total_attempts} ({success_rate:.1f}%)",
            f"Parse Methods: {len(self.by_parse_method)}",
            f"Merchants: {len(self.by_merchant)}",
        ]

        # Add datapoint extraction rates
        for field, stats in self.datapoint_extraction.items():
            if stats["attempted"] > 0:
                rate = stats["success"] / stats["attempted"] * 100
                lines.append(
                    f"  {field.capitalize()}: {stats['success']}/{stats['attempted']} ({rate:.1f}%)"
                )

        return "\n".join(lines)
