"""
Enrichment Service - Business Logic

Orchestrates LLM-based transaction enrichment including:
- Configuration management for multiple LLM providers
- Cost estimation and job triggering
- Progress tracking via Celery tasks
- Enrichment cache management
- Model selection and validation

Supports: Anthropic (Claude), OpenAI, Google (Gemini), DeepSeek, Ollama (local)

Separates business logic from HTTP routing concerns.
"""

from database import enrichment, truelayer
from config.llm_config import (
    load_llm_config,
    get_provider_info,
    LLMProvider
)
from mcp.llm_enricher import LLMEnricher
import cache_manager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

def get_config() -> dict:
    """
    Get LLM enrichment configuration.

    Returns:
        Configuration dict with provider details or not configured status
    """
    try:
        llm_cfg = load_llm_config()
    except Exception:
        llm_cfg = None

    if llm_cfg:
        return {
            'configured': True,
            'config': {
                'provider': llm_cfg.provider.value,
                'model': llm_cfg.model,
                'cache_enabled': llm_cfg.cache_enabled,
                'batch_size': llm_cfg.batch_size_override or llm_cfg.batch_size_initial
            }
        }
    else:
        return {
            'configured': False,
            'message': 'LLM enrichment is not configured. Set the LLM_PROVIDER and LLM_API_KEY environment variables to enable this feature.'
        }


def get_account_info() -> dict:
    """
    Get LLM provider account information (balance, tier, usage).

    Returns:
        Account details dict or error status

    Raises:
        ValueError: If LLM not configured
    """
    llm_cfg = load_llm_config()
    if not llm_cfg:
        return {
            'configured': False,
            'error': 'LLM enrichment not configured'
        }

    try:
        enricher = LLMEnricher()
        account_info = enricher.provider.get_account_info()

        return {
            'configured': True,
            'provider': llm_cfg.provider.value,
            'account': {
                'available': account_info.available,
                'balance': account_info.balance,
                'subscription_tier': account_info.subscription_tier,
                'usage_this_month': account_info.usage_this_month,
                'error': account_info.error,
                'extra': account_info.extra
            }
        }
    except Exception as e:
        return {
            'configured': True,
            'provider': llm_cfg.provider.value,
            'account': {
                'available': False,
                'error': f'Failed to get account info: {str(e)}'
            }
        }


def validate_config() -> dict:
    """
    Validate LLM enrichment configuration.

    Returns:
        Validation status dict
    """
    try:
        llm_cfg = load_llm_config()
    except Exception as e:
        return {
            'valid': False,
            'message': str(e)
        }

    if not llm_cfg:
        return {
            'valid': False,
            'message': 'LLM enrichment is not configured'
        }

    return {
        'valid': True,
        'message': f'LLM enrichment configured with {llm_cfg.provider.value} ({llm_cfg.model})'
    }


def get_available_models() -> dict:
    """
    Get list of available models for all LLM providers.

    Returns:
        Dict with current provider and all available models
    """
    # Check current configuration
    try:
        llm_cfg = load_llm_config()
    except Exception:
        llm_cfg = None

    current_provider = llm_cfg.provider.value if llm_cfg else None

    # Build response with all providers and their models
    all_models_response = {
        'current_provider': current_provider,
        'all_models': {}
    }

    # Get models for each provider
    for provider in LLMProvider:
        provider_info = get_provider_info(provider)
        supported_models = provider_info.get('supported_models', [])

        # Build model list for this provider
        model_list = []
        for model in supported_models:
            model_list.append({
                'name': model,
                'selected': llm_cfg and llm_cfg.model == model
            })

        # Initialize provider models structure
        all_models_response['all_models'][provider.value] = {
            'provider': provider.value,
            'selected': llm_cfg.model if llm_cfg and llm_cfg.provider == provider else None,
            'built_in': model_list,
            'custom': []  # No custom models support yet
        }

    return all_models_response


# ============================================================================
# Statistics & Cache
# ============================================================================

def get_cache_stats() -> dict:
    """
    Get enrichment cache statistics.

    Returns:
        Cache statistics dict
    """
    stats = cache_manager.get_cache_stats()

    return {
        'total_cached': stats.get('total_keys', 0),
        'providers': {},
        'pending_retries': 0,
        'cache_size_bytes': stats.get('used_memory', 'N/A')
    }


def get_stats() -> dict:
    """
    Get overall enrichment statistics for TrueLayer transactions.

    Returns:
        Enrichment statistics dict
    """
    # Count total and enriched transactions
    all_transactions = truelayer.get_all_truelayer_transactions() or []
    total_transactions = len(all_transactions)

    enriched_count = truelayer.count_enriched_truelayer_transactions()
    unenriched_count = total_transactions - enriched_count

    # Cache stats
    cache_stats = cache_manager.get_cache_stats()

    return {
        'total_transactions': total_transactions,
        'enriched_count': enriched_count,
        'unenriched_count': unenriched_count,
        'enrichment_percentage': round(
            (enriched_count / max(total_transactions, 1) * 100),
            1
        ),
        'cache_stats': {
            'total_cached': cache_stats.get('total_keys', 0)
        }
    }


def get_failed_enrichments(limit: int = 20) -> dict:
    """
    Get failed enrichment records.

    Args:
        limit: Max failed records to return

    Returns:
        Failed enrichments list
    """
    # Return empty list for now - enrichment failures would be logged elsewhere
    return {
        'failed_enrichments': []
    }


# ============================================================================
# Cost Estimation
# ============================================================================

def estimate_cost(transaction_ids: list = None, force_refresh: bool = False) -> dict:
    """
    Estimate cost for enriching TrueLayer transactions.

    Args:
        transaction_ids: Specific transaction IDs to estimate (optional)
        force_refresh: Whether to force API calls even if cached

    Returns:
        Cost estimation dict

    Raises:
        ValueError: If LLM not configured
    """
    # Check if LLM configured
    llm_cfg = load_llm_config()
    if not llm_cfg:
        raise ValueError('LLM enrichment not configured')

    # Get transactions to estimate
    if transaction_ids:
        transactions = [
            truelayer.get_truelayer_transaction_by_id(tid)
            for tid in transaction_ids
            if truelayer.get_truelayer_transaction_by_id(tid)
        ]
    else:
        transactions = truelayer.get_unenriched_truelayer_transactions() or []

    # Count cached vs API calls needed
    cached_count = 0
    requires_api = []

    for txn in transactions:
        if not txn:
            continue
        direction = 'out' if txn.get('amount', 0) < 0 else 'in'
        cached = enrichment.get_enrichment_from_cache(txn.get('description', ''), direction)
        if cached:
            cached_count += 1
        else:
            requires_api.append(txn)

    # Calculate cost (assume 150 input + 50 output tokens per transaction)
    cost_info = get_provider_info(llm_cfg.provider)

    estimated_tokens = len(requires_api) * 200
    estimated_cost = (
        (len(requires_api) * 150 / 1000 * cost_info.get('cost_per_1k_input_tokens', 0)) +
        (len(requires_api) * 50 / 1000 * cost_info.get('cost_per_1k_output_tokens', 0))
    )

    return {
        'total_transactions': len(transactions),
        'cached_available': cached_count,
        'requires_api_call': len(requires_api),
        'estimated_tokens': estimated_tokens,
        'estimated_cost': round(estimated_cost, 6),
        'currency': 'USD',
        'provider': llm_cfg.provider.value,
        'model': llm_cfg.model
    }


# ============================================================================
# Enrichment Jobs
# ============================================================================

def trigger_enrichment(transaction_ids: list = None, force_refresh: bool = False,
                       confirm_cost: bool = False) -> dict:
    """
    Start enrichment job (requires cost confirmation).

    Args:
        transaction_ids: Specific transaction IDs to enrich (optional)
        force_refresh: Whether to force re-enrichment
        confirm_cost: User confirmation of costs (required)

    Returns:
        Job details with job_id and status

    Raises:
        ValueError: If cost not confirmed or LLM not configured
    """
    # Require cost confirmation
    if not confirm_cost:
        raise ValueError('Cost confirmation required. Set confirm_cost=true to proceed.')

    # Check LLM configured
    if not load_llm_config():
        raise ValueError('LLM enrichment not configured')

    # Start Celery task
    from tasks.enrichment_tasks import enrich_transactions_task

    task = enrich_transactions_task.apply_async(
        args=[transaction_ids, force_refresh]
    )

    # Invalidate transaction caches (enrichment will update transactions)
    cache_manager.cache_invalidate_transactions()

    return {
        'job_id': task.id,
        'status': 'running',
        'message': 'Enrichment job started',
        'started_at': datetime.now().isoformat()
    }


def get_job_status(job_id: str) -> dict:
    """
    Get enrichment job status by Celery task ID.

    Args:
        job_id: Celery task ID

    Returns:
        Job status dict with progress or result
    """
    from celery.result import AsyncResult
    from celery_app import celery_app

    task = AsyncResult(job_id, app=celery_app)

    if task.state == 'PENDING':
        return {
            'job_id': job_id,
            'status': 'pending',
            'message': 'Job not found or not started',
            '_http_status': 404
        }

    elif task.state == 'PROGRESS':
        return {
            'job_id': job_id,
            'status': 'running',
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 0),
            'progress_percentage': round(
                (task.info.get('current', 0) / max(task.info.get('total', 1), 1)) * 100, 1
            )
        }

    elif task.state == 'SUCCESS':
        result = task.result
        if isinstance(result, dict) and 'stats' in result:
            return {
                'job_id': job_id,
                'status': 'completed',
                **result.get('stats', {})
            }
        return result

    elif task.state == 'FAILURE':
        return {
            'job_id': job_id,
            'status': 'failed',
            'error': str(task.info)
        }

    else:
        return {
            'job_id': job_id,
            'status': task.state.lower()
        }


def retry_failed(transaction_ids: list = None) -> dict:
    """
    Retry failed enrichments.

    Args:
        transaction_ids: Specific transaction IDs to retry (optional)

    Returns:
        Job details with job_id and status
    """
    # Get failed transaction IDs if not specified
    if not transaction_ids:
        transaction_ids = enrichment.get_failed_enrichment_transaction_ids()

    # Start retry task
    from tasks.enrichment_tasks import enrich_transactions_task

    task = enrich_transactions_task.apply_async(
        args=[transaction_ids, True]  # force_refresh=True
    )

    return {
        'job_id': task.id,
        'status': 'running',
        'total_transactions': len(transaction_ids),
        'message': 'Retry job started'
    }


# ============================================================================
# Streaming Enrichment
# ============================================================================

def prepare_stream_enrichment(transaction_ids: list = None, mode: str = 'required',
                               limit: int = None, direction: str = 'out',
                               force_refresh: bool = False) -> tuple:
    """
    Prepare enrichment stream job and return task ID and transaction count.

    Args:
        transaction_ids: Specific transaction IDs (optional)
        mode: Selection mode ('required', 'limit', 'all', 'unenriched')
        limit: Max transactions to process
        direction: Transaction direction ('out', 'in', 'both')
        force_refresh: Whether to force re-enrichment

    Returns:
        Tuple of (task_id, transaction_ids_list)

    Raises:
        ValueError: If LLM not configured
    """
    # Check LLM configured
    if not load_llm_config():
        raise ValueError('LLM enrichment not configured')

    # If specific transaction IDs aren't provided, query based on mode
    if not transaction_ids:
        try:
            # For 'required' mode, use optimized query
            if mode == 'required':
                all_transactions = enrichment.get_required_unenriched_transactions(limit=limit) or []
                # Filter by direction if needed
                if direction == 'out':
                    all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'DEBIT']
                elif direction == 'in':
                    all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'CREDIT']
            else:
                all_transactions = truelayer.get_all_truelayer_transactions() or []

                # Filter by direction
                if direction == 'out':
                    all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'DEBIT']
                elif direction == 'in':
                    all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'CREDIT']

                # Filter by enrichment status and limit
                if mode == 'unenriched':
                    all_transactions = [t for t in all_transactions if not t.get('is_enriched')]
                elif mode == 'limit' and limit:
                    all_transactions = all_transactions[:limit]

        except Exception as e:
            logger.error(f"Error fetching transactions: {str(e)}")
            raise

        transaction_ids = [t.get('id') for t in all_transactions if t.get('id')]

    # Start Celery task
    from tasks.enrichment_tasks import enrich_transactions_task

    task = enrich_transactions_task.apply_async(
        args=[transaction_ids, force_refresh]
    )

    return task.id, transaction_ids


# ============================================================================
# Enrichment Sources
# ============================================================================

def get_source_details(source_id: int) -> dict:
    """
    Fetch full details from the source table for an enrichment source.

    Returns enrichment source metadata plus complete data from the
    appropriate source table based on source_type.

    Args:
        source_id: Enrichment source ID

    Returns:
        Source details dict with full data
    """
    return enrichment.get_enrichment_source_details(source_id)
