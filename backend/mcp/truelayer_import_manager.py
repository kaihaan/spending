"""
TrueLayer Import Job Manager

Manages batch imports with date ranges, account selection, and progress tracking.
Supports both sequential and parallel import strategies.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import database_postgres as database
from .truelayer_sync import sync_account_transactions, identify_transaction_merchant
from .truelayer_auth import decrypt_token

logger = logging.getLogger(__name__)


class ImportJob:
    """Manages a batch import job for TrueLayer transactions."""

    def __init__(self, job_id: int):
        """
        Initialize ImportJob.

        Args:
            job_id: Import job ID
        """
        self.job_id = job_id
        self.job_data = database.get_import_job(job_id)
        if not self.job_data:
            raise ValueError(f"Import job {job_id} not found")

        self.user_id = self.job_data['user_id']
        self.connection_id = self.job_data['connection_id']
        self.account_ids = self.job_data.get('account_ids', [])
        self.card_ids = self.job_data.get('card_ids', [])
        self.from_date = self.job_data.get('from_date')
        self.to_date = self.job_data.get('to_date')
        self.auto_enrich = self.job_data.get('auto_enrich', True)
        self.batch_size = self.job_data.get('batch_size', 50)

    def plan(self) -> Dict:
        """
        Plan import and estimate transaction count, duration, and cost.

        Returns:
            Dictionary with estimates
        """
        logger.info(f"Planning import job {self.job_id}")

        try:
            accounts = self._get_accounts_to_sync()
            estimated_transactions = 0
            total_accounts = len(accounts)

            # Rough estimate: 10 transactions per day
            if self.from_date and self.to_date:
                from datetime import datetime as dt, date
                # Convert date objects to ISO strings if needed (PostgreSQL returns DATE columns as date objects)
                from_date_str = self.from_date.isoformat() if isinstance(self.from_date, date) else self.from_date
                to_date_str = self.to_date.isoformat() if isinstance(self.to_date, date) else self.to_date
                from_dt = dt.strptime(from_date_str, '%Y-%m-%d')
                to_dt = dt.strptime(to_date_str, '%Y-%m-%d')
                days_span = (to_dt - from_dt).days
                estimated_transactions = days_span * 10 * total_accounts

            # Estimate duration: 10 seconds per account + 0.1 sec per transaction
            estimated_duration = (total_accounts * 10) + (estimated_transactions * 0.1)

            # Estimate API cost: $0.001 per API call, ~1 call per 100 txns
            api_calls_estimate = total_accounts + (estimated_transactions / 100)
            estimated_cost = api_calls_estimate * 0.001

            logger.info(f"✓ Plan complete: {estimated_transactions} txns, {estimated_duration:.0f}s, ${estimated_cost:.2f}")

            return {
                'job_id': self.job_id,
                'status': 'planned',
                'estimated_accounts': total_accounts,
                'estimated_transactions': estimated_transactions,
                'estimated_duration_seconds': int(estimated_duration),
                'estimated_cost': round(estimated_cost, 4),
                'date_range': {
                    'from': self.from_date,
                    'to': self.to_date
                },
                'accounts': [{'id': a['id'], 'display_name': a['display_name']} for a in accounts]
            }

        except Exception as e:
            logger.error(f"❌ Planning failed: {e}")
            raise

    def execute(self, use_parallel: bool = False, max_workers: int = 3) -> Dict:
        """
        Execute import job.

        Args:
            use_parallel: Whether to parallelize account syncing
            max_workers: Max concurrent workers if parallel

        Returns:
            Dictionary with sync results
        """
        logger.info(f"🔄 Executing import job {self.job_id}")

        try:
            # Mark as running
            estimated_time = datetime.now(timezone.utc).isoformat()
            database.update_import_job_status(
                self.job_id,
                'running',
                estimated_completion=estimated_time
            )

            accounts = self._get_accounts_to_sync()
            logger.info(f"   Found {len(accounts)} accounts to sync")

            if use_parallel:
                results = self._execute_parallel(accounts, max_workers)
            else:
                results = self._execute_sequential(accounts)

            # Aggregate results
            total_synced = sum(r.get('synced', 0) for r in results)
            total_duplicates = sum(r.get('duplicates', 0) for r in results)
            total_errors = sum(r.get('errors', 0) for r in results)

            # Mark job completed
            database.mark_job_completed(
                self.job_id,
                total_synced=total_synced,
                total_duplicates=total_duplicates,
                total_errors=total_errors
            )

            logger.info(f"✅ Job complete: {total_synced} synced, {total_duplicates} dupes, {total_errors} errors")

            return {
                'job_id': self.job_id,
                'status': 'completed',
                'summary': {
                    'total_synced': total_synced,
                    'total_duplicates': total_duplicates,
                    'total_errors': total_errors
                },
                'results': results
            }

        except Exception as e:
            logger.error(f"❌ Execution failed: {e}")
            database.update_import_job_status(
                self.job_id,
                'failed',
                error_message=str(e)
            )
            raise

    def _execute_sequential(self, accounts: List[Dict]) -> List[Dict]:
        """Execute accounts sequentially."""
        logger.info("   Executing sequentially")
        results = []

        for account in accounts:
            try:
                result = self._sync_single_account(account)
                results.append(result)
            except Exception as e:
                logger.error(f"   ❌ Error syncing {account['display_name']}: {e}")
                results.append({
                    'account_id': account['id'],
                    'status': 'failed',
                    'error': str(e),
                    'synced': 0,
                    'duplicates': 0,
                    'errors': 1
                })

        return results

    def _execute_parallel(self, accounts: List[Dict], max_workers: int) -> List[Dict]:
        """Execute accounts in parallel using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info(f"   Executing in parallel ({max_workers} workers)")
        results = []

        with ThreadPoolExecutor(max_workers=min(max_workers, len(accounts))) as executor:
            futures = {
                executor.submit(self._sync_single_account, account): account
                for account in accounts
            }

            for future in as_completed(futures):
                account = futures[future]
                try:
                    result = future.result(timeout=60)
                    results.append(result)
                except Exception as e:
                    logger.error(f"   ❌ Error syncing {account['display_name']}: {e}")
                    results.append({
                        'account_id': account['id'],
                        'status': 'failed',
                        'error': str(e),
                        'synced': 0,
                        'duplicates': 0,
                        'errors': 1
                    })

        return results

    def _sync_single_account(self, account: Dict) -> Dict:
        """Sync a single account."""
        account_id = account['id']
        truelayer_account_id = account['account_id']
        display_name = account['display_name']

        logger.info(f"   Syncing: {display_name}")

        try:
            # Get connection and refresh token if needed
            from .truelayer_sync import refresh_token_if_needed
            connection = database.get_connection(self.connection_id)
            if not connection:
                raise ValueError(f"Connection {self.connection_id} not found")

            # Refresh token if expired before making API calls
            connection = refresh_token_if_needed(self.connection_id, connection)
            access_token = decrypt_token(connection.get('access_token'))

            # Sync with custom date range
            result = sync_account_transactions(
                connection_id=self.connection_id,
                truelayer_account_id=truelayer_account_id,
                db_account_id=account_id,
                access_token=access_token,
                from_date=self.from_date,
                to_date=self.to_date,
                import_job_id=self.job_id,
                use_incremental=False  # Explicit date range, not incremental
            )

            # Record progress
            database.add_import_progress(
                job_id=self.job_id,
                account_id=account_id,
                synced=result.get('synced', 0),
                duplicates=result.get('duplicates', 0),
                errors=result.get('errors', 0),
                error_msg=result.get('error_message')
            )

            logger.info(f"     ✓ {result.get('synced', 0)} synced")
            return result

        except Exception as e:
            logger.error(f"     ✗ Error: {e}")
            database.add_import_progress(
                job_id=self.job_id,
                account_id=account_id,
                synced=0,
                duplicates=0,
                errors=1,
                error_msg=str(e)
            )
            raise

    def _get_accounts_to_sync(self) -> List[Dict]:
        """Get list of accounts to sync for this job."""
        if not self.connection_id:
            raise ValueError("Connection ID required for import job")

        all_accounts = database.get_connection_accounts(self.connection_id)
        if not all_accounts:
            return []

        # Filter by account_ids if specified
        if self.account_ids:
            accounts = [
                a for a in all_accounts
                if a['account_id'] in self.account_ids
            ]
        else:
            accounts = all_accounts

        return accounts

    def get_status(self) -> Dict:
        """Get current job status."""
        job = database.get_import_job(self.job_id)
        progress = database.get_import_progress(self.job_id)

        completed_accounts = sum(1 for p in progress if p['progress_status'] == 'completed')
        total_accounts = len(progress)

        percent = round(100.0 * completed_accounts / total_accounts) if total_accounts > 0 else 0

        return {
            'job_id': self.job_id,
            'status': job['job_status'],
            'progress': {
                'completed_accounts': completed_accounts,
                'total_accounts': total_accounts,
                'percent': percent
            },
            'accounts': progress,
            'estimated_completion': job['estimated_completion'],
            'total_so_far': {
                'synced': job['total_transactions_synced'],
                'duplicates': job['total_transactions_duplicates'],
                'errors': job['total_transactions_errors']
            }
        }


def create_import_job(
    user_id: int,
    connection_id: int,
    from_date: str,
    to_date: str,
    account_ids: Optional[List[str]] = None,
    auto_enrich: bool = True,
    batch_size: int = 50
) -> ImportJob:
    """
    Create and return a new ImportJob.

    Args:
        user_id: User ID
        connection_id: Bank connection ID
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        account_ids: List of account IDs to sync
        auto_enrich: Whether to auto-enrich after import
        batch_size: Transactions per batch

    Returns:
        ImportJob instance
    """
    job_id = database.create_import_job(
        user_id=user_id,
        connection_id=connection_id,
        job_type='date_range',
        from_date=from_date,
        to_date=to_date,
        account_ids=account_ids,
        auto_enrich=auto_enrich,
        batch_size=batch_size
    )
    return ImportJob(job_id)
