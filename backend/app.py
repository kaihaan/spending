from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import database_postgres as database
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

# Get frontend URL from environment, default to localhost:5173
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

# Global enrichment progress tracking
enrichment_progress = {}
enrichment_lock = threading.Lock()


@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Backend is running'})


def normalize_transaction(txn):
    """Normalize transaction field names to match frontend expectations.

    Converts:
    - timestamp → date
    - transaction_category → category
    - merchant_name → merchant
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

    return normalized


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get all transactions (both imported and TrueLayer synced)."""
    try:
        # Get both regular and TrueLayer transactions
        regular_transactions = database.get_all_transactions() or []
        truelayer_transactions = database.get_all_truelayer_transactions() or []

        # Combine both lists
        all_transactions = regular_transactions + truelayer_transactions

        # Normalize field names for frontend consistency
        all_transactions = [normalize_transaction(t) for t in all_transactions]

        # Sort by date descending (most recent first)
        # Convert to string for consistent sorting across date/datetime types
        all_transactions.sort(key=lambda t: str(t.get('date', '')), reverse=True)

        return jsonify(all_transactions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    """Manually add a transaction (for testing)."""
    try:
        data = request.json

        # Validate required fields
        if not all(k in data for k in ['date', 'description', 'amount']):
            return jsonify({'error': 'Missing required fields'}), 400

        transaction_id = database.add_transaction(
            date=data['date'],
            description=data['description'],
            amount=float(data['amount']),
            category=data.get('category', 'Other'),
            source_file=data.get('source_file'),
            merchant=data.get('merchant')
        )

        return jsonify({'id': transaction_id, **data}), 201
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
        mode = data.get('mode', 'unenriched')  # 'limit', 'all', 'unenriched'
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
                all_transactions = database.get_all_truelayer_transactions() or []
            except Exception as e:
                import traceback
                logger.error(f"Error fetching transactions: {str(e)}")
                logger.error(traceback.format_exc())
                return jsonify({
                    'error': f'Failed to fetch transactions: {str(e)}'
                }), 500

            # Filter by direction
            if direction == 'out':
                all_transactions = [t for t in all_transactions if t.get('amount', 0) < 0]
            elif direction == 'in':
                all_transactions = [t for t in all_transactions if t.get('amount', 0) > 0]
            # 'both' keeps all transactions

            # Filter by enrichment status and limit
            if mode == 'unenriched':
                # Only unenriched transactions
                all_transactions = [t for t in all_transactions if not t.get('is_enriched')]
            elif mode == 'limit' and limit:
                # First N transactions
                all_transactions = all_transactions[:limit]
            # 'all' keeps all transactions

            transaction_ids = [t.get('id') for t in all_transactions if t.get('id')]

        # Start Celery task
        from tasks.enrichment_tasks import enrich_transactions_task
        from celery.result import AsyncResult
        from celery_app import celery_app

        task = enrich_transactions_task.apply_async(
            args=[transaction_ids, force_refresh]
        )

        def generate_progress_stream():
            """Generate Server-Sent Events for enrichment progress."""
            import time

            # Send initial event
            yield f"data: {json.dumps({'status': 'started', 'job_id': task.id})}\n\n"

            # Poll task status every 500ms
            while True:
                try:
                    task_result = AsyncResult(task.id, app=celery_app)

                    if task_result.state == 'PROGRESS':
                        progress_data = task_result.info or {}
                        yield f"data: {json.dumps({'status': 'running', **progress_data})}\n\n"

                    elif task_result.state == 'SUCCESS':
                        result = task_result.result or {}
                        if isinstance(result, dict) and 'stats' in result:
                            stats = result.get('stats', {})
                            yield f"data: {json.dumps({'status': 'completed', **stats})}\n\n"
                        else:
                            yield f"data: {json.dumps({'status': 'completed', 'result': result})}\n\n"
                        break

                    elif task_result.state == 'FAILURE':
                        yield f"data: {json.dumps({'status': 'failed', 'error': str(task_result.info)})}\n\n"
                        break

                    else:
                        # Still pending or in unknown state
                        yield f"data: {json.dumps({'status': task_result.state.lower()})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
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


@app.route('/api/transactions/<int:transaction_id>/category', methods=['PUT'])
def update_transaction_category(transaction_id):
    """Update category for a specific transaction."""
    try:
        data = request.json

        if 'category' not in data:
            return jsonify({'error': 'Missing category'}), 400

        category = data['category']

        # Update in database
        success = database.update_transaction_category(transaction_id, category)

        if success:
            return jsonify({'success': True, 'id': transaction_id, 'category': category})
        else:
            return jsonify({'error': 'Transaction not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/<int:transaction_id>/category/smart', methods=['POST'])
def smart_update_transaction_category(transaction_id):
    """
    Smart category update with merchant learning.
    Updates transaction category and optionally:
    - Updates all transactions from the same merchant
    - Adds merchant to category rules for future auto-categorization
    """
    try:
        data = request.json

        if 'category' not in data:
            return jsonify({'error': 'Missing category'}), 400

        category = data['category']
        apply_to_merchant = data.get('apply_to_merchant', False)
        add_to_rules = data.get('add_to_rules', False)

        # Get the transaction to find merchant
        transaction = database.get_transaction_by_id(transaction_id)
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404

        merchant = transaction.get('merchant')
        updated_count = 0
        rule_added = False

        if apply_to_merchant and merchant:
            # Update all transactions from this merchant
            updated_count = database.update_transactions_by_merchant(merchant, category)
        else:
            # Update only this transaction
            success = database.update_transaction_category(transaction_id, category)
            updated_count = 1 if success else 0

        if add_to_rules and merchant:
            # Add merchant to category keywords
            rule_added = database.add_category_keyword(category, merchant)

            # Reload categorizer rules
            from mcp.categorizer import rebuild_keyword_lookup
            rebuild_keyword_lookup()

        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'merchant': merchant,
            'rule_added': rule_added,
            'category': category
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/<int:transaction_id>/merchant-info', methods=['GET'])
def get_transaction_merchant_info(transaction_id):
    """
    Get merchant information for a transaction.
    Returns merchant name and count of transactions from that merchant.
    """
    try:
        transaction = database.get_transaction_by_id(transaction_id)
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404

        merchant = transaction.get('merchant')
        if not merchant:
            return jsonify({
                'merchant': None,
                'merchant_transaction_count': 0
            })

        # Count transactions from this merchant
        merchant_transactions = database.get_transactions_by_merchant(merchant)

        return jsonify({
            'merchant': merchant,
            'merchant_transaction_count': len(merchant_transactions),
            'current_category': transaction.get('category')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats/categories', methods=['GET'])
def get_category_stats():
    """Get statistics about spending by category."""
    try:
        transactions = database.get_all_transactions()
        from mcp.categorizer import get_category_stats
        stats = get_category_stats(transactions)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/clear', methods=['DELETE'])
def clear_transactions():
    """Clear all transactions from the database (for testing purposes)."""
    try:
        count = database.clear_all_transactions()
        return jsonify({
            'success': True,
            'message': f'Cleared {count} transaction(s)',
            'count': count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/api/migrations/normalize-merchants/preview', methods=['GET'])
def preview_merchant_normalization():
    """Preview what would change if merchant names are normalized."""
    try:
        transactions = database.get_all_transactions()
        from mcp.merchant_normalizer import get_normalization_stats

        stats = get_normalization_stats(transactions)

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/normalize-merchants', methods=['POST'])
def normalize_merchants():
    """Normalize all merchant names in existing transactions."""
    try:
        transactions = database.get_all_transactions()
        from mcp.merchant_normalizer import normalize_merchant_name

        updated_count = 0
        changes = []

        for txn in transactions:
            original_merchant = txn.get('merchant')
            if original_merchant:
                normalized_merchant = normalize_merchant_name(original_merchant)

                if original_merchant != normalized_merchant:
                    # Update the merchant in database
                    with database.get_db() as conn:
                        c = conn.cursor()
                        c.execute('''
                            UPDATE transactions
                            SET merchant = ?
                            WHERE id = ?
                        ''', (normalized_merchant, txn['id']))
                        conn.commit()

                    updated_count += 1
                    changes.append({
                        'transaction_id': txn['id'],
                        'original': original_merchant,
                        'normalized': normalized_merchant,
                        'description': txn.get('description', '')[:50]
                    })

        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'sample_changes': changes[:20]  # Show first 20 examples
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-paypal-merchants/preview', methods=['GET'])
def preview_fix_paypal_merchants():
    """Preview what would change if PayPal merchants are extracted from descriptions."""
    try:
        changes = database.fix_paypal_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} PayPal transaction(s) would be updated'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-paypal-merchants', methods=['POST'])
def fix_paypal_merchants():
    """Extract real merchant names from PayPal transactions and update the database."""
    try:
        result = database.fix_paypal_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-via-apple-pay-merchants/preview', methods=['GET'])
def preview_fix_via_apple_pay_merchants():
    """Preview what would change if VIA APPLE PAY merchants are extracted from descriptions."""
    try:
        changes = database.fix_via_apple_pay_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} VIA APPLE PAY transaction(s) would be updated'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-via-apple-pay-merchants', methods=['POST'])
def fix_via_apple_pay_merchants():
    """Extract real merchant names from VIA APPLE PAY transactions and update the database."""
    try:
        result = database.fix_via_apple_pay_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-zettle-merchants/preview', methods=['GET'])
def preview_fix_zettle_merchants():
    """Preview what would change if Zettle merchants are extracted from descriptions."""
    try:
        changes = database.fix_zettle_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} Zettle transaction(s) would be updated'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-zettle-merchants', methods=['POST'])
def fix_zettle_merchants():
    """Extract real merchant names from Zettle transactions and update the database."""
    try:
        result = database.fix_zettle_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-bill-payment-merchants/preview', methods=['GET'])
def preview_fix_bill_payment_merchants():
    """Preview what would change if bill payment merchants are extracted from descriptions."""
    try:
        changes = database.fix_bill_payment_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} bill payment transaction(s) would be updated'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-bill-payment-merchants', methods=['POST'])
def fix_bill_payment_merchants():
    """Extract merchant names from bill payment transactions and update the database."""
    try:
        result = database.fix_bill_payment_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-bank-giro-merchants/preview', methods=['GET'])
def preview_fix_bank_giro_merchants():
    """Preview what would change if bank giro merchants are extracted from descriptions."""
    try:
        changes = database.fix_bank_giro_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} bank giro transaction(s) would be updated'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-bank-giro-merchants', methods=['POST'])
def fix_bank_giro_merchants():
    """Extract merchant names from bank giro transactions and update the database."""
    try:
        result = database.fix_bank_giro_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-direct-debit-merchants/preview', methods=['GET'])
def preview_fix_direct_debit_merchants():
    """Preview what would change if direct debit merchants are extracted from descriptions."""
    try:
        changes = database.fix_direct_debit_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} direct debit transaction(s) would be updated'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/fix-direct-debit-merchants', methods=['POST'])
def fix_direct_debit_merchants():
    """Extract real merchant names from direct debit transactions and update the database."""
    try:
        result = database.fix_direct_debit_merchants()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
def discover_accounts():
    """
    Discover account patterns in transactions that don't have mappings yet.
    Returns list of unmapped account details with sample transactions.
    """
    try:
        # Get all transactions
        transactions = database.get_all_transactions()

        # Get existing mappings
        existing_mappings = database.get_all_account_mappings()
        existing_keys = {(m['sort_code'], m['account_number']) for m in existing_mappings}

        # Find account patterns
        discovered = {}

        for txn in transactions:
            # Check merchant field first
            account_info = detect_account_pattern(txn.get('merchant', ''))

            # If not found, check description
            if not account_info:
                account_info = detect_account_pattern(txn.get('description', ''))

            if account_info:
                sort_code, account_number = account_info
                key = (sort_code, account_number)

                # Skip if already mapped
                if key in existing_keys:
                    continue

                # Store with sample transaction
                if key not in discovered:
                    discovered[key] = {
                        'sort_code': sort_code,
                        'account_number': account_number,
                        'sample_description': txn['description'],
                        'count': 0
                    }
                discovered[key]['count'] += 1

        return jsonify(list(discovered.values()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/migrations/reapply-account-mappings', methods=['POST'])
def reapply_account_mappings():
    """Re-process existing transactions to apply account mappings."""
    try:
        transactions = database.get_all_transactions()
        from mcp.merchant_normalizer import normalize_merchant_name

        updated_count = 0

        for txn in transactions:
            merchant = txn.get('merchant', '')
            description = txn.get('description', '')

            # Re-normalize with account mappings
            new_merchant = normalize_merchant_name(merchant, description)

            if new_merchant != merchant:
                # Update in database
                database.update_merchant(txn['id'], new_merchant)
                updated_count += 1

        return jsonify({
            'success': True,
            'transactions_updated': updated_count,
            'transactions_total': len(transactions)
        })
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


@app.route('/api/migrations/refresh-lookup-descriptions', methods=['POST'])
def refresh_lookup_descriptions():
    """
    Refresh lookup_description field for all matched Amazon and Apple transactions.

    This endpoint repopulates the lookup_description field based on current matches
    in the amazon_transaction_matches and apple_transaction_matches tables.
    """
    try:
        result = database.populate_lookup_descriptions()
        return jsonify({
            'success': True,
            'message': f"Updated {result['total']} lookup descriptions",
            'updated': {
                'total': result['total'],
                'amazon': result['amazon'],
                'apple': result['apple']
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Amazon Order History Endpoints
# ============================================================================

@app.route('/api/amazon/import', methods=['POST'])
def import_amazon_orders():
    """Import Amazon order history from CSV file."""
    try:
        data = request.json

        if 'filename' not in data:
            return jsonify({'error': 'Missing filename'}), 400

        filename = data['filename']
        website = data.get('website', 'Amazon.co.uk')  # Default to Amazon.co.uk

        # Parse the CSV file
        from mcp.amazon_parser import parse_amazon_csv
        import os

        file_path = os.path.join('..', 'sample', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {filename}'}), 404

        orders = parse_amazon_csv(file_path)

        # Import orders into database
        imported, duplicates = database.import_amazon_orders(orders, filename)

        # Run matching on existing transactions
        from mcp.amazon_matcher import match_all_amazon_transactions
        match_results = match_all_amazon_transactions()

        return jsonify({
            'success': True,
            'orders_imported': imported,
            'orders_duplicated': duplicates,
            'matching_results': match_results,
            'filename': filename
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
    """Get Amazon import and matching statistics."""
    try:
        stats = database.get_amazon_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/match', methods=['POST'])
def run_amazon_matching():
    """Run or re-run Amazon matching on existing transactions."""
    try:
        from mcp.amazon_matcher import match_all_amazon_transactions
        results = match_all_amazon_transactions()

        return jsonify({
            'success': True,
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
    """Import Amazon returns/refunds from CSV file."""
    try:
        data = request.json

        if 'filename' not in data:
            return jsonify({'error': 'Missing filename'}), 400

        filename = data['filename']

        # Parse the CSV file
        from mcp.amazon_returns_parser import parse_amazon_returns_csv
        import os

        file_path = os.path.join('..', 'sample', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {filename}'}), 404

        returns = parse_amazon_returns_csv(file_path)

        # Import returns into database
        imported, duplicates = database.import_amazon_returns(returns, filename)

        # Run matching on imported returns
        from mcp.amazon_returns_matcher import match_all_returns
        match_results = match_all_returns()

        return jsonify({
            'success': True,
            'returns_imported': imported,
            'returns_duplicated': duplicates,
            'matching_results': match_results,
            'filename': filename
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
    """Get Amazon returns statistics."""
    try:
        stats = database.get_returns_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amazon/returns/match', methods=['POST'])
def run_returns_matching():
    """Run or re-run returns matching."""
    try:
        from mcp.amazon_returns_matcher import match_all_returns
        results = match_all_returns()

        return jsonify({
            'success': True,
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

        # Run matching
        from mcp.apple_matcher import match_all_apple_transactions
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
    """Run or re-run Apple transaction matching."""
    try:
        from mcp.apple_matcher import match_all_apple_transactions
        results = match_all_apple_transactions()

        return jsonify({
            'success': True,
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

            formatted_connections.append({
                'id': connection_id,
                'provider_id': connection.get('provider_id'),
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
            'legacy_transactions': 'DELETE FROM transactions',
            'amazon_orders': 'DELETE FROM amazon_orders',
            'amazon_matches': 'DELETE FROM amazon_transaction_matches',
            'apple_transactions': 'DELETE FROM apple_transactions',
            'apple_matches': 'DELETE FROM apple_transaction_matches',
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
