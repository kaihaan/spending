"""Celery tasks for transaction enrichment."""

from mcp.llm_enricher import get_enricher
import database_postgres as db
from datetime import datetime
from celery_app import celery_app


@celery_app.task(bind=True, time_limit=900, soft_time_limit=800)
def enrich_transactions_task(self, transaction_ids=None, force_refresh=False, direction='out'):
    """
    Celery task to enrich transactions sequentially in batches.

    Args:
        transaction_ids: List of transaction IDs to enrich (None = all unenriched)
        force_refresh: Boolean to bypass cache
        direction: 'in' or 'out' for income/expense classification

    Returns:
        dict: Overall enrichment statistics
    """
    try:
        # Update task state to "STARTED"
        self.update_state(state='STARTED', meta={'status': 'initializing'})

        # Get enricher to calculate batch size
        enricher = get_enricher()
        if not enricher:
            raise Exception("LLM enricher not configured")

        # Get TrueLayer transactions to enrich
        if transaction_ids:
            transactions = []
            for tid in transaction_ids:
                t = db.get_truelayer_transaction_by_pk(tid)
                if t:
                    transactions.append(t)
            txn_ids_to_enrich = [t['id'] for t in transactions]
        else:
            transactions = db.get_unenriched_truelayer_transactions() or []
            txn_ids_to_enrich = [t['id'] for t in transactions]

        total = len(txn_ids_to_enrich)

        if total == 0:
            return {
                'status': 'completed',
                'stats': {
                    'total_transactions': 0,
                    'successful_enrichments': 0,
                    'failed_enrichments': 0,
                    'cached_hits': 0,
                    'api_calls_made': 0,
                    'total_tokens_used': 0,
                    'total_cost': 0.0
                },
                'completed_at': datetime.now().isoformat()
            }

        # Calculate batch size dynamically
        batch_size = enricher._calculate_batch_size(total)

        # Process batches sequentially (avoids Celery subtask anti-pattern)
        total_successful = 0
        total_failed = 0
        total_tokens = 0
        total_cost = 0.0
        total_api_calls = 0
        processed = 0

        num_batches = (total + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, len(txn_ids_to_enrich), batch_size)):
            batch_ids = txn_ids_to_enrich[i : i + batch_size]

            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': processed,
                    'total': total,
                    'status': 'enriching',
                    'completed_batches': batch_num,
                    'total_batches': num_batches,
                    'successful': total_successful,
                    'failed': total_failed,
                    'tokens_used': total_tokens,
                    'cost': total_cost
                }
            )

            try:
                # Enrich this batch directly
                stats = enricher.enrich_transactions(
                    transaction_ids=batch_ids,
                    direction=direction,
                    force_refresh=force_refresh
                )

                batch_successful = getattr(stats, 'successful_enrichments', 0)
                batch_failed = getattr(stats, 'failed_enrichments', 0)
                batch_tokens = getattr(stats, 'total_tokens_used', 0)
                batch_cost = getattr(stats, 'total_cost', 0.0)
                batch_api_calls = getattr(stats, 'api_calls_made', 0)

                total_successful += batch_successful
                total_failed += batch_failed
                total_tokens += batch_tokens
                total_cost += batch_cost
                total_api_calls += batch_api_calls

                # Note: enrichment_required flags are cleared inside
                # update_transaction_with_enrichment() for each successful save

            except Exception as e:
                # Log batch error but continue with other batches
                total_failed += len(batch_ids)
                print(f"Batch {batch_num} failed: {str(e)}")

            processed += len(batch_ids)

        return {
            'status': 'completed',
            'stats': {
                'total_transactions': total,
                'successful_enrichments': total_successful,
                'failed_enrichments': total_failed,
                'cached_hits': 0,
                'api_calls_made': total_api_calls,
                'total_tokens_used': total_tokens,
                'total_cost': total_cost,
                'batches_processed': num_batches
            },
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
