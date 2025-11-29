"""Celery tasks for transaction enrichment."""

from celery_app import celery_app
from mcp.llm_enricher import get_enricher
import database_postgres as db
from datetime import datetime


@celery_app.task(bind=True)
def enrich_transactions_task(self, transaction_ids=None, force_refresh=False):
    """
    Celery task to enrich TrueLayer transactions.

    Args:
        transaction_ids: List of transaction IDs to enrich (None = all unenriched)
        force_refresh: Boolean to bypass cache

    Returns:
        dict: Enrichment statistics and results
    """
    try:
        # Update task state to "STARTED"
        self.update_state(state='STARTED', meta={'status': 'initializing'})

        # Get enricher
        enricher = get_enricher()
        if not enricher:
            raise Exception("LLM enricher not configured")

        # Get TrueLayer transactions to enrich
        if transaction_ids:
            transactions = [db.get_truelayer_transaction_by_id(tid) for tid in transaction_ids if db.get_truelayer_transaction_by_id(tid)]
        else:
            transactions = db.get_unenriched_truelayer_transactions() or []

        total = len(transactions)

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

        # Update state with total count
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': total, 'status': 'enriching'}
        )

        # Run enrichment (only TrueLayer transactions are expenses)
        stats = enricher.enrich_transactions(
            transaction_ids=transaction_ids,
            direction='out',
            force_refresh=force_refresh
        )

        return {
            'status': 'completed',
            'stats': stats.__dict__ if hasattr(stats, '__dict__') else stats,
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
