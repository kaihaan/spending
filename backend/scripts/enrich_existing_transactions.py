#!/usr/bin/env python3
"""
Enrich existing transactions with LLM categorization.

This script processes existing transactions and applies LLM enrichment,
updating their categories and enrichment metadata.

Usage:
    # Enrich all 'Other' category transactions (default)
    python enrich_existing_transactions.py

    # Enrich specific category
    python enrich_existing_transactions.py --category "Uncategorized"

    # Enrich all transactions (no category filter)
    python enrich_existing_transactions.py --category ""

    # Enrich with limit
    python enrich_existing_transactions.py --limit 100

    # Force re-enrich (bypass cache)
    python enrich_existing_transactions.py --force-refresh
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# Load environment
load_dotenv(override=True)

import database


def enrich_transactions(category="Other", limit=50, force_refresh=False, verbose=True):
    """
    Enrich existing transactions with LLM.

    Args:
        category: Filter by category (default: 'Other')
        limit: Maximum transactions to process
        force_refresh: Bypass cache and re-enrich
        verbose: Print progress messages

    Returns:
        Enrichment statistics dict
    """
    try:
        from mcp.llm_enricher import get_enricher

        # Get enricher
        enricher = get_enricher()
        if not enricher:
            print("❌ LLM enrichment not configured. Check your .env file.")
            return None

        if verbose:
            print("\n" + "=" * 70)
            print("🔄 ENRICHING EXISTING TRANSACTIONS")
            print("=" * 70)

        # Get all transactions
        all_transactions = database.get_all_transactions() or []
        if verbose:
            print(f"📊 Total transactions in database: {len(all_transactions)}")

        # Filter by category
        if category:
            transactions_to_enrich = [
                t for t in all_transactions if t.get("category") == category
            ]
        else:
            transactions_to_enrich = all_transactions

        if verbose:
            filter_msg = f'category="{category}"' if category else "all"
            print(
                f"🔍 Found {len(transactions_to_enrich)} transactions matching filter ({filter_msg})"
            )

        # Apply limit
        transactions_to_enrich = transactions_to_enrich[:limit]

        if not transactions_to_enrich:
            print("⚠️  No transactions found to enrich.")
            return None

        transaction_ids = [t["id"] for t in transactions_to_enrich]

        if verbose:
            print(f"🎯 Processing {len(transaction_ids)} transactions...")
            print(f"   Force refresh: {force_refresh}")
            print(f"   Cache enabled: {enricher.config.cache_enabled}")
            print()

        # Determine direction
        has_expenses = any(t.get("amount", 0) < 0 for t in transactions_to_enrich)
        has_income = any(t.get("amount", 0) > 0 for t in transactions_to_enrich)

        if has_expenses and not has_income:
            direction = "out"
        elif has_income and not has_expenses:
            direction = "in"
        else:
            direction = "out"

        if verbose:
            print(f"📈 Enrichment direction: {direction}")
            print()

        # Run enrichment
        stats = enricher.enrich_transactions(
            transaction_ids=transaction_ids,
            direction=direction,
            force_refresh=force_refresh,
        )

        # Print results
        print("=" * 70)
        print("✅ ENRICHMENT COMPLETE")
        print("=" * 70)
        print(f"✔️  Successful:     {stats.successful_enrichments}")
        print(f"❌ Failed:         {stats.failed_enrichments}")
        print(f"💾 Cache hits:     {stats.cached_hits}")
        print(f"🔗 API calls:      {stats.api_calls_made}")
        print(f"📝 Tokens used:    {stats.total_tokens_used}")
        print(f"💰 Estimated cost: ${stats.total_cost:.6f}")
        if stats.retry_queue:
            print(f"🔄 Retries queued: {len(stats.retry_queue)}")
        print("=" * 70)
        print()

        return {
            "successful": stats.successful_enrichments,
            "failed": stats.failed_enrichments,
            "cached_hits": stats.cached_hits,
            "api_calls": stats.api_calls_made,
            "total_tokens": stats.total_tokens_used,
            "total_cost": stats.total_cost,
            "retry_queue_size": len(stats.retry_queue) if stats.retry_queue else 0,
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


def show_stats(verbose=True):
    """Show enrichment statistics."""
    try:
        all_transactions = database.get_all_transactions() or []

        # Count by category
        category_counts = {}
        for txn in all_transactions:
            cat = txn.get("category", "Unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Check enrichment status
        enriched_count = 0
        for txn in all_transactions:
            txn_id = txn.get("id")
            if txn_id and database.is_transaction_enriched(txn_id):
                enriched_count += 1

        unenriched_count = len(all_transactions) - enriched_count
        enrichment_pct = round(
            (enriched_count / len(all_transactions) * 100) if all_transactions else 0, 1
        )

        print("\n" + "=" * 70)
        print("📊 ENRICHMENT STATUS")
        print("=" * 70)
        print(f"Total transactions:      {len(all_transactions)}")
        print(f"Enriched:                {enriched_count}")
        print(f"Unenriched:              {unenriched_count}")
        print(f"Enrichment percentage:   {enrichment_pct}%")
        print()
        print("Transactions by category:")
        for cat in sorted(category_counts.keys()):
            count = category_counts[cat]
            pct = round(
                (count / len(all_transactions) * 100) if all_transactions else 0, 1
            )
            print(f"  {cat:20s}: {count:4d} ({pct:5.1f}%)")
        print("=" * 70)
        print()

    except Exception as e:
        print(f"❌ Error getting stats: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrich existing transactions with LLM categorization"
    )
    parser.add_argument(
        "--category",
        default="Other",
        help='Category to filter by (default: Other). Use "" to enrich all.',
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum transactions to process (default: 50)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass cache and re-enrich transactions",
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show enrichment statistics only"
    )

    args = parser.parse_args()

    try:
        # Show stats first
        show_stats()

        # If stats-only, exit
        if args.stats:
            sys.exit(0)

        # Otherwise, run enrichment
        result = enrich_transactions(
            category=args.category if args.category != '""' else "",
            limit=args.limit,
            force_refresh=args.force_refresh,
        )

        if result:
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️  Enrichment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
