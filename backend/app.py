from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import database_postgres as database
import cache_manager
import re
import os
import json
import threading
import logging
from datetime import datetime
from config import llm_config
from mcp.merchant_normalizer import detect_account_pattern
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Allow larger request bodies for CSV file uploads (16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Get frontend URL from environment, default to localhost:5173
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

# Global enrichment progress tracking
enrichment_progress = {}
enrichment_lock = threading.Lock()


@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Backend is running'})


@app.route('/api/cache/stats')
def get_cache_stats():
    """Get Redis cache statistics."""
    try:
        stats = cache_manager.get_cache_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def normalize_transaction(txn):
    """Normalize transaction field names to match frontend expectations.

    Converts:
    - timestamp → date
    - transaction_category → category
    - merchant_name → merchant
    - Ensures transaction_type is included for accounting model
    """
    normalized = {**txn}  # Create a copy

    # Map TrueLayer field names to expected frontend field names
    if 'timestamp' in normalized and 'date' not in normalized:
        normalized['date'] = normalized.pop('timestamp')

    if 'transaction_category' in normalized and 'category' not in normalized:
        normalized['category'] = normalized.pop('transaction_category')

    if 'merchant_name' in normalized and 'merchant' not in normalized:
        normalized['merchant'] = normalized.pop('merchant_name')

    # Ensure category defaults to 'Other' if missing
    if 'category' not in normalized or not normalized['category']:
        normalized['category'] = 'Other'

    # Ensure transaction_type is present (DEBIT or CREDIT)
    if 'transaction_type' not in normalized or not normalized['transaction_type']:
        # Fallback for legacy transactions: infer from amount sign if available
        if 'amount' in normalized:
            normalized['transaction_type'] = 'DEBIT' if normalized['amount'] < 0 else 'CREDIT'
        else:
            normalized['transaction_type'] = 'DEBIT'

    return normalized


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get all TrueLayer transactions with enrichment data (OPTIMIZED - single query + Redis cache)."""
    try:
        # Check cache first
        cache_key = "transactions:all"
        cached_data = cache_manager.cache_get(cache_key)
        if cached_data is not None:
            return jsonify(cached_data)

        # Cache miss - fetch from database
        # Use optimized single-query function (eliminates N+1 problem)
        all_transactions = database.get_all_truelayer_transactions_with_enrichment() or []

        # Batch-fetch enrichment sources for all transactions
        transaction_ids = [t.get('id') for t in all_transactions if t.get('id')]
        enrichment_sources_map = {}
        if transaction_ids:
            # Returns dict: {txn_id: [sources_list]}
            enrichment_sources_map = database.get_all_enrichment_sources_for_transactions(transaction_ids)

        # Normalize and build response
        normalized = []
        for t in all_transactions:
            # Normalize field names for frontend consistency
            transaction = normalize_transaction(t)

            # Build enrichment dict from prefixed columns (already extracted in SQL)
            has_enrichment = bool(t.get('enrichment_primary_category'))

            if has_enrichment:
                enrichment_obj = {
                    'is_enriched': True,
                    'primary_category': t.get('enrichment_primary_category'),
                    'subcategory': t.get('enrichment_subcategory'),
                    'merchant_clean_name': t.get('enrichment_merchant_clean_name'),
                    'merchant_type': t.get('enrichment_merchant_type'),
                    'essential_discretionary': t.get('enrichment_essential_discretionary'),
                    'payment_method': t.get('enrichment_payment_method'),
                    'payment_method_subtype': t.get('enrichment_payment_method_subtype'),
                    'confidence_score': float(t.get('enrichment_confidence_score', 0)) if t.get('enrichment_confidence_score') else None,
                    'enriched_at': t.get('enrichment_enriched_at').isoformat() if t.get('enrichment_enriched_at') else None,
                    'enrichment_source': t.get('enrichment_llm_provider', 'llm'),
                    'llm_provider': t.get('enrichment_llm_provider'),
                    'llm_model': t.get('enrichment_llm_model')
                }
                transaction['enrichment'] = enrichment_obj

                # Flatten key enrichment fields to top level
                transaction['subcategory'] = t.get('enrichment_subcategory')
                transaction['merchant_clean_name'] = t.get('enrichment_merchant_clean_name')
                transaction['essential_discretionary'] = t.get('enrichment_essential_discretionary')
                transaction['confidence_score'] = float(t.get('enrichment_confidence_score', 0)) if t.get('enrichment_confidence_score') else None
                transaction['enrichment_source'] = t.get('enrichment_llm_provider', 'llm')
                transaction['payment_method'] = t.get('enrichment_payment_method')
                transaction['payment_method_subtype'] = t.get('enrichment_payment_method_subtype')
            else:
                # Transaction not enriched
                transaction['enrichment'] = {'is_enriched': False}
                transaction['subcategory'] = None
                transaction['merchant_clean_name'] = None
                transaction['essential_discretionary'] = None
                transaction['confidence_score'] = None
                transaction['enrichment_source'] = None
                transaction['payment_method'] = None
                transaction['payment_method_subtype'] = None

            # Include enrichment_required flag for UI toggle
            transaction['enrichment_required'] = t.get('enrichment_required', True)

            # Compute huququllah_classification: manual override or LLM classification
            manual_classification = t.get('manual_huququllah_classification')
            llm_classification = t.get('enrichment_essential_discretionary', '').lower() if t.get('enrichment_essential_discretionary') else None

            # Use manual if set, otherwise fall back to LLM
            transaction['huququllah_classification'] = manual_classification or llm_classification

            # Add enrichment sources from multi-source table
            txn_id = t.get('id')
            sources = enrichment_sources_map.get(txn_id, [])
            # Format sources for frontend
            transaction['enrichment_sources'] = [
                {
                    'id': s.get('id'),  # Enrichment source ID for fetching full details
                    'source_type': s.get('source_type'),
                    'source_id': s.get('source_id'),
                    'description': s.get('description'),
                    'order_id': s.get('order_id'),
                    'confidence': s.get('match_confidence'),
                    'match_method': s.get('match_method'),
                    'is_primary': s.get('is_primary', False),
                    'user_verified': s.get('user_verified', False),
                    'line_items': s.get('line_items')
                }
                for s in sources
            ]

            normalized.append(transaction)

        # Sort by date descending (most recent first)
        normalized.sort(key=lambda t: str(t.get('date', '')), reverse=True)

        # Cache the result (15 minute TTL)
        cache_manager.cache_set(cache_key, normalized, ttl=900)

        return jsonify(normalized)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get all categories."""
    try:
        categories = database.get_all_categories()
        return jsonify(categories)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/<int:transaction_id>/toggle-required', methods=['POST'])
def toggle_transaction_required(transaction_id):
    """Toggle enrichment_required flag for a transaction.

    Returns the new state including enrichment_source for UI update.
    """
    try:
        result = database.toggle_enrichment_required(transaction_id)
        if result:
            # Invalidate transactions cache
            cache_manager.cache_delete("transactions:all")
            return jsonify(result)
        return jsonify({'error': 'Transaction not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Category Promotion Endpoints
# ============================================================================

@app.route('/api/categories/summary', methods=['GET'])
def get_category_spending_summary():
    """Get all categories with spending totals."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        categories = database.get_category_spending_summary(date_from, date_to)
        hidden_categories = database.get_custom_categories(category_type='hidden')

        return jsonify({
            'categories': categories,
            'hidden_categories': [{'name': c['name'], 'id': c['id']} for c in hidden_categories]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories/<path:category_name>/subcategories', methods=['GET'])
def get_category_subcategories(category_name):
    """Get subcategories for a specific category with spending totals."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        subcategories = database.get_subcategory_spending(category_name, date_from, date_to)

        return jsonify({
            'category': category_name,
            'subcategories': subcategories
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories/promote', methods=['POST'])
def promote_category():
    """Create a promoted category from selected subcategories."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        new_category_name = data.get('new_category_name')
        subcategories = data.get('subcategories', [])

        if not new_category_name:
            return jsonify({'error': 'new_category_name is required'}), 400
        if not subcategories:
            return jsonify({'error': 'At least one subcategory is required'}), 400

        result = database.create_promoted_category(new_category_name, subcategories)

        return jsonify({
            'success': True,
            'category_id': result['category_id'],
            'transactions_updated': result['transactions_updated'],
            'message': f"Created category '{new_category_name}' and updated {result['transactions_updated']} transactions"
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories/hide', methods=['POST'])
def hide_category():
    """Hide a category and reset its transactions for re-enrichment."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        category_name = data.get('category_name')
        if not category_name:
            return jsonify({'error': 'category_name is required'}), 400

        result = database.hide_category(category_name)

        return jsonify({
            'success': True,
            'category_id': result['category_id'],
            'transactions_reset': result['transactions_reset'],
            'message': f"Hidden category '{category_name}' and reset {result['transactions_reset']} transactions for re-enrichment"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories/unhide', methods=['POST'])
def unhide_category():
    """Restore a hidden category."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        category_name = data.get('category_name')
        if not category_name:
            return jsonify({'error': 'category_name is required'}), 400

        success = database.unhide_category(category_name)

        if success:
            return jsonify({
                'success': True,
                'message': f"Category '{category_name}' has been restored"
            })
        else:
            return jsonify({
                'success': False,
                'message': f"Category '{category_name}' was not found in hidden list"
            }), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/categories/custom', methods=['GET'])
def get_custom_categories():
    """Get all custom categories (promoted and hidden)."""
    try:
        category_type = request.args.get('type')  # 'promoted', 'hidden', or None for all

        categories = database.get_custom_categories(category_type=category_type)

        return jsonify({
            'categories': [dict(c) for c in categories]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Normalized Categories API (v2) - Full CRUD with FK relationships
# ============================================================================

@app.route('/api/v2/categories', methods=['GET'])
def get_normalized_categories_api():
    """Get all normalized categories with optional counts."""
    try:
        active_only = request.args.get('active_only', 'false').lower() == 'true'
        include_counts = request.args.get('include_counts', 'true').lower() == 'true'

        categories = database.get_normalized_categories(
            active_only=active_only,
            include_counts=include_counts
        )

        return jsonify({
            'categories': [dict(c) for c in categories]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/categories/<int:category_id>', methods=['GET'])
def get_normalized_category_api(category_id):
    """Get a single normalized category with subcategories."""
    try:
        category = database.get_normalized_category_by_id(category_id)

        if not category:
            return jsonify({'error': 'Category not found'}), 404

        return jsonify({
            'category': dict(category)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/categories', methods=['POST'])
def create_normalized_category_api():
    """Create a new normalized category."""
    try:
        data = request.get_json()

        if not data or not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400

        category = database.create_normalized_category(
            name=data['name'],
            description=data.get('description'),
            is_essential=data.get('is_essential', False),
            color=data.get('color')
        )

        if not category:
            return jsonify({'error': 'Category with this name already exists'}), 409

        return jsonify({
            'category': dict(category),
            'message': 'Category created successfully'
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/categories/<int:category_id>', methods=['PUT'])
def update_normalized_category_api(category_id):
    """Update a normalized category. Cascades name changes to all transactions."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = database.update_normalized_category(
            category_id=category_id,
            name=data.get('name'),
            description=data.get('description'),
            is_active=data.get('is_active'),
            is_essential=data.get('is_essential'),
            color=data.get('color')
        )

        if not result:
            return jsonify({'error': 'Category not found'}), 404

        return jsonify({
            'category': dict(result['category']),
            'transactions_updated': result['transactions_updated'],
            'rules_updated': result['rules_updated'],
            'old_name': result.get('old_name'),
            'new_name': result.get('new_name'),
            'message': 'Category updated successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/categories/<int:category_id>', methods=['DELETE'])
def delete_normalized_category_api(category_id):
    """Delete a normalized category. System categories cannot be deleted."""
    try:
        reassign_to = request.args.get('reassign_to', type=int)

        result = database.delete_normalized_category(
            category_id=category_id,
            reassign_to_category_id=reassign_to
        )

        if not result:
            return jsonify({'error': 'Category not found'}), 404

        if result.get('error'):
            return jsonify({'error': result['error']}), 400

        return jsonify({
            'deleted_category': result['deleted_category'],
            'transactions_reassigned': result['transactions_reassigned'],
            'message': 'Category deleted successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Normalized Subcategories API (v2)
# ============================================================================

@app.route('/api/v2/subcategories', methods=['GET'])
def get_normalized_subcategories_api():
    """Get all normalized subcategories, optionally filtered by category."""
    try:
        category_id = request.args.get('category_id', type=int)
        include_counts = request.args.get('include_counts', 'true').lower() == 'true'

        subcategories = database.get_normalized_subcategories(
            category_id=category_id,
            include_counts=include_counts
        )

        return jsonify({
            'subcategories': [dict(s) for s in subcategories]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/subcategories/<int:subcategory_id>', methods=['GET'])
def get_normalized_subcategory_api(subcategory_id):
    """Get a single normalized subcategory."""
    try:
        subcategory = database.get_normalized_subcategory_by_id(subcategory_id)

        if not subcategory:
            return jsonify({'error': 'Subcategory not found'}), 404

        return jsonify({
            'subcategory': dict(subcategory)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/categories/<int:category_id>/subcategories', methods=['POST'])
def create_normalized_subcategory_api(category_id):
    """Create a new normalized subcategory under a category."""
    try:
        data = request.get_json()

        if not data or not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400

        # Verify category exists
        category = database.get_normalized_category_by_id(category_id)
        if not category:
            return jsonify({'error': 'Category not found'}), 404

        subcategory = database.create_normalized_subcategory(
            category_id=category_id,
            name=data['name'],
            description=data.get('description')
        )

        if not subcategory:
            return jsonify({'error': 'Subcategory with this name already exists in this category'}), 409

        return jsonify({
            'subcategory': dict(subcategory),
            'message': 'Subcategory created successfully'
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/subcategories/<int:subcategory_id>', methods=['PUT'])
def update_normalized_subcategory_api(subcategory_id):
    """Update a normalized subcategory. Cascades name changes to transactions."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = database.update_normalized_subcategory(
            subcategory_id=subcategory_id,
            name=data.get('name'),
            description=data.get('description'),
            is_active=data.get('is_active'),
            category_id=data.get('category_id')  # For moving to different category
        )

        if not result:
            return jsonify({'error': 'Subcategory not found'}), 404

        return jsonify({
            'subcategory': dict(result['subcategory']),
            'transactions_updated': result['transactions_updated'],
            'old_name': result.get('old_name'),
            'new_name': result.get('new_name'),
            'message': 'Subcategory updated successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v2/subcategories/<int:subcategory_id>', methods=['DELETE'])
def delete_normalized_subcategory_api(subcategory_id):
    """Delete a normalized subcategory."""
    try:
        result = database.delete_normalized_subcategory(subcategory_id)

        if not result:
            return jsonify({'error': 'Subcategory not found'}), 404

        return jsonify({
            'deleted_subcategory': result['deleted_subcategory'],
            'category_name': result['category_name'],
            'transactions_cleared': result['transactions_cleared'],
            'message': 'Subcategory deleted successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/config', methods=['GET'])
def get_enrichment_config():
    """Get enrichment configuration."""
    try:
        # Try to load LLM config from environment variables
        from config.llm_config import load_llm_config

        llm_cfg = None
        try:
            llm_cfg = load_llm_config()
        except Exception as e:
            pass

        if llm_cfg:
            return jsonify({
                'configured': True,
                'config': {
                    'provider': llm_cfg.provider.value,
                    'model': llm_cfg.model,
                    'cache_enabled': llm_cfg.cache_enabled,
                    'batch_size': llm_cfg.batch_size_override or llm_cfg.batch_size_initial
                }
            }), 200
        else:
            return jsonify({
                'configured': False,
                'message': 'LLM enrichment is not configured. Set the LLM_PROVIDER and LLM_API_KEY environment variables to enable this feature.'
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/account-info', methods=['GET'])
def get_enrichment_account_info():
    """Get LLM provider account information (balance, tier)."""
    try:
        from config.llm_config import load_llm_config
        from mcp.llm_enricher import LLMEnricher

        llm_cfg = load_llm_config()
        if not llm_cfg:
            return jsonify({
                'configured': False,
                'error': 'LLM enrichment not configured'
            }), 200

        # Create enricher to get provider instance
        try:
            enricher = LLMEnricher()
            account_info = enricher.provider.get_account_info()

            return jsonify({
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
            }), 200

        except Exception as e:
            return jsonify({
                'configured': True,
                'provider': llm_cfg.provider.value,
                'account': {
                    'available': False,
                    'error': f'Failed to get account info: {str(e)}'
                }
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/cache/stats', methods=['GET'])
def get_enrichment_cache_stats():
    """Get enrichment cache statistics."""
    try:
        # Query the llm_enrichment_cache table for statistics
        from database_postgres import get_db
        from psycopg2.extras import RealDictCursor

        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get total cached entries
                cursor.execute('SELECT COUNT(*) as total FROM llm_enrichment_cache')
                total = cursor.fetchone()['total']

                # Get cache size in bytes (approximate)
                cursor.execute('''
                    SELECT COALESCE(SUM(LENGTH(enrichment_data::text)), 0) as size_bytes
                    FROM llm_enrichment_cache
                ''')
                size_bytes = cursor.fetchone()['size_bytes']

                return jsonify({
                    'total_cached': total,
                    'providers': {},
                    'pending_retries': 0,
                    'cache_size_bytes': size_bytes
                }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/failed', methods=['GET'])
def get_failed_enrichments():
    """Get failed enrichment records."""
    try:
        limit = request.args.get('limit', 20, type=int)

        # Return empty list for now - enrichment failures would be logged elsewhere
        return jsonify({
            'failed_enrichments': []
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/estimate', methods=['POST'])
def estimate_enrichment_cost():
    """Estimate cost for enriching unenriched TrueLayer transactions."""
    try:
        data = request.get_json() or {}
        transaction_ids = data.get('transaction_ids')
        force_refresh = data.get('force_refresh', False)

        # Check if LLM configured
        from config.llm_config import load_llm_config
        llm_cfg = load_llm_config()
        if not llm_cfg:
            return jsonify({
                'configured': False,
                'error': 'LLM enrichment not configured'
            }), 503

        # Get transactions to estimate
        if transaction_ids:
            transactions = [database.get_truelayer_transaction_by_id(tid) for tid in transaction_ids if database.get_truelayer_transaction_by_id(tid)]
        else:
            transactions = database.get_unenriched_truelayer_transactions() or []

        # Count cached vs API calls needed
        cached_count = 0
        requires_api = []

        for txn in transactions:
            if not txn:
                continue
            direction = 'out' if txn.get('amount', 0) < 0 else 'in'
            cached = database.get_enrichment_from_cache(txn.get('description', ''), direction)
            if cached:
                cached_count += 1
            else:
                requires_api.append(txn)

        # Calculate cost (assume 150 input + 50 output tokens per transaction)
        from config.llm_config import get_provider_cost_info
        cost_info = get_provider_cost_info(llm_cfg.provider)

        estimated_tokens = len(requires_api) * 200
        estimated_cost = (
            (len(requires_api) * 150 / 1000 * cost_info.get('cost_per_1k_input_tokens', 0)) +
            (len(requires_api) * 50 / 1000 * cost_info.get('cost_per_1k_output_tokens', 0))
        )

        return jsonify({
            'total_transactions': len(transactions),
            'cached_available': cached_count,
            'requires_api_call': len(requires_api),
            'estimated_tokens': estimated_tokens,
            'estimated_cost': round(estimated_cost, 6),
            'currency': 'USD',
            'provider': llm_cfg.provider.value,
            'model': llm_cfg.model
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/trigger', methods=['POST'])
def trigger_enrichment():
    """Start enrichment job (requires cost confirmation)."""
    try:
        data = request.get_json() or {}

        # Require cost confirmation
        if not data.get('confirm_cost'):
            return jsonify({
                'error': 'Cost confirmation required. Set confirm_cost=true to proceed.'
            }), 400

        # Check LLM configured
        from config.llm_config import load_llm_config
        if not load_llm_config():
            return jsonify({
                'configured': False,
                'error': 'LLM enrichment not configured'
            }), 503

        # Start Celery task
        from tasks.enrichment_tasks import enrich_transactions_task

        transaction_ids = data.get('transaction_ids')
        force_refresh = data.get('force_refresh', False)

        task = enrich_transactions_task.apply_async(
            args=[transaction_ids, force_refresh]
        )

        # Invalidate transaction caches (enrichment will update transactions)
        cache_manager.cache_invalidate_transactions()

        return jsonify({
            'job_id': task.id,
            'status': 'running',
            'message': 'Enrichment job started',
            'started_at': datetime.now().isoformat()
        }), 202

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/status/<job_id>', methods=['GET'])
def get_enrichment_status(job_id):
    """Get enrichment job status by Celery task ID."""
    try:
        from celery.result import AsyncResult
        from celery_app import celery_app

        task = AsyncResult(job_id, app=celery_app)

        if task.state == 'PENDING':
            return jsonify({
                'job_id': job_id,
                'status': 'pending',
                'message': 'Job not found or not started'
            }), 404

        elif task.state == 'PROGRESS':
            return jsonify({
                'job_id': job_id,
                'status': 'running',
                'current': task.info.get('current', 0),
                'total': task.info.get('total', 0),
                'progress_percentage': round(
                    (task.info.get('current', 0) / max(task.info.get('total', 1), 1)) * 100, 1
                )
            }), 200

        elif task.state == 'SUCCESS':
            result = task.result
            if isinstance(result, dict) and 'stats' in result:
                return jsonify({
                    'job_id': job_id,
                    'status': 'completed',
                    **result.get('stats', {})
                }), 200
            return jsonify(result), 200

        elif task.state == 'FAILURE':
            return jsonify({
                'job_id': job_id,
                'status': 'failed',
                'error': str(task.info)
            }), 200

        else:
            return jsonify({
                'job_id': job_id,
                'status': task.state.lower()
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/stats', methods=['GET'])
def get_enrichment_stats():
    """Get overall enrichment statistics for TrueLayer transactions."""
    try:
        # Count total TrueLayer transactions
        all_transactions = database.get_all_truelayer_transactions() or []
        total_transactions = len(all_transactions)

        # Count enriched
        enriched_count = database.count_enriched_truelayer_transactions()

        # Count unenriched
        unenriched_count = total_transactions - enriched_count

        # Cache stats
        with database.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM llm_enrichment_cache')
                cache_count = cursor.fetchone()[0]

        return jsonify({
            'total_transactions': total_transactions,
            'enriched_count': enriched_count,
            'unenriched_count': unenriched_count,
            'enrichment_percentage': round(
                (enriched_count / max(total_transactions, 1) * 100),
                1
            ),
            'cache_stats': {
                'total_cached': cache_count
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/retry', methods=['POST'])
def retry_failed_enrichments():
    """Retry failed enrichments."""
    try:
        data = request.get_json() or {}
        transaction_ids = data.get('transaction_ids')

        # Get failed transaction IDs if not specified
        if not transaction_ids:
            with database.get_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT transaction_id
                        FROM llm_enrichment_failures
                        WHERE retry_count < 3
                    """)
                    transaction_ids = [row[0] for row in cursor.fetchall()]

        # Start retry task
        from tasks.enrichment_tasks import enrich_transactions_task
        task = enrich_transactions_task.apply_async(
            args=[transaction_ids, True]  # force_refresh=True
        )

        return jsonify({
            'job_id': task.id,
            'status': 'running',
            'total_transactions': len(transaction_ids),
            'message': 'Retry job started'
        }), 202

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/available-models', methods=['GET'])
def get_available_models():
    """Get list of available models for all LLM providers."""
    try:
        from config.llm_config import load_llm_config, get_provider_info, LLMProvider

        # Check if LLM is configured
        llm_cfg = load_llm_config()
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

        return jsonify(all_models_response), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/validate', methods=['POST'])
def validate_enrichment_config():
    """Validate LLM enrichment configuration."""
    try:
        from config.llm_config import load_llm_config

        llm_cfg = load_llm_config()
        if not llm_cfg:
            return jsonify({
                'valid': False,
                'message': 'LLM enrichment is not configured'
            }), 200

        return jsonify({
            'valid': True,
            'message': f'LLM enrichment configured with {llm_cfg.provider.value} ({llm_cfg.model})'
        }), 200

    except Exception as e:
        return jsonify({
            'valid': False,
            'message': str(e)
        }), 500


@app.route('/api/enrichment/enrich-stream', methods=['GET', 'POST'])
def enrich_transactions_stream():
    """Start enrichment and stream progress via Server-Sent Events."""
    import traceback
    try:
        logger.info(f"enrich-stream endpoint called with method {request.method}")
        # Handle both GET (query params) and POST (JSON body) requests
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            # GET request - use query parameters
            data = request.args.to_dict()

        # Check LLM configured
        from config.llm_config import load_llm_config
        if not load_llm_config():
            return jsonify({
                'configured': False,
                'error': 'LLM enrichment not configured'
            }), 503

        # Get transaction selection parameters
        transaction_ids = data.get('transaction_ids')
        mode = data.get('mode', 'required')  # 'required', 'limit', 'all', 'unenriched'
        limit = data.get('limit')
        direction = data.get('direction', 'out')  # 'out', 'in', 'both'
        # Handle force_refresh as either string (GET) or bool (POST JSON)
        force_refresh_raw = data.get('force_refresh', False)
        if isinstance(force_refresh_raw, str):
            force_refresh = force_refresh_raw.lower() == 'true'
        else:
            force_refresh = bool(force_refresh_raw)

        # Convert limit to integer if provided
        if limit:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                limit = None

        # If specific transaction IDs aren't provided, query based on mode
        if not transaction_ids:
            try:
                # For 'required' mode, use optimized query
                if mode == 'required':
                    all_transactions = database.get_required_unenriched_transactions(limit=limit) or []
                    # Filter by direction if needed
                    if direction == 'out':
                        all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'DEBIT']
                    elif direction == 'in':
                        all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'CREDIT']
                else:
                    all_transactions = database.get_all_truelayer_transactions() or []

                    # Filter by direction (using transaction_type instead of amount sign)
                    if direction == 'out':
                        # Expenses are DEBIT transactions
                        all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'DEBIT']
                    elif direction == 'in':
                        # Income are CREDIT transactions
                        all_transactions = [t for t in all_transactions if t.get('transaction_type') == 'CREDIT']
                    # 'both' keeps all transactions

                    # Filter by enrichment status and limit
                    if mode == 'unenriched':
                        # Only unenriched transactions
                        all_transactions = [t for t in all_transactions if not t.get('is_enriched')]
                    elif mode == 'limit' and limit:
                        # First N transactions
                        all_transactions = all_transactions[:limit]
                    # 'all' keeps all transactions
            except Exception as e:
                import traceback
                logger.error(f"Error fetching transactions: {str(e)}")
                logger.error(traceback.format_exc())
                return jsonify({
                    'error': f'Failed to fetch transactions: {str(e)}'
                }), 500

            transaction_ids = [t.get('id') for t in all_transactions if t.get('id')]

        # Start Celery task
        from tasks.enrichment_tasks import enrich_transactions_task
        from celery.result import AsyncResult
        from celery_app import celery_app

        task = enrich_transactions_task.apply_async(
            args=[transaction_ids, force_refresh]
        )

        def generate_progress_stream():
            """Generate Server-Sent Events for enrichment progress.

            Sends events in format expected by frontend ProgressUpdate interface:
            - type: 'start' | 'progress' | 'complete' | 'error'
            - processed: current count
            - total: total count
            - percentage: 0-100
            """
            import time

            # Send initial event (frontend expects 'type' not 'status')
            yield f"data: {json.dumps({'type': 'start', 'job_id': task.id, 'total': len(transaction_ids)})}\n\n"

            # Poll task status every 500ms
            while True:
                try:
                    task_result = AsyncResult(task.id, app=celery_app)

                    if task_result.state == 'PROGRESS':
                        progress_data = task_result.info or {}
                        # Transform field names: current -> processed
                        current = progress_data.get('current', 0)
                        total = progress_data.get('total', len(transaction_ids))
                        percentage = round((current / total * 100) if total > 0 else 0)

                        yield f"data: {json.dumps({
                            'type': 'progress',
                            'processed': current,
                            'total': total,
                            'percentage': percentage,
                            'successful': progress_data.get('successful', 0),
                            'failed': progress_data.get('failed', 0),
                            'tokens_used': progress_data.get('tokens_used', 0),
                            'cost': progress_data.get('cost', 0.0)
                        })}\n\n"

                    elif task_result.state == 'SUCCESS':
                        result = task_result.result or {}
                        if isinstance(result, dict) and 'stats' in result:
                            stats = result.get('stats', {})
                            yield f"data: {json.dumps({
                                'type': 'complete',
                                'processed': stats.get('total_transactions', 0),
                                'total': stats.get('total_transactions', 0),
                                'percentage': 100,
                                'successful': stats.get('successful_enrichments', 0),
                                'failed': stats.get('failed_enrichments', 0),
                                'total_tokens': stats.get('total_tokens_used', 0),
                                'total_cost': stats.get('total_cost', 0.0)
                            })}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
                        break

                    elif task_result.state == 'FAILURE':
                        yield f"data: {json.dumps({'type': 'error', 'error': str(task_result.info)})}\n\n"
                        break

                    elif task_result.state == 'PENDING':
                        # Task is queued but not yet started
                        yield f"data: {json.dumps({'type': 'start', 'processed': 0, 'total': len(transaction_ids), 'percentage': 0, 'message': 'Queued'})}\n\n"

                    else:
                        # Unknown state - send as progress with 0
                        yield f"data: {json.dumps({'type': 'progress', 'processed': 0, 'total': len(transaction_ids), 'percentage': 0, 'message': task_result.state})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
                    break

                time.sleep(0.5)

        return Response(
            stream_with_context(generate_progress_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'  # Disable Nginx buffering
            }
        )

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Enrich-stream endpoint error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        print(f"ERROR in enrich-stream: {str(e)}")
        print(f"TRACEBACK: {error_trace}")
        return jsonify({'error': str(e), 'details': error_trace}), 500


@app.route('/api/migrations/fix-card-payment-merchants', methods=['POST'])
def fix_card_payment_merchants():
    """Extract real merchant names from card payment transactions and update the database."""
    try:
        result = database.fix_card_payment_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/account-mappings', methods=['GET'])
def get_account_mappings():
    """Get all account mappings."""
    try:
        mappings = database.get_all_account_mappings()
        return jsonify(mappings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/account-mappings', methods=['POST'])
def create_account_mapping():
    """Create a new account mapping."""
    try:
        data = request.json

        if not data.get('sort_code') or not data.get('account_number') or not data.get('friendly_name'):
            return jsonify({'error': 'Missing required fields'}), 400

        # Validate format
        sort_code = str(data['sort_code']).replace('-', '').replace(' ', '')
        account_number = str(data['account_number']).replace(' ', '')

        if not re.match(r'^\d{6}$', sort_code):
            return jsonify({'error': 'Sort code must be 6 digits'}), 400

        if not re.match(r'^\d{8}$', account_number):
            return jsonify({'error': 'Account number must be 8 digits'}), 400

        mapping_id = database.add_account_mapping(
            sort_code,
            account_number,
            data['friendly_name']
        )

        if mapping_id is None:
            return jsonify({'error': 'Account mapping already exists'}), 409

        return jsonify({'success': True, 'id': mapping_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/account-mappings/<int:mapping_id>', methods=['PUT'])
def update_account_mapping_endpoint(mapping_id):
    """Update an existing account mapping."""
    try:
        data = request.json

        if not data.get('friendly_name'):
            return jsonify({'error': 'Missing friendly_name'}), 400

        success = database.update_account_mapping(mapping_id, data['friendly_name'])

        if not success:
            return jsonify({'error': 'Account mapping not found'}), 404

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/account-mappings/<int:mapping_id>', methods=['DELETE'])
def delete_account_mapping_endpoint(mapping_id):
    """Delete an account mapping."""
    try:
        success = database.delete_account_mapping(mapping_id)

        if not success:
            return jsonify({'error': 'Account mapping not found'}), 404

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/account-mappings/discover', methods=['GET'])
def discover_account_mappings():
    """Scan TrueLayer transactions for unmapped account patterns."""
    try:
        from mcp.merchant_normalizer import detect_account_pattern

        # Get all TrueLayer transactions
        transactions = database.get_all_truelayer_transactions()

        # Get existing mappings to filter them out
        existing_mappings = database.get_all_account_mappings()
        mapped_accounts = {(m['sort_code'], m['account_number']) for m in existing_mappings}

        # Scan for account patterns
        discovered = {}  # key: (sort_code, account_number), value: {count, sample_description}

        for txn in transactions:
            description = txn.get('description', '') or ''
            merchant = txn.get('merchant_name', '') or ''

            # Try to detect account pattern in description or merchant
            account_info = detect_account_pattern(description)
            if not account_info:
                account_info = detect_account_pattern(merchant)

            if account_info:
                sort_code, account_number = account_info

                # Skip if already mapped
                if (sort_code, account_number) in mapped_accounts:
                    continue

                key = (sort_code, account_number)
                if key not in discovered:
                    discovered[key] = {
                        'sort_code': sort_code,
                        'account_number': account_number,
                        'sample_description': description[:100] if description else merchant[:100],
                        'count': 0
                    }
                discovered[key]['count'] += 1

        # Convert to list and sort by count descending
        result = sorted(discovered.values(), key=lambda x: x['count'], reverse=True)

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/<int:transaction_id>/huququllah', methods=['PUT'])
def update_huququllah_classification(transaction_id):
    """Update the Huququllah classification for a transaction."""
    try:
        data = request.json
        classification = data.get('classification')

        # Validate classification
        if classification not in ['essential', 'discretionary', None]:
            return jsonify({'error': 'Invalid classification. Must be "essential", "discretionary", or null'}), 400

        success = database.update_transaction_huququllah(transaction_id, classification)

        if success:
            return jsonify({'success': True, 'transaction_id': transaction_id, 'classification': classification})
        else:
            return jsonify({'error': 'Transaction not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/huququllah/suggest/<int:transaction_id>', methods=['GET'])
def get_huququllah_suggestion(transaction_id):
    """Get a smart suggestion for classifying a transaction."""
    try:
        from mcp.huququllah_classifier import get_suggestion_for_transaction
        suggestion = get_suggestion_for_transaction(transaction_id)
        return jsonify(suggestion)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/huququllah/summary', methods=['GET'])
def get_huququllah_summary():
    """Get Huququllah summary with essential vs discretionary totals and 19% calculation."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        summary = database.get_huququllah_summary(date_from, date_to)
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/huququllah/unclassified', methods=['GET'])
def get_unclassified_transactions():
    """Get all transactions that haven't been classified yet."""
    try:
        transactions = database.get_unclassified_transactions()
        return jsonify(transactions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/api/migrations/add-huququllah-column', methods=['POST'])
def migrate_huququllah_column():
    """Migration endpoint to add huququllah_classification column to existing databases."""
    try:
        was_added = database.migrate_add_huququllah_column()
        return jsonify({
            'success': True,
            'column_added': was_added,
            'message': 'Migration completed successfully' if was_added else 'Column already exists'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/reapply-account-mappings', methods=['POST'])
def reapply_account_mappings():
    """Apply all account mappings to existing TrueLayer transactions."""
    try:
        from mcp.merchant_normalizer import detect_account_pattern

        # Get all account mappings
        mappings = database.get_all_account_mappings()
        if not mappings:
            return jsonify({
                'success': True,
                'transactions_updated': 0,
                'transactions_total': 0,
                'message': 'No account mappings configured'
            })

        # Create lookup dict for mappings
        mapping_lookup = {(m['sort_code'], m['account_number']): m['friendly_name'] for m in mappings}

        # Get all TrueLayer transactions
        transactions = database.get_all_truelayer_transactions()
        total = len(transactions)
        updated = 0

        for txn in transactions:
            description = txn.get('description', '') or ''
            merchant = txn.get('merchant_name', '') or ''

            # Try to detect account pattern
            account_info = detect_account_pattern(description)
            if not account_info:
                account_info = detect_account_pattern(merchant)

            if account_info:
                sort_code, account_number = account_info
                friendly_name = mapping_lookup.get((sort_code, account_number))

                if friendly_name:
                    new_merchant = f"Payment to {friendly_name}"
                    # Update the transaction if merchant name is different
                    if merchant != new_merchant:
                        database.update_truelayer_transaction_merchant(txn['id'], new_merchant)
                        updated += 1

        return jsonify({
            'success': True,
            'transactions_updated': updated,
            'transactions_total': total
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Pre-Enrichment Status Endpoints
# ============================================================================

@app.route('/api/pre-enrichment/summary', methods=['GET'])
def get_pre_enrichment_summary():
    """Get summary of identified transactions by vendor (matched + unmatched)."""
    try:
        summary = database.get_identified_summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pre-enrichment/backfill', methods=['POST'])
def backfill_pre_enrichment():
    """Backfill pre_enrichment_status for all existing transactions.

    Analyzes all transactions and sets their status based on description patterns
    and existing matches in the database.
    """
    try:
        counts = database.backfill_pre_enrichment_status()

        # Invalidate transaction cache if available
        try:
            from cache_manager import cache_invalidate_transactions
            cache_invalidate_transactions()
        except ImportError:
            pass  # Cache manager not available

        return jsonify({
            'success': True,
            'counts': counts,
            'message': f"Analyzed {sum(counts.values())} transactions"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preai/jobs/active', methods=['GET'])
def get_active_preai_jobs():
    """Get all active Pre-AI jobs for the current user.

    Returns any running Gmail sync jobs and matching jobs.
    Used by frontend to resume progress tracking after navigation.

    Auto-cleans up stale jobs (stuck > 30 min) before returning.
    """
    try:
        user_id = int(request.args.get('user_id', 1))

        # Auto-cleanup stale jobs before checking active ones
        cleanup_result = database.cleanup_stale_matching_jobs(stale_threshold_minutes=30)
        if cleanup_result['cleaned_up'] > 0:
            print(f"🧹 Auto-cleaned {cleanup_result['cleaned_up']} stale matching jobs: {cleanup_result['job_ids']}")

        # Get active Gmail sync job
        gmail_job = database.get_latest_active_gmail_sync_job(user_id)

        # Get active matching jobs
        matching_jobs = database.get_active_matching_jobs(user_id)

        return jsonify({
            'gmail_sync': gmail_job,
            'matching': matching_jobs
        })
    except Exception as e:
        print(f"❌ Active jobs error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/matching/jobs/<int:job_id>', methods=['GET'])
def get_matching_job_status(job_id):
    """Get status of a specific matching job."""
    try:
        job = database.get_matching_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)
    except Exception as e:
        print(f"❌ Matching job status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/matching/jobs/cleanup-stale', methods=['POST'])
def cleanup_stale_jobs():
    """Cleanup stale matching jobs older than 30 minutes.

    Marks jobs stuck in 'queued' or 'running' status as 'failed'.
    """
    try:
        threshold = int(request.args.get('threshold_minutes', 30))
        result = database.cleanup_stale_matching_jobs(stale_threshold_minutes=threshold)
        return jsonify({
            'success': True,
            'cleaned_up': result['cleaned_up'],
            'job_ids': result['job_ids']
        })
    except Exception as e:
        print(f"❌ Cleanup stale jobs error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Unified Matching Endpoints
# ============================================================================


@app.route('/api/matching/coverage', methods=['GET'])
def get_matching_coverage():
    """
    Get source coverage dates to detect stale data.

    Returns date ranges for each source and flags which ones are stale
    (more than 7 days behind bank transaction data).

    Response:
    {
        "bank_transactions": {"max_date": "2025-12-20", "count": 1500},
        "amazon": {"max_date": "2025-12-10", "count": 200, "is_stale": true},
        "apple": {"max_date": "2025-12-19", "count": 50, "is_stale": false},
        "gmail": {"max_date": "2025-12-15", "count": 100, "is_stale": true},
        "stale_sources": ["amazon", "gmail"],
        "stale_threshold_days": 7
    }
    """
    try:
        user_id = request.args.get('user_id', 1, type=int)
        coverage = database.get_source_coverage_dates(user_id)
        return jsonify(coverage)
    except Exception as e:
        print(f"❌ Matching coverage error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/matching/run', methods=['POST'])
def run_unified_matching():
    """
    Unified matching endpoint - runs matching across all sources in parallel.

    Request body:
    {
        "sources": ["amazon", "apple", "gmail"],  # Optional - default: all
        "sync_sources_first": false  # Optional - sync source data before matching
    }

    Returns:
    {
        "job_id": "unified-123",
        "status": "running",
        "source_coverage_warning": {...} // if any sources are stale
    }
    """
    try:
        data = request.json or {}
        user_id = data.get('user_id', 1)
        sources = data.get('sources', ['amazon', 'apple', 'gmail'])
        sync_first = data.get('sync_sources_first', False)

        # Check source coverage first
        coverage = database.get_source_coverage_dates(user_id)
        stale_warning = None
        if coverage.get('stale_sources'):
            stale_warning = {
                'stale_sources': coverage['stale_sources'],
                'bank_max_date': coverage['bank_transactions']['max_date'],
                'sources': {
                    source: coverage[source]
                    for source in coverage['stale_sources']
                }
            }

        # Import Celery task
        from tasks.matching_tasks import unified_matching_task

        # Launch the unified matching task
        task = unified_matching_task.delay(user_id, sources, sync_first)

        return jsonify({
            'job_id': task.id,
            'status': 'running',
            'sources': sources,
            'sync_sources_first': sync_first,
            'source_coverage_warning': stale_warning
        })

    except ImportError as e:
        # Fallback if Celery task not yet implemented
        print(f"⚠️ Unified matching task not implemented yet: {e}")
        return jsonify({
            'error': 'Unified matching task not yet implemented',
            'message': 'Run individual matchers via /api/amazon/match, /api/apple/match, /api/gmail/match'
        }), 501
    except Exception as e:
        print(f"❌ Unified matching error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Direct Debit Mapping Endpoints
# ============================================================================


@app.route('/api/direct-debit/payees', methods=['GET'])
def get_direct_debit_payees():
    """Get unique direct debit payees from transactions.

    Returns list of payees with transaction counts and current enrichment status.
    """
    try:
        payees = database.get_direct_debit_payees()
        return jsonify(payees)
    except Exception as e:
        print(f"❌ Direct debit payees error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/direct-debit/mappings', methods=['GET'])
def get_direct_debit_mappings():
    """Get all configured direct debit mappings."""
    try:
        mappings = database.get_direct_debit_mappings()
        return jsonify(mappings)
    except Exception as e:
        print(f"❌ Direct debit mappings error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/direct-debit/mappings', methods=['POST'])
def save_direct_debit_mapping():
    """Create or update a direct debit mapping.

    Request body:
    {
        "payee_pattern": "EMMANUEL COLL",
        "normalized_name": "Emmanuel College",
        "category": "Charity",
        "subcategory": "Emmanuel College",
        "merchant_type": "Educational/Charity"
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Missing request body'}), 400

        payee_pattern = data.get('payee_pattern')
        normalized_name = data.get('normalized_name')
        category = data.get('category')

        if not payee_pattern or not normalized_name or not category:
            return jsonify({'error': 'Missing required fields: payee_pattern, normalized_name, category'}), 400

        mapping_id = database.save_direct_debit_mapping(
            payee_pattern=payee_pattern,
            normalized_name=normalized_name,
            category=category,
            subcategory=data.get('subcategory'),
            merchant_type=data.get('merchant_type')
        )

        return jsonify({
            'success': True,
            'mapping_id': mapping_id,
            'message': f'Mapping saved for {payee_pattern}'
        }), 201
    except Exception as e:
        print(f"❌ Save direct debit mapping error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/direct-debit/mappings/<int:mapping_id>', methods=['DELETE'])
def delete_direct_debit_mapping(mapping_id):
    """Delete a direct debit mapping."""
    try:
        deleted = database.delete_direct_debit_mapping(mapping_id)
        if deleted:
            return jsonify({'success': True, 'message': 'Mapping deleted'})
        else:
            return jsonify({'error': 'Mapping not found'}), 404
    except Exception as e:
        print(f"❌ Delete direct debit mapping error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/direct-debit/apply-mappings', methods=['POST'])
def apply_direct_debit_mappings():
    """Apply all direct debit mappings to transactions.

    Re-enriches all direct debit transactions using the configured mappings.
    """
    try:
        result = database.apply_direct_debit_mappings()

        # Invalidate transaction cache if available
        try:
            from cache_manager import cache_invalidate_transactions
            cache_invalidate_transactions()
        except ImportError:
            pass  # Cache manager not available

        return jsonify({
            'success': True,
            'updated_count': result['updated_count'],
            'transactions': result['transactions'],
            'message': f"Updated {result['updated_count']} transactions"
        })
    except Exception as e:
        print(f"❌ Apply direct debit mappings error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/direct-debit/new', methods=['GET'])
def get_new_direct_debits():
    """Get newly detected direct debit payees that haven't been mapped.

    Returns list of unmapped payees with transaction counts and mandate numbers.
    """
    try:
        result = database.detect_new_direct_debits()
        return jsonify(result)
    except Exception as e:
        print(f"❌ Detect new direct debits error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Enrichment Rules Management Endpoints
# ============================================================================

@app.route('/api/rules/category', methods=['GET'])
def get_category_rules():
    """Get all category rules with optional filtering.

    Query params:
        active_only: Filter to active rules only (default: true)
        category: Filter by category
        source: Filter by source (manual, learned, llm)
    """
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        rules = database.get_category_rules(active_only=active_only)

        # Apply filters
        category_filter = request.args.get('category')
        source_filter = request.args.get('source')

        if category_filter:
            rules = [r for r in rules if r.get('category') == category_filter]
        if source_filter:
            rules = [r for r in rules if r.get('source') == source_filter]

        return jsonify(rules)
    except Exception as e:
        print(f"❌ Get category rules error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/category', methods=['POST'])
def create_category_rule():
    """Create a new category rule.

    Body:
        rule_name: Human-readable name (required)
        description_pattern: Pattern to match (required)
        category: Target category (required)
        pattern_type: contains, starts_with, exact, regex (default: contains)
        transaction_type: CREDIT, DEBIT, or null for all
        subcategory: Optional subcategory
        priority: Integer priority (default: 0)
    """
    try:
        data = request.json
        from mcp.pattern_utils import parse_pattern_with_prefix, validate_pattern

        # Parse pattern if it has a prefix
        pattern = data.get('description_pattern', '')
        pattern_type = data.get('pattern_type')

        if not pattern_type:
            # Auto-detect from prefix
            pattern, pattern_type = parse_pattern_with_prefix(pattern)

        # Validate pattern
        is_valid, error_msg = validate_pattern(pattern, pattern_type)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        rule_id = database.add_category_rule(
            rule_name=data.get('rule_name'),
            description_pattern=pattern,
            category=data.get('category'),
            transaction_type=data.get('transaction_type'),
            subcategory=data.get('subcategory'),
            pattern_type=pattern_type,
            priority=data.get('priority', 0),
            source=data.get('source', 'manual')
        )

        return jsonify({
            'success': True,
            'id': rule_id,
            'message': f"Created rule '{data.get('rule_name')}'"
        }), 201
    except Exception as e:
        print(f"❌ Create category rule error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/category/<int:rule_id>', methods=['PUT'])
def update_category_rule(rule_id):
    """Update an existing category rule."""
    try:
        data = request.json
        from mcp.pattern_utils import parse_pattern_with_prefix, validate_pattern

        # Handle pattern prefix if provided
        if 'description_pattern' in data:
            pattern = data['description_pattern']
            pattern_type = data.get('pattern_type')
            if not pattern_type:
                pattern, pattern_type = parse_pattern_with_prefix(pattern)
                data['description_pattern'] = pattern
                data['pattern_type'] = pattern_type

            is_valid, error_msg = validate_pattern(
                data['description_pattern'],
                data.get('pattern_type', 'contains')
            )
            if not is_valid:
                return jsonify({'error': error_msg}), 400

        success = database.update_category_rule(rule_id, **data)

        if success:
            return jsonify({'success': True, 'message': f"Updated rule {rule_id}"})
        else:
            return jsonify({'error': 'Rule not found'}), 404
    except Exception as e:
        print(f"❌ Update category rule error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/category/<int:rule_id>', methods=['DELETE'])
def delete_category_rule(rule_id):
    """Delete a category rule."""
    try:
        success = database.delete_category_rule(rule_id)
        if success:
            return jsonify({'success': True, 'message': f"Deleted rule {rule_id}"})
        else:
            return jsonify({'error': 'Rule not found'}), 404
    except Exception as e:
        print(f"❌ Delete category rule error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/category/<int:rule_id>/test', methods=['POST'])
def test_category_rule(rule_id):
    """Test an existing category rule against all transactions."""
    try:
        # Get the rule
        rules = database.get_category_rules(active_only=False)
        rule = next((r for r in rules if r['id'] == rule_id), None)
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404

        result = database.test_rule_pattern(
            rule['description_pattern'],
            rule['pattern_type'],
            limit=request.args.get('limit', 10, type=int)
        )
        return jsonify(result)
    except Exception as e:
        print(f"❌ Test category rule error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/category/test-pattern', methods=['POST'])
def test_category_pattern():
    """Test a pattern against transactions before creating a rule.

    Body:
        pattern: The pattern to test
        pattern_type: contains, starts_with, exact, regex (optional - auto-detect from prefix)
        limit: Max transactions to return (default: 10)
    """
    try:
        data = request.json
        from mcp.pattern_utils import parse_pattern_with_prefix, validate_pattern

        pattern = data.get('pattern', '')
        pattern_type = data.get('pattern_type')

        if not pattern_type:
            pattern, pattern_type = parse_pattern_with_prefix(pattern)

        # Validate pattern
        is_valid, error_msg = validate_pattern(pattern, pattern_type)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        result = database.test_rule_pattern(
            pattern,
            pattern_type,
            limit=data.get('limit', 10)
        )
        return jsonify(result)
    except Exception as e:
        print(f"❌ Test category pattern error: {e}")
        return jsonify({'error': str(e)}), 500


# Merchant Normalization Endpoints

@app.route('/api/rules/merchant', methods=['GET'])
def get_merchant_normalizations():
    """Get all merchant normalizations with optional filtering.

    Query params:
        source: Filter by source (manual, learned, llm, direct_debit)
        category: Filter by default_category
    """
    try:
        normalizations = database.get_merchant_normalizations()

        # Apply filters
        source_filter = request.args.get('source')
        category_filter = request.args.get('category')

        if source_filter:
            normalizations = [n for n in normalizations if n.get('source') == source_filter]
        if category_filter:
            normalizations = [n for n in normalizations if n.get('default_category') == category_filter]

        return jsonify(normalizations)
    except Exception as e:
        print(f"❌ Get merchant normalizations error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/merchant', methods=['POST'])
def create_merchant_normalization():
    """Create a new merchant normalization.

    Body:
        pattern: Pattern to match (required)
        normalized_name: Clean merchant name (required)
        pattern_type: contains, starts_with, exact, regex (default: contains)
        merchant_type: Business type (optional)
        default_category: Category to assign (optional)
        priority: Integer priority (default: 0)
    """
    try:
        data = request.json
        from mcp.pattern_utils import parse_pattern_with_prefix, validate_pattern

        pattern = data.get('pattern', '')
        pattern_type = data.get('pattern_type')

        if not pattern_type:
            pattern, pattern_type = parse_pattern_with_prefix(pattern)

        is_valid, error_msg = validate_pattern(pattern, pattern_type)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        norm_id = database.add_merchant_normalization(
            pattern=pattern,
            normalized_name=data.get('normalized_name'),
            merchant_type=data.get('merchant_type'),
            default_category=data.get('default_category'),
            pattern_type=pattern_type,
            priority=data.get('priority', 0),
            source=data.get('source', 'manual')
        )

        return jsonify({
            'success': True,
            'id': norm_id,
            'message': f"Created merchant normalization for '{pattern}'"
        }), 201
    except Exception as e:
        print(f"❌ Create merchant normalization error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/merchant/<int:norm_id>', methods=['PUT'])
def update_merchant_normalization(norm_id):
    """Update an existing merchant normalization."""
    try:
        data = request.json
        from mcp.pattern_utils import parse_pattern_with_prefix, validate_pattern

        if 'pattern' in data:
            pattern = data['pattern']
            pattern_type = data.get('pattern_type')
            if not pattern_type:
                pattern, pattern_type = parse_pattern_with_prefix(pattern)
                data['pattern'] = pattern
                data['pattern_type'] = pattern_type

            is_valid, error_msg = validate_pattern(
                data['pattern'],
                data.get('pattern_type', 'contains')
            )
            if not is_valid:
                return jsonify({'error': error_msg}), 400

        success = database.update_merchant_normalization(norm_id, **data)

        if success:
            return jsonify({'success': True, 'message': f"Updated normalization {norm_id}"})
        else:
            return jsonify({'error': 'Normalization not found'}), 404
    except Exception as e:
        print(f"❌ Update merchant normalization error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/merchant/<int:norm_id>', methods=['DELETE'])
def delete_merchant_normalization(norm_id):
    """Delete a merchant normalization."""
    try:
        success = database.delete_merchant_normalization(norm_id)
        if success:
            return jsonify({'success': True, 'message': f"Deleted normalization {norm_id}"})
        else:
            return jsonify({'error': 'Normalization not found'}), 404
    except Exception as e:
        print(f"❌ Delete merchant normalization error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/merchant/<int:norm_id>/test', methods=['POST'])
def test_merchant_normalization(norm_id):
    """Test an existing merchant normalization against all transactions."""
    try:
        normalizations = database.get_merchant_normalizations()
        norm = next((n for n in normalizations if n['id'] == norm_id), None)
        if not norm:
            return jsonify({'error': 'Normalization not found'}), 404

        result = database.test_rule_pattern(
            norm['pattern'],
            norm['pattern_type'],
            limit=request.args.get('limit', 10, type=int)
        )
        return jsonify(result)
    except Exception as e:
        print(f"❌ Test merchant normalization error: {e}")
        return jsonify({'error': str(e)}), 500


# Bulk Operations

@app.route('/api/rules/statistics', methods=['GET'])
def get_rules_statistics():
    """Get comprehensive rule usage statistics and coverage metrics."""
    try:
        stats = database.get_rules_statistics()
        return jsonify(stats)
    except Exception as e:
        print(f"❌ Get rules statistics error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/test-all', methods=['POST'])
def test_all_rules():
    """Evaluate all rules against all transactions.

    Returns detailed coverage report with category breakdown,
    unused rules, and potential conflicts.
    """
    try:
        result = database.test_all_rules()
        return jsonify(result)
    except Exception as e:
        print(f"❌ Test all rules error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/apply-all', methods=['POST'])
def apply_all_rules():
    """Re-apply all rules to all transactions.

    This re-enriches all transactions using the current rules,
    updating any transactions that match.
    """
    try:
        result = database.apply_all_rules_to_transactions()

        # Invalidate transaction cache if available
        try:
            from cache_manager import cache_invalidate_transactions
            cache_invalidate_transactions()
        except ImportError:
            pass

        return jsonify({
            'success': True,
            'updated_count': result['updated_count'],
            'total_transactions': result['total_transactions'],
            'rule_hits': result['rule_hits'],
            'message': f"Updated {result['updated_count']} of {result['total_transactions']} transactions"
        })
    except Exception as e:
        print(f"❌ Apply all rules error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Amazon Order History Endpoints
# ============================================================================

@app.route('/api/amazon/import', methods=['POST'])
def import_amazon_orders():
    """Import Amazon order history from CSV file or content."""
    try:
        data = request.json
        website = data.get('website', 'Amazon.co.uk')  # Default to Amazon.co.uk

        # Support both file content (new) and filename (legacy)
        if 'csv_content' in data and data['csv_content']:
            from mcp.amazon_parser import parse_amazon_csv_content
            orders = parse_amazon_csv_content(data['csv_content'])
            source_name = data.get('filename', 'uploaded_file.csv')
        elif 'filename' in data:
            # Legacy: load from sample folder
            from mcp.amazon_parser import parse_amazon_csv
            import os
            file_path = os.path.join('..', 'sample', data['filename'])
            if not os.path.exists(file_path):
                return jsonify({'error': f'File not found: {data["filename"]}'}), 404
            orders = parse_amazon_csv(file_path)
            source_name = data['filename']
        else:
            return jsonify({'error': 'Missing csv_content or filename'}), 400

        # Import orders into database
        imported, duplicates = database.import_amazon_orders(orders, source_name)

        # Run matching on existing transactions
        from mcp.amazon_matcher import match_all_amazon_transactions
        match_results = match_all_amazon_transactions()

        return jsonify({
            'success': True,
            'orders_imported': imported,
            'orders_duplicated': duplicates,
            'matching_results': match_results,
            'filename': source_name
        }), 201

    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@app.route('/api/amazon/orders', methods=['GET'])
def get_amazon_orders():
    """Get all Amazon orders with optional filters."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        website = request.args.get('website')

        orders = database.get_amazon_orders(date_from, date_to, website)

        return jsonify({
            'orders': orders,
            'count': len(orders)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/statistics', methods=['GET'])
def get_amazon_stats():
    """Get Amazon import and matching statistics (cached)."""
    try:
        # Check cache first
        cache_key = "amazon:statistics"
        cached_data = cache_manager.cache_get(cache_key)
        if cached_data is not None:
            return jsonify(cached_data)

        # Cache miss - fetch from database
        stats = database.get_amazon_statistics()

        # Cache the result (15 minute TTL)
        cache_manager.cache_set(cache_key, stats, ttl=900)

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/match', methods=['POST'])
def run_amazon_matching():
    """Run or re-run Amazon matching on existing transactions.

    Query params:
        async: If 'true', runs matching as async Celery task and returns job_id
    """
    try:
        async_mode = request.args.get('async', 'true').lower() == 'true'
        user_id = int(request.args.get('user_id', 1))

        if async_mode:
            # Create job entry and dispatch Celery task
            from tasks.matching_tasks import match_amazon_orders_task

            job_id = database.create_matching_job(user_id, 'amazon')
            task = match_amazon_orders_task.delay(job_id, user_id)

            # Update job with celery task ID
            database.update_matching_job_status(job_id, 'queued')

            return jsonify({
                'success': True,
                'async': True,
                'job_id': job_id,
                'celery_task_id': task.id,
                'status': 'queued'
            })
        else:
            # Sync mode for backward compatibility
            from mcp.amazon_matcher import match_all_amazon_transactions
            results = match_all_amazon_transactions()

            # Invalidate Amazon caches
            cache_manager.cache_invalidate_amazon()

            return jsonify({
                'success': True,
                'async': False,
                'results': results
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/match/<int:transaction_id>', methods=['POST'])
def rematch_single_transaction(transaction_id):
    """Re-match a specific transaction with Amazon orders."""
    try:
        from mcp.amazon_matcher import rematch_transaction
        result = rematch_transaction(transaction_id)

        if result and result.get('success'):
            return jsonify(result)
        else:
            return jsonify({
                'error': 'No suitable match found',
                'details': result
            }), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/coverage', methods=['GET'])
def check_amazon_coverage():
    """Check if Amazon order data exists for a date range."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Missing date_from or date_to parameters'}), 400

        coverage = database.check_amazon_coverage(date_from, date_to)

        return jsonify(coverage)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/unmatched', methods=['GET'])
def get_unmatched_amazon_transactions():
    """Get all Amazon transactions that haven't been matched to orders."""
    try:
        unmatched = database.get_unmatched_amazon_transactions()

        return jsonify({
            'transactions': unmatched,
            'count': len(unmatched)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/orders', methods=['DELETE'])
def clear_amazon_data():
    """Clear all Amazon orders and matches (for testing/reimporting)."""
    try:
        orders_deleted, matches_deleted = database.clear_amazon_orders()

        return jsonify({
            'success': True,
            'orders_deleted': orders_deleted,
            'matches_deleted': matches_deleted,
            'message': f'Cleared {orders_deleted} orders and {matches_deleted} matches'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/files', methods=['GET'])
def list_amazon_files():
    """List available Amazon CSV files in the sample folder."""
    try:
        from mcp.amazon_parser import get_amazon_csv_files
        files = get_amazon_csv_files('../sample')

        # Get just the filenames
        import os
        file_list = [{'filename': os.path.basename(f), 'path': f} for f in files]

        return jsonify({
            'files': file_list,
            'count': len(file_list)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/upload', methods=['POST'])
def upload_amazon_file():
    """Upload an Amazon CSV file."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'Only CSV files are allowed'}), 400

        # Save the file to the sample folder
        import os
        sample_folder = os.path.join(os.path.dirname(__file__), '..', 'sample')
        os.makedirs(sample_folder, exist_ok=True)

        # Sanitize filename
        filename = os.path.basename(file.filename)
        filepath = os.path.join(sample_folder, filename)

        # Save file
        file.save(filepath)

        return jsonify({
            'success': True,
            'message': f'File uploaded successfully: {filename}',
            'filename': filename
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Amazon Returns Endpoints
# ============================================================================

@app.route('/api/amazon/returns/import', methods=['POST'])
def import_amazon_returns():
    """Import Amazon returns/refunds from CSV file or content."""
    try:
        data = request.json

        # Support both file content (new) and filename (legacy)
        if 'csv_content' in data and data['csv_content']:
            from mcp.amazon_returns_parser import parse_amazon_returns_csv_content
            returns = parse_amazon_returns_csv_content(data['csv_content'])
            source_name = data.get('filename', 'uploaded_file.csv')
        elif 'filename' in data:
            # Legacy: load from sample folder
            from mcp.amazon_returns_parser import parse_amazon_returns_csv
            import os
            file_path = os.path.join('..', 'sample', data['filename'])
            if not os.path.exists(file_path):
                return jsonify({'error': f'File not found: {data["filename"]}'}), 404
            returns = parse_amazon_returns_csv(file_path)
            source_name = data['filename']
        else:
            return jsonify({'error': 'Missing csv_content or filename'}), 400

        # Import returns into database
        imported, duplicates = database.import_amazon_returns(returns, source_name)

        # Run matching on imported returns
        from mcp.amazon_returns_matcher import match_all_returns
        match_results = match_all_returns()

        return jsonify({
            'success': True,
            'returns_imported': imported,
            'returns_duplicated': duplicates,
            'matching_results': match_results,
            'filename': source_name
        }), 201

    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@app.route('/api/amazon/returns', methods=['GET'])
def get_amazon_returns():
    """Get all Amazon returns."""
    try:
        returns = database.get_amazon_returns()

        return jsonify({
            'returns': returns,
            'count': len(returns)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/returns/statistics', methods=['GET'])
def get_returns_stats():
    """Get Amazon returns statistics (cached)."""
    try:
        # Check cache first
        cache_key = "amazon:returns:statistics"
        cached_data = cache_manager.cache_get(cache_key)
        if cached_data is not None:
            return jsonify(cached_data)

        # Cache miss - fetch from database
        stats = database.get_returns_statistics()

        # Cache the result (15 minute TTL)
        cache_manager.cache_set(cache_key, stats, ttl=900)

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/returns/match', methods=['POST'])
def run_returns_matching():
    """Run or re-run returns matching.

    Query params:
        async: If 'true', runs matching as async Celery task and returns job_id
    """
    try:
        async_mode = request.args.get('async', 'true').lower() == 'true'
        user_id = int(request.args.get('user_id', 1))

        if async_mode:
            # Create job entry and dispatch Celery task
            from tasks.matching_tasks import match_amazon_returns_task

            job_id = database.create_matching_job(user_id, 'returns')
            task = match_amazon_returns_task.delay(job_id, user_id)

            # Update job with celery task ID
            database.update_matching_job_status(job_id, 'queued')

            return jsonify({
                'success': True,
                'async': True,
                'job_id': job_id,
                'celery_task_id': task.id,
                'status': 'queued'
            })
        else:
            # Sync mode for backward compatibility
            from mcp.amazon_returns_matcher import match_all_returns
            results = match_all_returns()

            # Invalidate Amazon caches
            cache_manager.cache_invalidate_amazon()

            return jsonify({
                'success': True,
                'async': False,
                'results': results
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/returns', methods=['DELETE'])
def clear_returns_data():
    """Clear all Amazon returns (for testing/reimporting)."""
    try:
        returns_deleted = database.clear_amazon_returns()

        return jsonify({
            'success': True,
            'returns_deleted': returns_deleted,
            'message': f'Cleared {returns_deleted} returns and removed [RETURNED] labels'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/returns/files', methods=['GET'])
def list_returns_files():
    """List available Amazon returns CSV files in the sample folder."""
    try:
        from mcp.amazon_returns_parser import get_amazon_returns_csv_files
        files = get_amazon_returns_csv_files('../sample')

        # Get just the filenames
        import os
        file_list = [{'filename': os.path.basename(f), 'path': f} for f in files]

        return jsonify({
            'files': file_list,
            'count': len(file_list)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Apple Transactions Endpoints
# ============================================================================

@app.route('/api/apple/import', methods=['POST'])
def import_apple_transactions():
    """Import Apple transactions from HTML file."""
    try:
        data = request.json

        if 'filename' not in data:
            return jsonify({'error': 'Missing filename'}), 400

        filename = data['filename']
        file_path = os.path.join('..', 'sample', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {filename}'}), 404

        # Parse HTML file
        from mcp.apple_parser import parse_apple_html
        transactions = parse_apple_html(file_path)

        if not transactions:
            return jsonify({'error': 'No transactions found in HTML file'}), 400

        # Import to database
        imported, duplicates = database.import_apple_transactions(transactions, filename)

        # Run matching with TrueLayer transactions
        from mcp.apple_matcher_truelayer import match_all_apple_transactions
        match_results = match_all_apple_transactions()

        return jsonify({
            'success': True,
            'transactions_imported': imported,
            'transactions_duplicated': duplicates,
            'matching_results': match_results,
            'filename': filename
        }), 201

    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


# Browser-based Apple Import Endpoints
# ----------------------------------------------------------------------------

@app.route('/api/apple/import/browser-start', methods=['POST'])
def start_apple_browser_import():
    """Start a browser session for Apple import.

    Launches a visible Chromium browser navigated to Apple's Report a Problem page.
    User must log in manually with their Apple ID and 2FA.
    """
    from mcp.apple_browser_import import AppleBrowserSession
    try:
        AppleBrowserSession.start_session()
        return jsonify({
            'success': True,
            'status': 'ready',
            'message': 'Browser launched. Log in to your Apple ID and navigate to your purchase history.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/apple/import/browser-status', methods=['GET'])
def get_apple_browser_status():
    """Get current browser session status."""
    from mcp.apple_browser_import import AppleBrowserSession
    return jsonify(AppleBrowserSession.get_status())


@app.route('/api/apple/import/browser-capture', methods=['POST'])
def capture_apple_browser():
    """Capture HTML from browser and import transactions.

    Auto-scrolls the page to load all transactions (stops when finding
    transactions already in database), then captures HTML, parses it,
    imports to database, and runs matching.
    """
    from mcp.apple_browser_import import AppleBrowserSession
    from mcp.apple_parser import parse_apple_html_content

    try:
        # Get known order_ids for stop condition during scrolling
        known_order_ids = database.get_apple_order_ids()
        print(f"[Apple Import] Found {len(known_order_ids)} existing Apple order_ids in database")

        # Auto-scroll to load all transactions, then capture HTML
        html_content = AppleBrowserSession.scroll_and_capture(known_order_ids)

        # Parse HTML content
        transactions = parse_apple_html_content(html_content)

        if not transactions:
            return jsonify({'error': 'No transactions found in page. Make sure your purchase history is visible.'}), 400

        # Import to database
        imported, duplicates = database.import_apple_transactions(transactions, 'browser-import')

        # Run matching with TrueLayer transactions
        from mcp.apple_matcher_truelayer import match_all_apple_transactions
        match_results = match_all_apple_transactions()

        return jsonify({
            'success': True,
            'transactions_imported': imported,
            'transactions_duplicated': duplicates,
            'matching_results': match_results,
            'source': 'browser-import'
        })

    except Exception as e:
        return jsonify({'error': f'Capture failed: {str(e)}'}), 500


@app.route('/api/apple/import/browser-cancel', methods=['POST'])
def cancel_apple_browser():
    """Cancel the current browser session."""
    from mcp.apple_browser_import import AppleBrowserSession
    try:
        AppleBrowserSession.cancel_session()
        return jsonify({'success': True, 'message': 'Browser session cancelled'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apple', methods=['GET'])
def get_apple_transactions():
    """Get all Apple transactions."""
    try:
        transactions = database.get_apple_transactions()

        return jsonify({
            'transactions': transactions,
            'count': len(transactions)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apple/statistics', methods=['GET'])
def get_apple_stats():
    """Get Apple transactions statistics."""
    try:
        stats = database.get_apple_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apple/match', methods=['POST'])
def run_apple_matching():
    """Run or re-run Apple transaction matching (TrueLayer only).

    Query params:
        async: If 'true', runs matching as async Celery task and returns job_id
    """
    try:
        async_mode = request.args.get('async', 'true').lower() == 'true'
        user_id = int(request.args.get('user_id', 1))

        if async_mode:
            # Create job entry and dispatch Celery task
            from tasks.matching_tasks import match_apple_transactions_task

            job_id = database.create_matching_job(user_id, 'apple')
            task = match_apple_transactions_task.delay(job_id, user_id)

            # Update job with celery task ID
            database.update_matching_job_status(job_id, 'queued')

            return jsonify({
                'success': True,
                'async': True,
                'job_id': job_id,
                'celery_task_id': task.id,
                'status': 'queued'
            })
        else:
            # Sync mode for backward compatibility
            from mcp.apple_matcher_truelayer import match_all_apple_transactions
            results = match_all_apple_transactions()

            return jsonify({
                'success': True,
                'async': False,
                'results': results
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apple', methods=['DELETE'])
def clear_apple_data():
    """Clear all Apple transactions (for testing/reimporting)."""
    try:
        transactions_deleted = database.clear_apple_transactions()

        return jsonify({
            'success': True,
            'transactions_deleted': transactions_deleted,
            'message': f'Cleared {transactions_deleted} Apple transactions'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apple/files', methods=['GET'])
def list_apple_files():
    """List available Apple HTML files in the sample folder."""
    try:
        from mcp.apple_parser import get_apple_html_files
        files = get_apple_html_files('../sample')

        # Get just the filenames
        import os
        file_list = [{'filename': os.path.basename(f), 'path': f} for f in files]

        return jsonify({
            'files': file_list,
            'count': len(file_list)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apple/export-csv', methods=['POST'])
def export_apple_to_csv():
    """Convert Apple HTML to CSV format."""
    try:
        data = request.json

        if 'filename' not in data:
            return jsonify({'error': 'Missing filename'}), 400

        filename = data['filename']
        file_path = os.path.join('..', 'sample', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {filename}'}), 404

        # Parse HTML file
        from mcp.apple_parser import parse_apple_html, export_to_csv
        transactions = parse_apple_html(file_path)

        if not transactions:
            return jsonify({'error': 'No transactions found in HTML file'}), 400

        # Generate CSV filename
        csv_filename = filename.replace('.html', '.csv')
        csv_path = os.path.join('..', 'sample', csv_filename)

        # Export to CSV
        export_to_csv(transactions, csv_path)

        return jsonify({
            'success': True,
            'csv_filename': csv_filename,
            'transactions_count': len(transactions),
            'message': f'Exported {len(transactions)} transactions to {csv_filename}'
        })

    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500


# ============================================================================
# TrueLayer Bank Integration Routes
# ============================================================================

@app.route('/api/truelayer/authorize', methods=['GET'])
def truelayer_authorize():
    """Initiate TrueLayer OAuth authorization flow."""
    try:
        from mcp.truelayer_auth import get_authorization_url

        user_id = request.args.get('user_id', 1)  # In production, get from session

        auth_data = get_authorization_url(user_id)

        # Store PKCE values in database temporarily for callback verification
        database.store_oauth_state(
            user_id=user_id,
            state=auth_data['state'],
            code_verifier=auth_data['code_verifier']
        )

        return jsonify({
            'auth_url': auth_data['auth_url'],
            'state': auth_data['state'],
            'code_verifier': auth_data['code_verifier']  # Still return to frontend for sessionStorage
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/callback', methods=['GET'])
def truelayer_callback():
    """Handle TrueLayer OAuth callback."""
    try:
        from mcp.truelayer_auth import exchange_code_for_token, save_bank_connection, discover_and_save_accounts
        from flask import redirect

        code = request.args.get('code')
        state = request.args.get('state')

        if not code or not state:
            return redirect(f'{FRONTEND_URL}/auth/callback?error=Missing+code+or+state')

        # Try to get code_verifier from query params (frontend sessionStorage)
        code_verifier = request.args.get('code_verifier')

        # If not in query params, retrieve from database
        if not code_verifier:
            oauth_state = database.get_oauth_state(state)
            if not oauth_state:
                return redirect(f'{FRONTEND_URL}/auth/callback?error=Invalid+state+parameter')
            code_verifier = oauth_state.get('code_verifier')
            user_id = int(oauth_state.get('user_id'))
        else:
            user_id = int(request.args.get('user_id', 1))

        if not code_verifier:
            return redirect(f'{FRONTEND_URL}/auth/callback?error=Missing+code_verifier')

        print(f"🔐 TrueLayer OAuth Callback:")
        print(f"   User ID: {user_id}")
        print(f"   State: {state[:20]}...")
        print(f"   Code: {code[:20]}...")

        # Exchange code for token
        token_data = exchange_code_for_token(code, code_verifier)
        print(f"   ✅ Token exchanged: {token_data.get('access_token', 'N/A')[:20]}...")

        # Save connection to database
        connection_info = save_bank_connection(user_id, token_data)
        print(f"   ✅ Connection saved: ID={connection_info.get('connection_id')}")

        # Discover and save accounts from TrueLayer
        try:
            account_discovery = discover_and_save_accounts(
                connection_info['connection_id'],
                token_data['access_token']
            )
            print(f"   ✅ Accounts discovered: {account_discovery['accounts_discovered']} found, {account_discovery['accounts_saved']} saved")
        except Exception as acc_error:
            print(f"   ⚠️  Account discovery failed (non-fatal): {acc_error}")

        # Clean up stored OAuth state
        database.delete_oauth_state(state)

        # Redirect to frontend success page with connection info
        return redirect(f'{FRONTEND_URL}/auth/callback?status=authorized&connection_id={connection_info.get("connection_id")}')

    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        import traceback
        traceback.print_exc()
        # Sanitize error message for URL (remove newlines and special chars)
        error_msg = str(e).split('\n')[0].replace(' ', '+').replace('\n', '')
        return redirect(f'{FRONTEND_URL}/auth/callback?error={error_msg}')


@app.route('/api/truelayer/accounts', methods=['GET'])
def get_truelayer_accounts():
    """Get list of connected TrueLayer accounts."""
    try:
        user_id = int(request.args.get('user_id', 1))

        # Get all connections for user
        import sys
        connections = database.get_user_connections(user_id)
        sys.stderr.write(f"📊 TrueLayer accounts query for user {user_id}: {len(connections) if connections else 0} connections\n")
        sys.stderr.flush()

        # Format connections with their accounts
        formatted_connections = []
        for connection in connections:
            connection_id = connection.get('id')
            sys.stderr.write(f"   Connection ID: {connection_id}, Status: {connection.get('connection_status')}\n")
            sys.stderr.flush()
            conn_accounts = database.get_connection_accounts(connection_id)
            sys.stderr.write(f"   Found {len(conn_accounts) if conn_accounts else 0} accounts\n")
            sys.stderr.flush()

            accounts = []
            for account in conn_accounts:
                accounts.append({
                    'id': account.get('id'),
                    'account_id': account.get('account_id'),
                    'display_name': account.get('display_name'),
                    'account_type': account.get('account_type'),
                    'currency': account.get('currency'),
                    'last_synced_at': account.get('last_synced_at'),
                })

            # Use provider_name from DB, but fall back to formatted provider_id if it's missing or 'TrueLayer'
            provider_name = connection.get('provider_name')
            if not provider_name or provider_name == 'TrueLayer':
                provider_name = connection.get('provider_id', '').replace('_', ' ').title()

            formatted_connections.append({
                'id': connection_id,
                'provider_id': connection.get('provider_id'),
                'provider_name': provider_name,
                'connection_status': connection.get('connection_status'),
                'last_synced_at': connection.get('last_synced_at'),
                'accounts': accounts,
            })

        return jsonify({'connections': formatted_connections})

    except Exception as e:
        print(f"❌ Error in get_truelayer_accounts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/discover-accounts', methods=['POST'])
def discover_truelayer_accounts():
    """Discover and sync accounts for a specific connection."""
    try:
        from mcp.truelayer_auth import discover_and_save_accounts
        from mcp.truelayer_auth import decrypt_token

        data = request.json
        connection_id = data.get('connection_id')

        if not connection_id:
            return jsonify({'error': 'connection_id required'}), 400

        # Get connection from database
        connection = database.get_connection(connection_id)
        if not connection:
            return jsonify({'error': 'Connection not found'}), 404

        # Decrypt access token
        access_token = decrypt_token(connection.get('access_token'))

        # Discover and save accounts
        result = discover_and_save_accounts(connection_id, access_token)

        print(f"✅ Account discovery complete: {result['accounts_discovered']} discovered, {result['accounts_saved']} saved")

        return jsonify({
            'status': 'success',
            'accounts_discovered': result['accounts_discovered'],
            'accounts_saved': result['accounts_saved'],
            'accounts': result['accounts']
        })

    except Exception as e:
        print(f"❌ Error in discover_truelayer_accounts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/sync', methods=['POST'])
def sync_truelayer_transactions():
    """Trigger manual sync of TrueLayer transactions."""
    try:
        from mcp.truelayer_sync import sync_all_accounts

        print(f"🔄 Starting TrueLayer sync...")
        data = request.json or {}

        # Support both user_id and connection_id
        user_id = data.get('user_id')
        connection_id = data.get('connection_id')

        # If connection_id provided, get user_id from connection
        if connection_id and not user_id:
            connection = database.get_connection(connection_id)
            if connection:
                user_id = connection.get('user_id')
                print(f"   📍 Found user_id {user_id} from connection {connection_id}")

        # Default to user 1 if still not found
        if not user_id:
            user_id = 1
            print(f"   📍 Using default user_id: {user_id}")

        # Sync all accounts for user
        print(f"   🔄 Syncing all accounts for user {user_id}...")
        result = sync_all_accounts(user_id)

        # Calculate totals
        total_synced = sum(acc.get('synced', 0) for acc in result.get('accounts', []))
        total_duplicates = sum(acc.get('duplicates', 0) for acc in result.get('accounts', []))
        total_errors = sum(acc.get('errors', 0) for acc in result.get('accounts', []))

        print(f"✅ Sync completed: {total_synced} synced, {total_duplicates} duplicates, {total_errors} errors")

        # Invalidate transaction caches (new transactions imported)
        cache_manager.cache_invalidate_transactions()

        response = {
            'status': 'completed',
            'summary': {
                'total_accounts': result.get('total_accounts', 0),
                'total_synced': total_synced,
                'total_duplicates': total_duplicates,
                'total_errors': total_errors,
            },
            'result': result
        }

        return jsonify(response)

    except Exception as e:
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


@app.route('/api/truelayer/sync/status', methods=['GET'])
def get_sync_status():
    """Get sync status for all accounts."""
    try:
        from mcp.truelayer_sync import get_sync_status

        user_id = request.args.get('user_id', 1)

        status = get_sync_status(user_id)

        return jsonify(status)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/disconnect', methods=['POST'])
def disconnect_bank_account():
    """Disconnect a TrueLayer bank account."""
    try:
        data = request.json
        connection_id = data.get('connection_id')

        if not connection_id:
            return jsonify({'error': 'Missing connection_id'}), 400

        # Mark connection as inactive
        database.update_connection_status(connection_id, 'inactive')

        return jsonify({
            'status': 'disconnected',
            'connection_id': connection_id
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/clear-transactions', methods=['DELETE'])
def clear_truelayer_transactions():
    """Clear all TrueLayer transactions from database (for testing)."""
    try:
        # Check confirmation header
        confirmation = request.headers.get('X-Confirm-Delete', '').lower()
        if confirmation != 'yes':
            return jsonify({'error': 'Deletion not confirmed'}), 400

        # Delete TrueLayer transactions
        with database.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('DELETE FROM truelayer_transactions')
                conn.commit()
                deleted_count = cursor.rowcount
                cursor.close()

        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} TrueLayer transaction(s)',
            'deleted_count': deleted_count
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/fetch-accounts', methods=['POST'])
def fetch_truelayer_accounts_on_demand():
    """On-demand fetch of TrueLayer account transactions."""
    try:
        from mcp.truelayer_sync import sync_all_accounts

        data = request.json

        # Support both user_id and connection_id
        user_id = data.get('user_id')
        connection_id = data.get('connection_id')

        # If connection_id provided, get user_id from connection
        if connection_id and not user_id:
            connection = database.get_connection(connection_id)
            if connection:
                user_id = connection.get('user_id')

        # Default to user 1 if still not found
        if not user_id:
            user_id = 1

        # Sync all accounts for user
        result = sync_all_accounts(user_id)

        return jsonify({
            'status': 'completed',
            'result': result
        })

    except Exception as e:
        print(f"❌ Account fetch error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/fetch-cards', methods=['POST'])
def fetch_truelayer_cards_on_demand():
    """On-demand fetch of TrueLayer card transactions."""
    try:
        from mcp.truelayer_sync import sync_all_cards

        data = request.json

        # Support both user_id and connection_id
        user_id = data.get('user_id')
        connection_id = data.get('connection_id')

        # If connection_id provided, get user_id from connection
        if connection_id and not user_id:
            connection = database.get_connection(connection_id)
            if connection:
                user_id = connection.get('user_id')

        # Default to user 1 if still not found
        if not user_id:
            user_id = 1

        # Sync all cards for user
        result = sync_all_cards(user_id)

        return jsonify({
            'status': 'completed',
            'result': result
        })

    except Exception as e:
        print(f"❌ Card fetch error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/cards', methods=['GET'])
def get_truelayer_cards():
    """Get all connected TrueLayer cards for a user."""
    try:
        user_id = request.args.get('user_id', 1, type=int)

        # Get all active connections for user
        connections = database.get_user_connections(user_id)

        if not connections:
            return jsonify({
                'user_id': user_id,
                'connections': []
            })

        connections_data = []
        for connection in connections:
            connection_id = connection.get('id')
            cards = database.get_connection_cards(connection_id)

            connections_data.append({
                'connection_id': connection_id,
                'provider_id': connection.get('provider_id'),
                'connection_status': connection.get('connection_status'),
                'last_synced_at': connection.get('last_synced_at'),
                'cards': cards if cards else []
            })

        return jsonify({
            'user_id': user_id,
            'connections': connections_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/fetch-transactions', methods=['POST'])
def fetch_transactions_on_demand():
    """On-demand fetch of transactions for a specific account or card."""
    try:
        from mcp.truelayer_auth import decrypt_token
        from mcp.truelayer_client import TrueLayerClient

        data = request.json
        account_id = data.get('account_id')
        card_id = data.get('card_id')
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        if not account_id and not card_id:
            return jsonify({'error': 'Must provide either account_id or card_id'}), 400

        # If account_id provided
        if account_id:
            account = database.get_account_by_truelayer_id(account_id)
            if not account:
                return jsonify({'error': f'Account {account_id} not found'}), 404

            db_account_id = account.get('id')
            connection_id = account.get('connection_id')
            connection = database.get_connection(connection_id)
            access_token = decrypt_token(connection.get('access_token'))

            client = TrueLayerClient(access_token)
            transactions = client.get_transactions(account_id, from_date, to_date)

            # Normalize transactions
            normalized = [client.normalize_transaction(txn) for txn in transactions]

            # Count existing transactions
            synced_count = 0
            duplicate_count = 0
            for txn in normalized:
                existing = database.get_truelayer_transaction_by_id(txn.get('normalised_provider_id'))
                if not existing:
                    synced_count += 1
                else:
                    duplicate_count += 1

            return jsonify({
                'status': 'completed',
                'account_id': account_id,
                'total_transactions': len(transactions),
                'synced': synced_count,
                'duplicates': duplicate_count,
                'transactions': transactions
            })

        # If card_id provided
        elif card_id:
            card = database.get_card_by_truelayer_id(card_id)
            if not card:
                return jsonify({'error': f'Card {card_id} not found'}), 404

            db_card_id = card.get('id')
            connection_id = card.get('connection_id')
            connection = database.get_connection(connection_id)
            access_token = decrypt_token(connection.get('access_token'))

            client = TrueLayerClient(access_token)
            transactions = client.get_card_transactions(card_id, from_date, to_date)

            # Normalize card transactions
            normalized = [client.normalize_card_transaction(txn) for txn in transactions]

            # Count existing transactions
            synced_count = 0
            duplicate_count = 0
            for txn in normalized:
                existing = database.get_card_transaction_by_id(txn.get('normalised_provider_id'))
                if not existing:
                    synced_count += 1
                else:
                    duplicate_count += 1

            return jsonify({
                'status': 'completed',
                'card_id': card_id,
                'total_transactions': len(transactions),
                'synced': synced_count,
                'duplicates': duplicate_count,
                'transactions': transactions
            })

    except Exception as e:
        print(f"❌ Transaction fetch error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/import/plan', methods=['POST'])
def plan_import():
    """Plan an import job and provide estimates."""
    try:
        from mcp.truelayer_import_manager import create_import_job

        data = request.json
        user_id = data.get('user_id', 1)
        connection_id = data.get('connection_id')
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        account_ids = data.get('account_ids', [])
        auto_enrich = data.get('auto_enrich', True)
        batch_size = data.get('batch_size', 50)

        if not connection_id:
            return jsonify({'error': 'connection_id required'}), 400
        if not from_date or not to_date:
            return jsonify({'error': 'from_date and to_date required'}), 400

        # Validate date format (handle both string and date object)
        try:
            from datetime import datetime, date
            # Convert to string if it's a date object
            if isinstance(from_date, date):
                from_date = from_date.isoformat()
            if isinstance(to_date, date):
                to_date = to_date.isoformat()
            # Validate format
            datetime.strptime(from_date, '%Y-%m-%d')
            datetime.strptime(to_date, '%Y-%m-%d')
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Invalid date format. Use YYYY-MM-DD (error: {str(e)})'}), 400

        # Create job
        job = create_import_job(
            user_id=user_id,
            connection_id=connection_id,
            from_date=from_date,
            to_date=to_date,
            account_ids=account_ids or None,
            auto_enrich=auto_enrich,
            batch_size=batch_size
        )

        # Plan import
        plan = job.plan()

        return jsonify(plan), 201

    except Exception as e:
        print(f"❌ Plan import error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/import/start', methods=['POST'])
def start_import():
    """Start an import job (executes synchronously for Phase 1)."""
    try:
        from mcp.truelayer_import_manager import ImportJob

        data = request.json
        job_id = data.get('job_id')

        if not job_id:
            return jsonify({'error': 'job_id required'}), 400

        job = ImportJob(job_id)

        # Execute import (Phase 1: synchronous, Phase 2: async via Celery)
        result = job.execute(use_parallel=True, max_workers=3)

        # Broadcast progress (Phase 2 will use WebSocket)
        print(f"✅ Import job {job_id} completed")

        return jsonify(result), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Start import error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/import/status/<int:job_id>', methods=['GET'])
def get_import_status(job_id):
    """Get current import job status and progress."""
    try:
        from mcp.truelayer_import_manager import ImportJob

        job = ImportJob(job_id)
        status = job.get_status()

        return jsonify(status), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Get import status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/truelayer/import/history', methods=['GET'])
def get_import_history():
    """Get import job history for user."""
    try:
        user_id = request.args.get('user_id', 1, type=int)
        limit = request.args.get('limit', 50, type=int)

        history = database.get_user_import_history(user_id, limit=limit)

        return jsonify({
            'user_id': user_id,
            'imports': history
        }), 200

    except Exception as e:
        print(f"❌ Get import history error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/testing/clear', methods=['POST'])
def clear_testing_data():
    """Clear selected data types for testing purposes.

    Query parameter: types (comma-separated list of data type names)
    Allowed types: truelayer_transactions, legacy_transactions, amazon_orders,
                   amazon_matches, apple_transactions, apple_matches,
                   enrichment_cache, import_history, category_rules

    Returns: JSON with success status and counts per data type
    """
    try:
        # Get and validate types parameter
        types_str = request.args.get('types', '').strip()

        if not types_str:
            return jsonify({
                'success': False,
                'error': 'No data types specified. At least one type must be selected.'
            }), 400

        # Define allowed types and their corresponding tables
        allowed_types = {
            'truelayer_transactions': 'DELETE FROM truelayer_transactions',
            'amazon_orders': 'DELETE FROM amazon_orders',
            'truelayer_amazon_matches': 'DELETE FROM truelayer_amazon_transaction_matches',
            'apple_transactions': 'DELETE FROM apple_transactions',
            'truelayer_apple_matches': 'DELETE FROM truelayer_apple_transaction_matches',
            'enrichment_cache': 'DELETE FROM llm_enrichment_cache',
            'import_history': 'DELETE FROM truelayer_import_jobs',
            'category_rules': 'DELETE FROM category_keywords'
        }

        # Parse and validate types
        types_list = [t.strip() for t in types_str.split(',') if t.strip()]

        invalid_types = [t for t in types_list if t not in allowed_types]
        if invalid_types:
            return jsonify({
                'success': False,
                'error': f"Invalid data type: {invalid_types[0]}. Allowed types: {', '.join(allowed_types.keys())}"
            }), 400

        # Execute clearing operations with fail-fast behavior
        cleared_counts = {t: 0 for t in allowed_types.keys()}

        try:
            from database_postgres import get_db

            with get_db() as conn:
                with conn.cursor() as cursor:
                    for data_type in types_list:
                        try:
                            delete_sql = allowed_types[data_type]
                            cursor.execute(delete_sql)
                            row_count = cursor.rowcount
                            cleared_counts[data_type] = row_count
                            conn.commit()

                        except Exception as e:
                            # Fail-fast: stop on first error
                            conn.rollback()
                            return jsonify({
                                'success': False,
                                'error': f"Failed to clear {data_type}: {str(e)}"
                            }), 500

            # Return success with all counts
            return jsonify({
                'success': True,
                'cleared': cleared_counts
            }), 200

        except Exception as e:
            print(f"❌ Clear testing data error: {e}")
            return jsonify({
                'success': False,
                'error': f"Error during clearing: {str(e)}"
            }), 500

    except Exception as e:
        print(f"❌ Clear testing data error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/truelayer/webhook', methods=['POST'])
def handle_truelayer_webhook():
    """Handle incoming TrueLayer webhook events."""
    try:
        from mcp.truelayer_sync import handle_webhook_event

        # In production, verify webhook signature
        # signature = request.headers.get('X-TrueLayer-Signature')
        # if not verify_webhook_signature(request.data, signature):
        #     return jsonify({'error': 'Invalid signature'}), 401

        payload = request.json

        result = handle_webhook_event(payload)

        return jsonify(result), 200

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Amazon Business API Endpoints
# ============================================================================

@app.route('/api/amazon-business/authorize', methods=['GET'])
def amazon_business_authorize():
    """Start Amazon Business OAuth flow.

    Returns authorization URL and state token.
    """
    try:
        from mcp.amazon_business_auth import get_authorization_url

        result = get_authorization_url()

        return jsonify({
            'success': True,
            'authorization_url': result['authorization_url'],
            'state': result['state']
        })

    except ValueError as e:
        # Missing credentials
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Amazon Business API credentials not configured'
        }), 400
    except Exception as e:
        print(f"❌ Amazon Business authorize error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/amazon-business/callback', methods=['POST'])
def amazon_business_callback():
    """Handle Amazon Business OAuth callback.

    Expects JSON body with 'code' from OAuth redirect.
    """
    try:
        from mcp.amazon_business_auth import exchange_code_for_tokens

        data = request.json
        code = data.get('code')

        if not code:
            return jsonify({'success': False, 'error': 'Authorization code required'}), 400

        # Exchange code for tokens
        tokens = exchange_code_for_tokens(code)

        # Save connection to database
        region = data.get('region', 'UK')
        connection_id = database.save_amazon_business_connection(
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            expires_in=tokens['expires_in'],
            region=region
        )

        return jsonify({
            'success': True,
            'connection_id': connection_id,
            'message': 'Amazon Business connected successfully'
        })

    except Exception as e:
        print(f"❌ Amazon Business callback error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/amazon-business/connection', methods=['GET'])
def get_amazon_business_connection_status():
    """Get Amazon Business connection status."""
    try:
        conn = database.get_amazon_business_connection()

        if conn:
            return jsonify({
                'connected': True,
                'connection_id': conn['id'],
                'region': conn['region'],
                'status': conn['status'],
                'created_at': conn['created_at'].isoformat() if conn['created_at'] else None
            })
        else:
            return jsonify({
                'connected': False,
                'status': None
            })

    except Exception as e:
        print(f"❌ Amazon Business connection status error: {e}")
        return jsonify({'connected': False, 'error': str(e)}), 500


@app.route('/api/amazon-business/disconnect', methods=['POST'])
def disconnect_amazon_business():
    """Disconnect Amazon Business account."""
    try:
        conn = database.get_amazon_business_connection()

        if not conn:
            return jsonify({'success': False, 'error': 'No connection found'}), 404

        success = database.delete_amazon_business_connection(conn['id'])

        return jsonify({
            'success': success,
            'message': 'Amazon Business disconnected' if success else 'Failed to disconnect'
        })

    except Exception as e:
        print(f"❌ Amazon Business disconnect error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/amazon-business/import', methods=['POST'])
def import_amazon_business():
    """Import orders from Amazon Business API.

    Expects JSON body with:
    - start_date: YYYY-MM-DD format
    - end_date: YYYY-MM-DD format
    - run_matching: bool (optional, default True)
    """
    try:
        from mcp.amazon_business_client import import_orders_for_date_range
        from mcp.amazon_business_matcher import match_all_amazon_business_transactions

        data = request.json
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        run_matching = data.get('run_matching', True)

        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'error': 'start_date and end_date required'
            }), 400

        # Import from API
        import_results = import_orders_for_date_range(start_date, end_date)

        # Run matching if requested
        matching_results = None
        if run_matching:
            matching_results = match_all_amazon_business_transactions()

        return jsonify({
            'success': True,
            'import': import_results,
            'matching': matching_results
        })

    except ValueError as e:
        # No connection found
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Please connect Amazon Business first'
        }), 400
    except Exception as e:
        print(f"❌ Amazon Business import error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/amazon-business/statistics', methods=['GET'])
def amazon_business_statistics():
    """Get Amazon Business import and matching statistics."""
    try:
        stats = database.get_amazon_business_statistics()
        return jsonify(stats)
    except Exception as e:
        print(f"❌ Amazon Business statistics error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon-business/orders', methods=['GET'])
def get_amazon_business_orders_endpoint():
    """Get Amazon Business orders with optional date filtering."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        orders = database.get_amazon_business_orders(
            date_from=date_from,
            date_to=date_to
        )

        # Convert Decimal values for JSON serialization
        for order in orders:
            for key in ['subtotal', 'tax', 'shipping', 'net_total']:
                if order.get(key) is not None:
                    order[key] = float(order[key])
            if order.get('order_date'):
                order['order_date'] = order['order_date'].isoformat()
            if order.get('created_at'):
                order['created_at'] = order['created_at'].isoformat()

        return jsonify(orders)

    except Exception as e:
        print(f"❌ Amazon Business orders error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon-business/match', methods=['POST'])
def run_amazon_business_matching():
    """Run matching for Amazon Business transactions."""
    try:
        from mcp.amazon_business_matcher import match_all_amazon_business_transactions

        results = match_all_amazon_business_transactions()

        return jsonify({
            'success': True,
            'results': results
        })

    except Exception as e:
        print(f"❌ Amazon Business matching error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/amazon-business/clear', methods=['POST'])
def clear_amazon_business_data():
    """Clear all Amazon Business data (for testing/reset)."""
    try:
        results = database.clear_amazon_business_data()

        return jsonify({
            'success': True,
            'deleted': results
        })

    except Exception as e:
        print(f"❌ Amazon Business clear error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# GMAIL RECEIPT INTEGRATION ENDPOINTS
# =============================================================================


@app.route('/api/gmail/authorize', methods=['GET'])
def gmail_authorize():
    """Initiate Gmail OAuth authorization flow."""
    try:
        from mcp.gmail_auth import get_authorization_url

        user_id = int(request.args.get('user_id', 1))

        auth_data = get_authorization_url(user_id)

        # Store PKCE values in database temporarily for callback verification
        database.store_gmail_oauth_state(
            user_id=user_id,
            state=auth_data['state'],
            code_verifier=auth_data['code_verifier']
        )

        return jsonify({
            'auth_url': auth_data['auth_url'],
            'state': auth_data['state'],
            'code_verifier': auth_data['code_verifier']  # Return to frontend for sessionStorage backup
        })
    except ValueError as e:
        return jsonify({'error': str(e), 'error_type': 'configuration'}), 400
    except Exception as e:
        print(f"❌ Gmail authorize error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/callback', methods=['GET'])
def gmail_callback():
    """Handle Gmail OAuth callback."""
    try:
        from mcp.gmail_auth import (
            exchange_code_for_token,
            save_gmail_connection,
            get_gmail_user_email
        )
        from flask import redirect

        code = request.args.get('code')
        state = request.args.get('state')

        if not code or not state:
            return redirect(f'{FRONTEND_URL}/auth/gmail/callback?error=Missing+code+or+state')

        # Try to get code_verifier from query params (frontend sessionStorage)
        code_verifier = request.args.get('code_verifier')

        # If not in query params, retrieve from database
        if not code_verifier:
            oauth_state = database.get_gmail_oauth_state(state)
            if not oauth_state:
                return redirect(f'{FRONTEND_URL}/auth/gmail/callback?error=Invalid+state+parameter')
            code_verifier = oauth_state.get('code_verifier')
            user_id = int(oauth_state.get('user_id'))
        else:
            user_id = int(request.args.get('user_id', 1))

        if not code_verifier:
            return redirect(f'{FRONTEND_URL}/auth/gmail/callback?error=Missing+code_verifier')

        print(f"📧 Gmail OAuth Callback:")
        print(f"   User ID: {user_id}")
        print(f"   State: {state[:20]}...")
        print(f"   Code: {code[:20]}...")

        # Exchange code for token
        token_data = exchange_code_for_token(code, code_verifier)
        print(f"   ✅ Token exchanged successfully")

        # Get user's email address from Gmail API
        email_address = get_gmail_user_email(token_data['access_token'])

        # Save connection to database
        connection_info = save_gmail_connection(user_id, email_address, token_data)
        print(f"   ✅ Gmail connection saved: ID={connection_info.get('connection_id')}")

        # Clean up stored OAuth state
        database.delete_gmail_oauth_state(state)

        # Redirect to frontend success page
        return redirect(f'{FRONTEND_URL}/auth/gmail/callback?status=authorized&connection_id={connection_info.get("connection_id")}&email={email_address}')

    except Exception as e:
        print(f"❌ Gmail OAuth callback error: {e}")
        import traceback
        traceback.print_exc()
        error_msg = str(e).split('\n')[0].replace(' ', '+').replace('\n', '')
        return redirect(f'{FRONTEND_URL}/auth/gmail/callback?error={error_msg}')


@app.route('/api/gmail/connection', methods=['GET'])
def get_gmail_connection():
    """Get Gmail connection status for a user."""
    try:
        user_id = int(request.args.get('user_id', 1))

        connection = database.get_gmail_connection(user_id)

        if not connection:
            return jsonify({
                'connected': False,
                'connection': None,
                'statistics': None
            })

        # Get statistics for this user
        stats = database.get_gmail_statistics(user_id)

        # Don't return tokens to frontend
        return jsonify({
            'connected': True,
            'connection': {
                'id': connection.get('id'),
                'email_address': connection.get('email_address'),
                'connection_status': connection.get('connection_status'),
                'last_synced_at': connection.get('last_synced_at'),
                'sync_from_date': connection.get('sync_from_date'),
                'created_at': connection.get('created_at'),
            },
            'statistics': stats
        })

    except Exception as e:
        print(f"❌ Gmail connection status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/disconnect', methods=['POST'])
def disconnect_gmail():
    """Disconnect Gmail account and delete all associated data."""
    try:
        from mcp.gmail_auth import disconnect_gmail as do_disconnect

        data = request.json or {}
        connection_id = data.get('connection_id')
        user_id = int(data.get('user_id', 1))

        if not connection_id:
            return jsonify({'error': 'connection_id required'}), 400

        result = do_disconnect(connection_id, user_id)

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Gmail disconnect error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/statistics', methods=['GET'])
def get_gmail_statistics():
    """Get Gmail receipt statistics for a user."""
    try:
        user_id = int(request.args.get('user_id', 1))

        stats = database.get_gmail_statistics(user_id)

        return jsonify(stats)

    except Exception as e:
        print(f"❌ Gmail statistics error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/receipts', methods=['GET'])
def get_gmail_receipts():
    """Get paginated list of Gmail receipts."""
    try:
        user_id = int(request.args.get('user_id', 1))
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        status = request.args.get('status')  # Optional filter: pending, parsed, matched

        # Get connection for user
        connection = database.get_gmail_connection(user_id)
        if not connection:
            return jsonify({
                'receipts': [],
                'total': 0,
                'message': 'No Gmail connection found'
            })

        receipts = database.get_gmail_receipts(
            connection_id=connection['id'],
            limit=limit,
            offset=offset,
            status=status
        )

        return jsonify({
            'receipts': receipts,
            'total': len(receipts),
            'limit': limit,
            'offset': offset
        })

    except Exception as e:
        print(f"❌ Gmail receipts error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/receipts/<int:receipt_id>', methods=['GET'])
def get_gmail_receipt(receipt_id):
    """Get a single Gmail receipt with full details."""
    try:
        receipt = database.get_gmail_receipt_by_id(receipt_id)

        if not receipt:
            return jsonify({'error': 'Receipt not found'}), 404

        return jsonify(receipt)

    except Exception as e:
        print(f"❌ Gmail receipt error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/receipts/<int:receipt_id>', methods=['DELETE'])
def delete_gmail_receipt(receipt_id):
    """Soft delete a Gmail receipt."""
    try:
        success = database.soft_delete_gmail_receipt(receipt_id)

        if not success:
            return jsonify({'error': 'Receipt not found or already deleted'}), 404

        return jsonify({'status': 'deleted', 'receipt_id': receipt_id})

    except Exception as e:
        print(f"❌ Gmail receipt delete error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/matches', methods=['GET'])
def get_gmail_matches():
    """Get Gmail receipt to transaction matches."""
    try:
        user_id = int(request.args.get('user_id', 1))
        unconfirmed_only = request.args.get('unconfirmed_only', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Get connection for user
        connection = database.get_gmail_connection(user_id)
        if not connection:
            return jsonify({
                'matches': [],
                'total': 0,
                'message': 'No Gmail connection found'
            })

        matches = database.get_gmail_matches(
            connection_id=connection['id'],
            unconfirmed_only=unconfirmed_only,
            limit=limit,
            offset=offset
        )

        return jsonify({
            'matches': matches,
            'total': len(matches),
            'limit': limit,
            'offset': offset
        })

    except Exception as e:
        print(f"❌ Gmail matches error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/matches/<int:match_id>/confirm', methods=['POST'])
def confirm_gmail_match(match_id):
    """Confirm a Gmail receipt match."""
    try:
        success = database.confirm_gmail_match(match_id)

        if not success:
            return jsonify({'error': 'Match not found'}), 404

        return jsonify({'status': 'confirmed', 'match_id': match_id})

    except Exception as e:
        print(f"❌ Gmail match confirm error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/matches/<int:match_id>', methods=['DELETE'])
def delete_gmail_match(match_id):
    """Delete a Gmail receipt match."""
    try:
        success = database.delete_gmail_match(match_id)

        if not success:
            return jsonify({'error': 'Match not found'}), 404

        return jsonify({'status': 'deleted', 'match_id': match_id})

    except Exception as e:
        print(f"❌ Gmail match delete error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/sync', methods=['POST'])
def start_gmail_sync():
    """Start a Gmail receipt sync job asynchronously."""
    try:
        from tasks.gmail_tasks import sync_gmail_receipts_task

        data = request.json or {}
        user_id = int(data.get('user_id', 1))
        sync_type = data.get('sync_type', 'full')  # 'full' or 'incremental'
        from_date_str = data.get('from_date')  # ISO format: 'YYYY-MM-DD'
        to_date_str = data.get('to_date')      # ISO format: 'YYYY-MM-DD'

        # Get connection for user
        connection = database.get_gmail_connection(user_id)
        if not connection:
            return jsonify({'error': 'No Gmail connection found'}), 404

        connection_id = connection['id']

        # Create job record first for tracking
        job_id = database.create_gmail_sync_job(connection_id, job_type=sync_type)

        # Store date range in job if provided
        if from_date_str or to_date_str:
            database.update_gmail_sync_job_dates(job_id, from_date_str, to_date_str)

        # Dispatch async task
        sync_gmail_receipts_task.delay(
            connection_id,
            sync_type,
            job_id,
            from_date_str,
            to_date_str
        )

        print(f"📧 Gmail sync queued: job_id={job_id}, type={sync_type}, dates={from_date_str} to {to_date_str}")

        return jsonify({
            'job_id': job_id,
            'status': 'queued',
            'sync_type': sync_type,
            'from_date': from_date_str,
            'to_date': to_date_str,
            'connection_id': connection_id,
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Gmail sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/sync/status', methods=['GET'])
def get_gmail_sync_status():
    """Get Gmail sync status for a user."""
    try:
        from mcp.gmail_sync import get_sync_status

        user_id = int(request.args.get('user_id', 1))

        # Get connection for user
        connection = database.get_gmail_connection(user_id)
        if not connection:
            return jsonify({
                'connected': False,
                'message': 'No Gmail connection found'
            })

        status = get_sync_status(connection['id'])

        return jsonify(status)

    except Exception as e:
        print(f"❌ Gmail sync status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/sync/<int:job_id>', methods=['GET'])
def get_gmail_sync_job_status(job_id):
    """Get status of a specific sync job."""
    try:
        # Clean up any stale jobs before checking status
        # This ensures orphaned jobs from worker restarts are marked as failed
        stale_count = database.cleanup_stale_gmail_jobs()
        if stale_count > 0:
            print(f"🧹 Cleaned up {stale_count} stale Gmail sync job(s)")

        job = database.get_gmail_sync_job(job_id)

        if not job:
            return jsonify({'error': 'Sync job not found'}), 404

        return jsonify(job)

    except Exception as e:
        print(f"❌ Gmail sync job status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/parse', methods=['POST'])
def parse_gmail_receipts():
    """Parse pending receipts for a user."""
    try:
        from mcp.gmail_parser import parse_pending_receipts

        data = request.json or {}
        user_id = int(data.get('user_id', 1))
        limit = int(data.get('limit', 100))

        # Get connection for user
        connection = database.get_gmail_connection(user_id)
        if not connection:
            return jsonify({'error': 'No Gmail connection found'}), 404

        # Parse pending receipts
        result = parse_pending_receipts(connection['id'], limit)

        return jsonify(result)

    except Exception as e:
        print(f"❌ Gmail parse error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/parse/<int:receipt_id>', methods=['POST'])
def parse_single_gmail_receipt(receipt_id):
    """Parse a single receipt."""
    try:
        from mcp.gmail_parser import parse_receipt

        result = parse_receipt(receipt_id)

        if result.get('error'):
            return jsonify(result), 404

        return jsonify(result)

    except Exception as e:
        print(f"❌ Gmail parse single error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/match', methods=['POST'])
def match_gmail_receipts():
    """Match parsed receipts to transactions."""
    try:
        from mcp.gmail_matcher import match_all_gmail_receipts

        data = request.get_json(silent=True) or {}
        user_id = int(data.get('user_id', 1))

        result = match_all_gmail_receipts(user_id)

        return jsonify(result)

    except Exception as e:
        print(f"❌ Gmail match error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/match/<int:receipt_id>', methods=['POST'])
def match_single_gmail_receipt(receipt_id):
    """Find matching transactions for a single receipt."""
    try:
        from mcp.gmail_matcher import match_single_receipt

        data = request.json or {}
        user_id = int(data.get('user_id', 1))

        result = match_single_receipt(receipt_id, user_id)

        if result.get('error'):
            return jsonify(result), 400

        return jsonify(result)

    except Exception as e:
        print(f"❌ Gmail match single error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/match/suggestions', methods=['GET'])
def get_gmail_match_suggestions():
    """Get low-confidence matches needing user confirmation."""
    try:
        from mcp.gmail_matcher import get_match_suggestions

        user_id = int(request.args.get('user_id', 1))
        limit = int(request.args.get('limit', 50))

        suggestions = get_match_suggestions(user_id, limit)

        return jsonify({
            'suggestions': suggestions,
            'total': len(suggestions)
        })

    except Exception as e:
        print(f"❌ Gmail suggestions error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GMAIL MERCHANTS AGGREGATION ENDPOINTS
# ============================================================================

@app.route('/api/gmail/merchants', methods=['GET'])
def get_gmail_merchants():
    """
    Get aggregated Gmail merchant statistics.

    Returns merchants grouped by sender domain with:
    - Receipt counts (total, parsed, matched, pending, failed)
    - Template availability (has_template, template_type)
    - Potential transaction matches (unmatched bank txns with same merchant)
    - Alternative source coverage (Amazon/Apple)
    """
    try:
        user_id = int(request.args.get('user_id', 1))

        result = database.get_gmail_merchants_summary(user_id)

        return jsonify(result)

    except Exception as e:
        print(f"❌ Gmail merchants error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/merchants/<path:identifier>/receipts', methods=['GET'])
def get_merchant_receipts(identifier):
    """
    Get all receipts for a specific merchant.

    The identifier can be either:
    - A domain (contains '.') e.g., "amazon.co.uk"
    - A normalized name (no '.') e.g., "amazon_business", "amazon_fresh"

    Path params:
        identifier: URL-encoded merchant domain or normalized name

    Query params:
        user_id: User ID (default: 1)
        limit: Max receipts (default: 50)
        offset: Pagination offset (default: 0)
        status: Filter by parsing_status
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        status = request.args.get('status')

        # Auto-detect: if contains '.', treat as domain; otherwise as normalized name
        if '.' in identifier:
            result = database.get_receipts_by_domain(
                merchant_domain=identifier,
                user_id=user_id,
                limit=limit,
                offset=offset,
                status=status
            )
        else:
            result = database.get_receipts_by_domain(
                merchant_normalized=identifier,
                user_id=user_id,
                limit=limit,
                offset=offset,
                status=status
            )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Merchant receipts error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/merchants/<path:domain>/enrich', methods=['POST'])
def enrich_merchant_receipts(domain):
    """
    Run LLM enrichment for pending/failed receipts from a merchant.

    This parses receipts using LLM to extract amount, date, and line items,
    then triggers matching against bank transactions.

    Request body:
        user_id: User ID (default: 1)
        force: Re-parse even if already parsed (default: false)
    """
    try:
        from mcp.gmail_parser import extract_with_llm, compute_receipt_hash
        from mcp.gmail_matcher import match_all_gmail_receipts

        data = request.json or {}
        user_id = int(data.get('user_id', 1))
        force = data.get('force', False)

        # Get receipts for this domain that need parsing
        status_filter = None if force else 'pending'
        receipts_data = database.get_receipts_by_domain(
            merchant_domain=domain,
            user_id=user_id,
            limit=100,  # Process up to 100 at a time
            status=status_filter
        )

        receipts = receipts_data.get('receipts', [])

        # If force mode, also get failed receipts
        if force:
            # Filter to only pending/failed/unparseable
            receipts = [r for r in receipts if r['parsing_status'] in ('pending', 'failed', 'unparseable')]

        if not receipts:
            return jsonify({
                'success': True,
                'processed': 0,
                'parsed': 0,
                'failed': 0,
                'message': 'No receipts to process'
            })

        # Process each receipt with LLM
        processed = 0
        parsed = 0
        failed = 0
        total_cost_cents = 0

        for receipt in receipts:
            try:
                # Get full receipt data including raw content
                full_receipt = database.get_gmail_receipt_by_id(receipt['id'])
                if not full_receipt:
                    failed += 1
                    continue

                # Extract with LLM
                raw_data = full_receipt.get('raw_schema_data') or {}
                html_body = raw_data.get('html_body', '')
                text_body = raw_data.get('text_body', '')
                subject = full_receipt.get('subject', '')

                result = extract_with_llm(html_body, text_body, subject)

                if result and result.get('merchant_name'):
                    # Calculate receipt hash for deduplication
                    receipt_hash = compute_receipt_hash(
                        merchant=result.get('merchant_name', ''),
                        amount=result.get('total_amount'),
                        date=result.get('receipt_date'),
                        order_id=result.get('order_id')
                    )

                    # Update receipt with parsed data
                    database.update_gmail_receipt_parsed(
                        receipt_id=receipt['id'],
                        merchant_name=result.get('merchant_name'),
                        merchant_name_normalized=result.get('merchant_name', '').lower().strip(),
                        order_id=result.get('order_id'),
                        total_amount=result.get('total_amount'),
                        currency_code=result.get('currency_code', 'GBP'),
                        receipt_date=result.get('receipt_date'),
                        line_items=result.get('line_items', []),
                        receipt_hash=receipt_hash,
                        parse_method='llm',
                        parse_confidence=result.get('confidence', 70),
                        parsing_status='parsed',
                        llm_cost_cents=result.get('cost_cents', 1)
                    )
                    parsed += 1
                    total_cost_cents += result.get('cost_cents', 1)
                else:
                    # Mark as failed
                    database.update_gmail_receipt_status(
                        receipt['id'],
                        'failed',
                        'LLM extraction returned no data'
                    )
                    failed += 1

                processed += 1

            except Exception as e:
                print(f"❌ LLM extraction error for receipt {receipt['id']}: {e}")
                database.update_gmail_receipt_status(
                    receipt['id'],
                    'failed',
                    str(e)
                )
                failed += 1
                processed += 1

        # After parsing, run matching to link to transactions
        if parsed > 0:
            try:
                match_all_gmail_receipts(user_id)
            except Exception as e:
                print(f"⚠️ Matching after LLM parse failed: {e}")

        return jsonify({
            'success': True,
            'processed': processed,
            'parsed': parsed,
            'failed': failed,
            'llm_cost_cents': total_cost_cents,
            'domain': domain
        })

    except Exception as e:
        print(f"❌ Merchant enrichment error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/sender-patterns', methods=['GET'])
def get_gmail_sender_patterns():
    """
    Get all registered sender patterns (templates).

    Returns list of pattern configurations showing which merchants
    have dedicated parsing templates.
    """
    try:
        patterns = database.get_gmail_sender_patterns_list()

        # Also get list of vendor parsers from the registry
        vendor_domains = []
        try:
            from mcp.gmail_vendor_parsers import VENDOR_PARSERS
            vendor_domains = list(VENDOR_PARSERS.keys())
        except ImportError:
            pass

        return jsonify({
            'patterns': patterns,
            'vendor_parsers': vendor_domains,
            'total': len(patterns)
        })

    except Exception as e:
        print(f"❌ Sender patterns error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GMAIL LLM QUEUE ENDPOINTS
# ============================================================================

@app.route('/api/gmail/llm-queue', methods=['GET'])
def get_gmail_llm_queue():
    """
    Get unparseable Gmail receipts available for LLM parsing.

    Query params:
        - connection_id: Optional filter by connection
        - limit: Max receipts to return (default 100)

    Returns:
        - receipts: List of unparseable receipts with cost estimates
        - summary: Queue statistics and LLM provider info
    """
    try:
        from mcp.gmail_llm_queue import get_queue_with_estimates

        connection_id = request.args.get('connection_id', type=int)
        limit = request.args.get('limit', 100, type=int)

        result = get_queue_with_estimates(
            connection_id=connection_id,
            limit=min(limit, 500)  # Cap at 500
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ LLM queue error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/llm-queue/estimate', methods=['POST'])
def estimate_gmail_llm_queue_cost():
    """
    Estimate LLM cost for selected receipts.

    Request body:
        - receipt_ids: List of receipt IDs to estimate

    Returns:
        - total_cost_cents: Estimated total cost
        - per_receipt: List of {id, estimated_cost_cents}
        - provider: Current LLM provider
        - model: Current LLM model
    """
    try:
        from mcp.gmail_llm_queue import estimate_receipt_cost, get_current_llm_config

        data = request.get_json() or {}
        receipt_ids = data.get('receipt_ids', [])

        if not receipt_ids:
            return jsonify({'error': 'receipt_ids required'}), 400

        # Get receipts and estimate costs
        receipts = database.get_unparseable_receipts_for_llm_queue(limit=500)
        receipt_map = {r['id']: r for r in receipts}

        per_receipt = []
        total_cost = 0

        for rid in receipt_ids:
            receipt = receipt_map.get(rid)
            if receipt:
                cost = estimate_receipt_cost(receipt)
                per_receipt.append({
                    'id': rid,
                    'subject': receipt.get('subject', ''),
                    'estimated_cost_cents': cost,
                })
                total_cost += cost

        llm_config = get_current_llm_config()

        return jsonify({
            'total_cost_cents': total_cost,
            'per_receipt': per_receipt,
            'provider': llm_config['provider'],
            'model': llm_config['model'],
            'is_free_provider': llm_config['is_free'],
        })

    except Exception as e:
        print(f"❌ LLM queue estimate error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/llm-queue/process', methods=['POST'])
def process_gmail_llm_queue():
    """
    Process selected receipts with LLM (streaming progress).

    Request body:
        - receipt_ids: List of receipt IDs to process

    Returns:
        SSE stream with progress updates
    """
    try:
        from mcp.gmail_llm_queue import process_llm_queue

        data = request.get_json() or {}
        receipt_ids = data.get('receipt_ids', [])

        if not receipt_ids:
            return jsonify({'error': 'receipt_ids required'}), 400

        def generate():
            import json
            for progress in process_llm_queue(receipt_ids):
                yield f"data: {json.dumps(progress)}\n\n"

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            }
        )

    except Exception as e:
        print(f"❌ LLM queue process error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/gmail/llm-queue/<int:receipt_id>/parse', methods=['POST'])
def parse_single_gmail_receipt_with_llm(receipt_id):
    """
    Parse a single receipt with LLM.

    Returns:
        - success: Boolean
        - parsed_data: Extracted data (if successful)
        - actual_cost_cents: Cost incurred
        - error: Error message (if failed)
    """
    try:
        from mcp.gmail_llm_queue import fetch_and_parse_receipt_with_llm

        result = fetch_and_parse_receipt_with_llm(receipt_id)

        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        print(f"❌ LLM parse error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# PDF Attachment Endpoints (MinIO storage)
# =============================================================================

@app.route('/api/gmail/receipts/<int:receipt_id>/attachments', methods=['GET'])
def get_receipt_attachments(receipt_id):
    """Get all PDF attachments for a Gmail receipt."""
    try:
        attachments = database.get_pdf_attachments_for_receipt(receipt_id)
        return jsonify({'attachments': attachments, 'receipt_id': receipt_id})
    except Exception as e:
        print(f"❌ Get attachments error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/attachments/<int:attachment_id>/download', methods=['GET'])
def download_attachment(attachment_id):
    """Download a PDF attachment directly."""
    try:
        from mcp.minio_client import get_pdf

        attachment = database.get_pdf_attachment_by_id(attachment_id)
        if not attachment:
            return jsonify({'error': 'Attachment not found'}), 404

        pdf_bytes = get_pdf(attachment['object_key'])
        if not pdf_bytes:
            return jsonify({'error': 'PDF not found in storage'}), 404

        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{attachment["filename"]}"'
            }
        )
    except Exception as e:
        print(f"❌ Download attachment error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/attachments/<int:attachment_id>/url', methods=['GET'])
def get_attachment_url(attachment_id):
    """Get a presigned URL for a PDF attachment (valid for 1 hour)."""
    try:
        from mcp.minio_client import get_presigned_url

        attachment = database.get_pdf_attachment_by_id(attachment_id)
        if not attachment:
            return jsonify({'error': 'Attachment not found'}), 404

        url = get_presigned_url(attachment['object_key'], expires_hours=1)
        if not url:
            return jsonify({'error': 'Failed to generate URL'}), 500

        return jsonify({
            'url': url,
            'filename': attachment['filename'],
            'expires_in_seconds': 3600
        })
    except Exception as e:
        print(f"❌ Get attachment URL error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/storage/status', methods=['GET'])
def get_storage_status():
    """Get MinIO storage status and statistics."""
    try:
        from mcp.minio_client import is_available, get_storage_stats

        available = is_available()
        db_stats = database.get_pdf_storage_stats()

        result = {
            'minio_available': available,
            'database_stats': db_stats
        }

        if available:
            minio_stats = get_storage_stats()
            result['minio_stats'] = minio_stats

        return jsonify(result)
    except Exception as e:
        print(f"❌ Storage status error: {e}")
        return jsonify({'error': str(e), 'minio_available': False}), 500


@app.route('/api/transactions/<int:txn_id>/enrichment-sources', methods=['GET'])
def get_enrichment_sources(txn_id):
    """Get all enrichment sources for a transaction from the multi-source table."""
    try:
        # Use the new unified enrichment sources table
        sources = database.get_transaction_enrichment_sources(txn_id)

        # Format for frontend
        formatted_sources = []
        for source in sources:
            formatted_sources.append({
                'id': source.get('id'),  # Enrichment source ID for fetching full details
                'source_type': source.get('source_type'),
                'source_id': source.get('source_id'),
                'description': source.get('description'),
                'order_id': source.get('order_id'),
                'line_items': source.get('line_items'),
                'confidence': source.get('match_confidence'),
                'match_method': source.get('match_method'),
                'is_primary': source.get('is_primary', False),
                'user_verified': source.get('user_verified', False),
                'created_at': source.get('created_at').isoformat() if source.get('created_at') else None
            })

        return jsonify({'sources': formatted_sources, 'transaction_id': txn_id})

    except Exception as e:
        print(f"❌ Enrichment sources error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/<int:txn_id>/enrichment-sources/primary', methods=['POST'])
def set_primary_enrichment_source(txn_id):
    """Set the primary enrichment source for a transaction."""
    try:
        data = request.json
        source_type = data.get('source_type')
        source_id = data.get('source_id')

        if not source_type:
            return jsonify({'error': 'source_type is required'}), 400

        success = database.set_primary_enrichment_source(txn_id, source_type, source_id)

        if success:
            # Invalidate cache since transaction data changed
            cache_manager.cache_delete("transactions:all")

            return jsonify({
                'success': True,
                'transaction_id': txn_id,
                'primary_source': {'source_type': source_type, 'source_id': source_id}
            })
        else:
            return jsonify({'error': 'Source not found or update failed'}), 404

    except Exception as e:
        print(f"❌ Set primary source error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment-sources/<int:source_id>/details', methods=['GET'])
def get_enrichment_source_details(source_id):
    """
    Fetch full details from the source table for an enrichment source.

    Returns the enrichment source metadata plus complete data from the
    appropriate source table (amazon_orders, apple_transactions, gmail_receipts, etc.)
    based on the source_type.
    """
    try:
        result = database.get_enrichment_source_full_details(source_id)

        if not result:
            return jsonify({'error': 'Enrichment source not found'}), 404

        # Format dates for JSON serialization
        def format_dates(obj):
            if isinstance(obj, dict):
                return {k: format_dates(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [format_dates(item) for item in obj]
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return obj

        formatted_result = format_dates(result)

        return jsonify(formatted_result)

    except Exception as e:
        print(f"❌ Enrichment source details error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Initialize database on startup (SQLite only)
    if hasattr(database, 'init_db'):
        database.init_db()
    # Run migration to add huququllah column if needed (SQLite only)
    if hasattr(database, 'migrate_add_huququllah_column'):
        database.migrate_add_huququllah_column()

    print("\n" + "="*50)
    print("🚀 Personal Finance Backend Starting...")
    print("="*50)
    print("📍 API available at: http://localhost:5000")
    print("💡 Test health: http://localhost:5000/api/health")
    print("="*50 + "\n")

    app.run(debug=False, use_reloader=False, port=5000)
