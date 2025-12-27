#!/usr/bin/env python3
"""
Gmail Sync Performance Testing Script

Tests the Gmail sync performance with different configurations.
Usage:
    python test_gmail_sync_performance.py --connection-id 1 --limit 100
    python test_gmail_sync_performance.py --connection-id 1 --limit 100 --sequential
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_postgres as database
from mcp.gmail_sync import sync_receipts_full


def test_sync_performance(connection_id: int, message_limit: int = 100, use_parallel: bool = True):
    """
    Test Gmail sync performance with a limited number of messages.

    Args:
        connection_id: Gmail connection ID to use
        message_limit: Maximum number of messages to sync (default: 100)
        use_parallel: Whether to use parallel fetching (default: True)
    """
    # Temporarily override environment variables for this test
    original_parallel = os.getenv('GMAIL_PARALLEL_FETCH')
    original_workers = os.getenv('GMAIL_SYNC_WORKERS')

    try:
        # Set test configuration
        os.environ['GMAIL_PARALLEL_FETCH'] = 'true' if use_parallel else 'false'
        os.environ['GMAIL_SYNC_WORKERS'] = '5'

        print(f"\n{'='*80}")
        print(f"GMAIL SYNC PERFORMANCE TEST")
        print(f"{'='*80}")
        print(f"Connection ID: {connection_id}")
        print(f"Message Limit: {message_limit}")
        print(f"Parallel Fetch: {use_parallel}")
        print(f"Workers: {os.environ['GMAIL_SYNC_WORKERS']}")
        print(f"{'='*80}\n")

        # Verify connection exists
        connection = database.get_gmail_connection_by_id(connection_id)
        if not connection:
            print(f"❌ Error: Gmail connection {connection_id} not found")
            return

        print(f"📧 Testing sync for: {connection['email_address']}")
        print(f"   Status: {connection.get('connection_status', 'Unknown')}")
        print(f"   Last sync: {connection.get('last_synced_at', 'Never')}\n")

        # Create a sync job
        job_id = database.create_gmail_sync_job(connection_id, 'full')
        print(f"📊 Created sync job ID: {job_id}\n")

        # Use a narrow date range to limit messages (last 1 month)
        # This is a workaround since we can't limit directly in the sync function
        from_date = datetime.now() - timedelta(days=30)

        # Run sync (it's a generator, so we need to consume it)
        print(f"🔄 Starting sync with date range (last 30 days)...\n")
        print(f"   Note: Will process all messages in date range")
        print(f"   Recommended: Select a date range with ~{message_limit} messages\n")

        message_count = 0
        for progress in sync_receipts_full(
            connection_id=connection_id,
            job_id=job_id,
            from_date=from_date,
            force_reparse=False
        ):
            # Print progress updates
            if progress.get('status') == 'scanning':
                total = progress.get('total_messages', 0)
                print(f"📊 Found {total} messages to process")

                # Warn if too many messages
                if total > message_limit * 2:
                    print(f"⚠️  Warning: Found {total} messages (recommended: ~{message_limit})")
                    print(f"   This test may take longer than expected")
                    print(f"   Consider using a smaller date range for faster testing\n")

            elif progress.get('status') == 'processing':
                processed = progress.get('processed', 0)
                total = progress.get('total_messages', 0)

                # Print progress every 10 messages
                if processed % 10 == 0 or processed == total:
                    print(f"   Progress: {processed}/{total} messages processed")

                message_count = processed

            elif progress.get('status') == 'completed':
                print(f"\n✅ Sync completed!")
                print(f"   Processed: {progress.get('processed', 0)}")
                print(f"   Parsed: {progress.get('parsed', 0)}")
                print(f"   Failed: {progress.get('failed', 0)}")
                print(f"   Duplicates: {progress.get('duplicates', 0)}")
                break

        print(f"\n{'='*80}")
        print(f"TEST COMPLETED")
        print(f"{'='*80}")
        print(f"Check the PERFORMANCE SUMMARY above for detailed metrics\n")

    except Exception as e:
        print(f"\n❌ Error during sync test: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Restore original environment variables
        if original_parallel:
            os.environ['GMAIL_PARALLEL_FETCH'] = original_parallel
        elif 'GMAIL_PARALLEL_FETCH' in os.environ:
            del os.environ['GMAIL_PARALLEL_FETCH']

        if original_workers:
            os.environ['GMAIL_SYNC_WORKERS'] = original_workers
        elif 'GMAIL_SYNC_WORKERS' in os.environ:
            del os.environ['GMAIL_SYNC_WORKERS']


def main():
    parser = argparse.ArgumentParser(description='Test Gmail sync performance')
    parser.add_argument('--connection-id', type=int, required=True,
                        help='Gmail connection ID to test')
    parser.add_argument('--limit', type=int, default=100,
                        help='Maximum number of messages to sync (default: 100)')
    parser.add_argument('--sequential', action='store_true',
                        help='Use sequential processing instead of parallel (for baseline)')

    args = parser.parse_args()

    test_sync_performance(
        connection_id=args.connection_id,
        message_limit=args.limit,
        use_parallel=not args.sequential
    )


if __name__ == '__main__':
    main()
