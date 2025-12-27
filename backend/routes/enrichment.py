"""
Enrichment Routes - Flask Blueprint

Handles all LLM enrichment endpoints including:
- Configuration and validation
- Cost estimation and job triggering
- Progress tracking and streaming
- Enrichment statistics and cache management

Routes are thin controllers that delegate to enrichment_service for business logic.
"""

from flask import Blueprint, request, jsonify, Response, stream_with_context
from services import enrichment_service
import traceback
import json
import logging

logger = logging.getLogger(__name__)

enrichment_bp = Blueprint('enrichment', __name__)


# ============================================================================
# Configuration
# ============================================================================

@enrichment_bp.route('/api/enrichment/config', methods=['GET'])
def get_config():
    """
    Get LLM enrichment configuration.

    Returns:
        Configuration details or not configured status
    """
    try:
        config = enrichment_service.get_config()
        return jsonify(config)

    except Exception as e:
        print(f"❌ Enrichment config error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/account-info', methods=['GET'])
def get_account_info():
    """
    Get LLM provider account information (balance, tier, usage).

    Returns:
        Account details or not configured status
    """
    try:
        account_info = enrichment_service.get_account_info()
        return jsonify(account_info)

    except Exception as e:
        print(f"❌ Enrichment account info error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/validate', methods=['POST'])
def validate_config():
    """
    Validate LLM enrichment configuration.

    Returns:
        Validation status
    """
    try:
        validation = enrichment_service.validate_config()
        status_code = 200 if validation['valid'] else 500
        return jsonify(validation), status_code

    except Exception as e:
        print(f"❌ Enrichment validation error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/llm/available-models', methods=['GET'])
def get_available_models():
    """
    Get list of available models for all LLM providers.

    Returns:
        All providers with their supported models
    """
    try:
        models = enrichment_service.get_available_models()
        return jsonify(models)

    except Exception as e:
        print(f"❌ Get available models error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Statistics & Cache
# ============================================================================

@enrichment_bp.route('/api/enrichment/cache/stats', methods=['GET'])
def get_cache_stats():
    """
    Get enrichment cache statistics.

    Returns:
        Cache statistics dict
    """
    try:
        stats = enrichment_service.get_cache_stats()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Enrichment cache stats error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/stats', methods=['GET'])
def get_stats():
    """
    Get overall enrichment statistics for TrueLayer transactions.

    Returns:
        Enrichment statistics summary
    """
    try:
        stats = enrichment_service.get_stats()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Enrichment stats error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/status', methods=['GET'])
def get_status():
    """
    Get enrichment status (alias for /stats).

    Returns:
        Enrichment statistics summary
    """
    try:
        stats = enrichment_service.get_stats()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Enrichment status error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/failed', methods=['GET'])
def get_failed():
    """
    Get failed enrichment records.

    Query params:
        limit (int): Max failed records to return (default: 20)

    Returns:
        Failed enrichments list
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        failed = enrichment_service.get_failed_enrichments(limit=limit)
        return jsonify(failed)

    except Exception as e:
        print(f"❌ Get failed enrichments error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Cost Estimation & Job Triggering
# ============================================================================

@enrichment_bp.route('/api/enrichment/estimate', methods=['POST'])
def estimate_cost():
    """
    Estimate cost for enriching TrueLayer transactions.

    Request body:
        transaction_ids (list): Specific transaction IDs (optional)
        force_refresh (bool): Force API calls even if cached

    Returns:
        Cost estimation with breakdown
    """
    try:
        data = request.get_json() or {}
        transaction_ids = data.get('transaction_ids')
        force_refresh = data.get('force_refresh', False)

        estimate = enrichment_service.estimate_cost(
            transaction_ids=transaction_ids,
            force_refresh=force_refresh
        )

        return jsonify(estimate)

    except ValueError as e:
        # LLM not configured
        return jsonify({
            'configured': False,
            'error': str(e)
        }), 503
    except Exception as e:
        print(f"❌ Enrichment estimate error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/trigger', methods=['POST'])
def trigger_enrichment():
    """
    Start enrichment job (requires cost confirmation).

    Request body:
        transaction_ids (list): Specific transaction IDs (optional)
        force_refresh (bool): Force re-enrichment
        confirm_cost (bool): Cost confirmation - REQUIRED

    Returns:
        Job details with job_id and status
    """
    try:
        data = request.get_json() or {}
        transaction_ids = data.get('transaction_ids')
        force_refresh = data.get('force_refresh', False)
        confirm_cost = data.get('confirm_cost', False)

        result = enrichment_service.trigger_enrichment(
            transaction_ids=transaction_ids,
            force_refresh=force_refresh,
            confirm_cost=confirm_cost
        )

        return jsonify(result), 202

    except ValueError as e:
        # Cost not confirmed or LLM not configured
        if 'confirmation' in str(e).lower():
            return jsonify({'error': str(e)}), 400
        else:
            return jsonify({
                'configured': False,
                'error': str(e)
            }), 503
    except Exception as e:
        print(f"❌ Trigger enrichment error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get enrichment job status by Celery task ID.

    Path params:
        job_id (str): Celery task ID

    Returns:
        Job status with progress or result
    """
    try:
        status = enrichment_service.get_job_status(job_id)

        # Check if service indicated a specific HTTP status
        http_status = status.pop('_http_status', 200)

        return jsonify(status), http_status

    except Exception as e:
        print(f"❌ Enrichment job status error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@enrichment_bp.route('/api/enrichment/retry', methods=['POST'])
def retry_failed():
    """
    Retry failed enrichments.

    Request body:
        transaction_ids (list): Specific transaction IDs to retry (optional)

    Returns:
        Job details with job_id
    """
    try:
        data = request.get_json() or {}
        transaction_ids = data.get('transaction_ids')

        result = enrichment_service.retry_failed(transaction_ids=transaction_ids)
        return jsonify(result), 202

    except Exception as e:
        print(f"❌ Retry enrichment error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Streaming Enrichment (Server-Sent Events)
# ============================================================================

@enrichment_bp.route('/api/enrichment/enrich-stream', methods=['GET', 'POST'])
def enrich_stream():
    """
    Start enrichment and stream progress via Server-Sent Events.

    Request params (POST JSON or GET query):
        transaction_ids (list): Specific transaction IDs (optional)
        mode (str): Selection mode - 'required', 'limit', 'all', 'unenriched' (default: 'required')
        limit (int): Max transactions to process
        direction (str): Transaction direction - 'out', 'in', 'both' (default: 'out')
        force_refresh (bool): Force re-enrichment

    Returns:
        Server-Sent Events stream with progress updates
    """
    try:
        logger.info(f"enrich-stream endpoint called with method {request.method}")

        # Handle both GET (query params) and POST (JSON body) requests
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            data = request.args.to_dict()

        # Parse parameters
        transaction_ids = data.get('transaction_ids')
        mode = data.get('mode', 'required')
        limit = data.get('limit')
        direction = data.get('direction', 'out')

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

        # Prepare enrichment task
        task_id, transaction_ids = enrichment_service.prepare_stream_enrichment(
            transaction_ids=transaction_ids,
            mode=mode,
            limit=limit,
            direction=direction,
            force_refresh=force_refresh
        )

        def generate_progress_stream():
            """
            Generate Server-Sent Events for enrichment progress.

            Sends events in format expected by frontend ProgressUpdate interface:
            - type: 'start' | 'progress' | 'complete' | 'error'
            - processed: current count
            - total: total count
            - percentage: 0-100
            """
            import time
            from celery.result import AsyncResult
            from celery_app import celery_app

            # Send initial event
            yield f"data: {json.dumps({'type': 'start', 'job_id': task_id, 'total': len(transaction_ids)})}\n\n"

            # Poll task status every 500ms
            while True:
                try:
                    task_result = AsyncResult(task_id, app=celery_app)

                    if task_result.state == 'PROGRESS':
                        progress_data = task_result.info or {}
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
                        yield f"data: {json.dumps({'type': 'start', 'processed': 0, 'total': len(transaction_ids), 'percentage': 0, 'message': 'Queued'})}\n\n"

                    else:
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

    except ValueError as e:
        # LLM not configured
        logger.error(f"Enrich-stream config error: {str(e)}")
        return jsonify({
            'configured': False,
            'error': str(e)
        }), 503
    except Exception as e:
        logger.error(f"Enrich-stream endpoint error: {str(e)}")
        logger.error(traceback.format_exc())
        print(f"ERROR in enrich-stream: {str(e)}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Enrichment Sources
# ============================================================================

@enrichment_bp.route('/api/enrichment-sources/<int:source_id>/details', methods=['GET'])
def get_source_details(source_id):
    """
    Fetch full details from the source table for an enrichment source.

    Path params:
        source_id (int): Enrichment source ID

    Returns:
        Source details with full data from appropriate source table
    """
    try:
        details = enrichment_service.get_source_details(source_id)
        return jsonify(details)

    except Exception as e:
        print(f"❌ Enrichment source details error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
