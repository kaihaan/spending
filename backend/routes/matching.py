"""
Matching Routes - Flask Blueprint

Handles cross-source transaction matching endpoints:
- Unified matching across Amazon, Apple, and Gmail
- Job tracking and status monitoring
- Source coverage analysis
- Stale job cleanup

Matching Context:
Links bank transactions to purchase receipts from multiple sources
to enrich transaction data with detailed line items and accurate categorization.

Routes are thin controllers that delegate to matching_service for business logic.
"""

from flask import Blueprint, request, jsonify
from services import matching_service
import traceback

matching_bp = Blueprint('matching', __name__, url_prefix='/api/matching')


# ============================================================================
# Matching Job Operations
# ============================================================================

@matching_bp.route('/jobs/<int:job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get status of a specific matching job.

    Path params:
        job_id (int): Job ID to query

    Returns:
        Job dict with status, progress, and results
    """
    try:
        job = matching_service.get_job_status(job_id)
        return jsonify(job)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Matching job status error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@matching_bp.route('/jobs/cleanup-stale', methods=['POST'])
def cleanup_stale():
    """
    Cleanup stale matching jobs older than threshold.

    Marks jobs stuck in 'queued' or 'running' status as 'failed'.
    Useful for recovering from worker crashes or network issues.

    Query params:
        threshold_minutes (int): Age threshold in minutes (default: 30)

    Returns:
        Dict with cleaned_up count and job_ids list
    """
    try:
        threshold = int(request.args.get('threshold_minutes', 30))
        result = matching_service.cleanup_stale_jobs(threshold_minutes=threshold)

        return jsonify(result)

    except Exception as e:
        print(f"❌ Cleanup stale jobs error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Source Coverage & Staleness Detection
# ============================================================================

@matching_bp.route('/coverage', methods=['GET'])
def get_coverage():
    """
    Get source coverage dates to detect stale data.

    Returns date ranges for each source and flags which ones are stale
    (more than 7 days behind bank transaction data).

    Query params:
        user_id (int): User ID to check coverage for (default: 1)

    Returns:
        Coverage dict with:
        - bank_transactions: Max date and count
        - amazon: Max date, count, and is_stale flag
        - apple: Max date, count, and is_stale flag
        - gmail: Max date, count, and is_stale flag
        - stale_sources: List of stale source names
        - stale_threshold_days: Staleness threshold (7 days)

    Example response:
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
        coverage = matching_service.get_coverage(user_id=user_id)

        return jsonify(coverage)

    except Exception as e:
        print(f"❌ Matching coverage error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Unified Matching
# ============================================================================

@matching_bp.route('/run', methods=['POST'])
def run_unified():
    """
    Unified matching endpoint - runs matching across all sources in parallel.

    Launches a Celery task that runs matching for Amazon, Apple, and Gmail
    simultaneously. Optionally syncs source data before matching.

    Request body:
        sources (list): Optional list of sources to match (default: ['amazon', 'apple', 'gmail'])
        sync_sources_first (bool): Whether to sync source data before matching (default: false)
        user_id (int): User ID for matching (default: 1)

    Returns:
        Dict with job_id, status, sources, and optional stale warning

    Example request:
        {
            "sources": ["amazon", "apple", "gmail"],
            "sync_sources_first": false
        }

    Example response:
        {
            "job_id": "unified-123",
            "status": "running",
            "sources": ["amazon", "apple", "gmail"],
            "sync_sources_first": false,
            "source_coverage_warning": {
                "stale_sources": ["amazon"],
                "bank_max_date": "2025-12-20",
                "sources": {
                    "amazon": {"max_date": "2025-12-10", "count": 200, "is_stale": true}
                }
            }
        }
    """
    try:
        data = request.json or {}
        user_id = data.get('user_id', 1)
        sources = data.get('sources', ['amazon', 'apple', 'gmail'])
        sync_first = data.get('sync_sources_first', False)

        result = matching_service.run_unified_matching(
            user_id=user_id,
            sources=sources,
            sync_first=sync_first
        )

        return jsonify(result)

    except ImportError as e:
        # Fallback if Celery task not yet implemented
        print(f"⚠️ Unified matching task not implemented yet: {e}")
        return jsonify({
            'error': 'Unified matching task not yet implemented',
            'message': 'Run individual matchers via /api/amazon/match, /api/apple/match, /api/gmail/match'
        }), 501
    except Exception as e:
        print(f"❌ Unified matching error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
