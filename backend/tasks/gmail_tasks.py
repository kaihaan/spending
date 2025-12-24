"""Celery tasks for Gmail receipt processing."""

from datetime import datetime, timedelta
from celery_app import celery_app
import database_postgres as db


@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def sync_gmail_receipts_task(
    self,
    connection_id: int,
    sync_type: str = 'auto',
    job_id: int = None,
    from_date_str: str = None,
    to_date_str: str = None
):
    """
    Celery task to sync Gmail receipts in the background.

    Args:
        connection_id: Gmail connection ID
        sync_type: 'full' or 'incremental' or 'auto'
        job_id: Optional pre-created job ID for progress tracking
        from_date_str: ISO format start date (YYYY-MM-DD)
        to_date_str: ISO format end date (YYYY-MM-DD)

    Returns:
        dict: Sync statistics
    """
    try:
        from mcp.gmail_sync import sync_receipts_full, sync_receipts_incremental

        # Parse dates if provided
        from_date = datetime.fromisoformat(from_date_str) if from_date_str else None
        to_date = datetime.fromisoformat(to_date_str) if to_date_str else None

        self.update_state(state='STARTED', meta={
            'status': 'initializing',
            'connection_id': connection_id,
            'job_id': job_id,
            'from_date': from_date_str,
            'to_date': to_date_str,
        })

        # Get connection info
        connection = db.get_gmail_connection_by_id(connection_id)
        if not connection:
            return {
                'status': 'failed',
                'error': 'Connection not found'
            }

        # Determine sync type
        if sync_type == 'auto':
            # Use incremental if we have a history ID
            if connection.get('history_id'):
                sync_type = 'incremental'
            else:
                sync_type = 'full'

        results = {
            'total_messages': 0,
            'processed': 0,
            'parsed': 0,
            'failed': 0,
            'duplicates': 0,
        }

        if sync_type == 'incremental':
            self.update_state(state='PROGRESS', meta={
                'status': 'syncing',
                'sync_type': 'incremental',
                'connection_id': connection_id,
                'job_id': job_id,
            })

            result = sync_receipts_incremental(connection_id, job_id=job_id)

            if result.get('error'):
                return {
                    'status': 'failed',
                    'error': result['error']
                }

            results = {
                'total_messages': result.get('new_messages', 0),
                'processed': result.get('new_messages', 0),
                'parsed': result.get('parsed', 0),
                'failed': result.get('failed', 0),
                'duplicates': result.get('duplicates', 0),
            }
            job_id = result.get('job_id', job_id)
        else:
            # Full sync with progress tracking
            for progress in sync_receipts_full(connection_id, from_date=from_date, to_date=to_date, job_id=job_id):
                status = progress.get('status')

                if status == 'started':
                    job_id = progress.get('job_id', job_id)
                    self.update_state(state='PROGRESS', meta={
                        'status': 'started',
                        'sync_type': 'full',
                        'job_id': job_id,
                        'from_date': progress.get('from_date'),
                        'to_date': progress.get('to_date'),
                        'connection_id': connection_id,
                    })

                elif status == 'scanning':
                    self.update_state(state='PROGRESS', meta={
                        'status': 'scanning',
                        'sync_type': 'full',
                        'job_id': job_id,
                        'total_messages': progress.get('total_messages', 0),
                        'processed': 0,
                        'connection_id': connection_id,
                    })

                elif status == 'processing':
                    self.update_state(state='PROGRESS', meta={
                        'status': 'processing',
                        'sync_type': 'full',
                        'job_id': job_id,
                        'total_messages': progress.get('total_messages', 0),
                        'processed': progress.get('processed', 0),
                        'parsed': progress.get('parsed', 0),
                        'failed': progress.get('failed', 0),
                        'duplicates': progress.get('duplicates', 0),
                        'connection_id': connection_id,
                    })

                elif status == 'completed':
                    results = {
                        'total_messages': progress.get('total_messages', 0),
                        'processed': progress.get('processed', 0),
                        'parsed': progress.get('parsed', 0),
                        'failed': progress.get('failed', 0),
                        'duplicates': progress.get('duplicates', 0),
                    }
                    job_id = progress.get('job_id', job_id)

        return {
            'status': 'completed',
            'sync_type': sync_type,
            'job_id': job_id,
            'stats': results,
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'job_id': job_id,
        }


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def parse_gmail_receipts_task(self, connection_id: int, limit: int = 100):
    """
    DEPRECATED: Parsing now happens during sync (parse-on-sync workflow).

    This task is kept for backwards compatibility but will return immediately
    since there are no longer any 'pending' receipts to parse.

    Args:
        connection_id: Gmail connection ID
        limit: Maximum receipts to parse

    Returns:
        dict: Parse statistics (will show 0 parsed since parse-on-sync is active)
    """
    return {
        'status': 'completed',
        'stats': {
            'total': 0,
            'parsed': 0,
            'failed': 0,
            'skipped': 0,
        },
        'message': 'Parsing now happens during sync - no separate parse step needed',
        'completed_at': datetime.now().isoformat()
    }


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def match_gmail_receipts_task(self, user_id: int = 1):
    """
    Celery task to match Gmail receipts to transactions.

    Args:
        user_id: User ID to match receipts for

    Returns:
        dict: Matching statistics
    """
    try:
        from mcp.gmail_matcher import match_all_gmail_receipts

        self.update_state(state='STARTED', meta={
            'status': 'initializing',
            'user_id': user_id
        })

        results = match_all_gmail_receipts(user_id)

        return {
            'status': 'completed',
            'stats': {
                'total_receipts': results.get('total_receipts', 0),
                'matched': results.get('matched', 0),
                'unmatched': results.get('unmatched', 0),
                'auto_matched': results.get('auto_matched', 0),
                'needs_confirmation': results.get('needs_confirmation', 0),
            },
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


@celery_app.task(bind=True, time_limit=300, soft_time_limit=280)
def cleanup_old_gmail_receipts_task(self, days: int = 90):
    """
    Celery task to clean up old Gmail receipts beyond retention period.

    Only deletes receipts that:
    - Are older than the specified days
    - Are NOT matched to a transaction
    - Have parsing_status of 'unparseable'

    Args:
        days: Number of days to retain (default 90)

    Returns:
        dict: Cleanup statistics
    """
    try:
        self.update_state(state='STARTED', meta={
            'status': 'cleaning',
            'retention_days': days
        })

        cutoff_date = datetime.now() - timedelta(days=days)

        # Delete old unparseable receipts that aren't matched
        deleted = db.delete_old_unmatched_gmail_receipts(cutoff_date)

        return {
            'status': 'completed',
            'stats': {
                'deleted_count': deleted,
                'cutoff_date': cutoff_date.isoformat(),
                'retention_days': days,
            },
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


@celery_app.task(bind=True, time_limit=900, soft_time_limit=850)
def full_gmail_pipeline_task(self, connection_id: int, user_id: int = 1):
    """
    Celery task to run the full Gmail processing pipeline:
    1. Sync receipts from Gmail (parsing happens inline during sync)
    2. Match receipts to transactions

    Note: Parsing is now done inline during sync (parse-on-sync workflow),
    so there's no separate parse step.

    Args:
        connection_id: Gmail connection ID
        user_id: User ID for matching

    Returns:
        dict: Combined statistics from all steps
    """
    try:
        from mcp.gmail_sync import sync_receipts_full, sync_receipts_incremental
        from mcp.gmail_matcher import match_all_gmail_receipts

        pipeline_results = {
            'sync': {},
            'match': {},
        }

        # Step 1: Sync (parsing happens inline)
        self.update_state(state='PROGRESS', meta={
            'status': 'syncing',
            'step': 1,
            'total_steps': 2
        })

        connection = db.get_gmail_connection_by_id(connection_id)
        if not connection:
            return {
                'status': 'failed',
                'error': 'Connection not found'
            }

        if connection.get('history_id'):
            sync_result = sync_receipts_incremental(connection_id)
            pipeline_results['sync'] = {
                'type': 'incremental',
                'messages_found': sync_result.get('new_messages', 0),
                'stored': sync_result.get('parsed', 0),
                'filtered': sync_result.get('filtered', 0),
                'duplicates': sync_result.get('duplicates', 0),
            }
        else:
            sync_results = {'total': 0, 'stored': 0}
            for progress in sync_receipts_full(connection_id):
                if progress.get('status') == 'completed':
                    sync_results = {
                        'total': progress.get('total_messages', 0),
                        'stored': progress.get('parsed', 0),
                        'filtered': progress.get('filtered', 0),
                        'duplicates': progress.get('duplicates', 0),
                    }
            pipeline_results['sync'] = {
                'type': 'full',
                'messages_found': sync_results['total'],
                'stored': sync_results.get('stored', 0),
                'filtered': sync_results.get('filtered', 0),
                'duplicates': sync_results.get('duplicates', 0),
            }

        # Step 2: Match
        self.update_state(state='PROGRESS', meta={
            'status': 'matching',
            'step': 2,
            'total_steps': 2
        })

        match_result = match_all_gmail_receipts(user_id)
        pipeline_results['match'] = {
            'total': match_result.get('total_receipts', 0),
            'matched': match_result.get('matched', 0),
            'unmatched': match_result.get('unmatched', 0),
        }

        return {
            'status': 'completed',
            'pipeline': pipeline_results,
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
