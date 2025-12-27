"""
Utilities Routes - Flask Blueprint

Handles system utility endpoints:
- Cache statistics
- Pre-enrichment status tracking and backfilling
- Active job monitoring (Gmail sync, matching)
- Testing data cleanup
- Storage status monitoring
- Enrichment source details

These are helper endpoints for development, testing, and system monitoring.

Routes are thin controllers that delegate to utilities_service for business logic.
"""

from flask import Blueprint, request, jsonify
from services import utilities_service
import traceback

utilities_bp = Blueprint('utilities', __name__, url_prefix='/api')


# ============================================================================
# Cache Statistics
# ============================================================================

@utilities_bp.route('/cache/stats', methods=['GET'])
def get_cache_stats():
    """
    Get Redis cache statistics.

    Returns cache metrics including:
    - Hit/miss ratios
    - Key counts
    - Memory usage
    - Connection status

    Returns:
        Dict with cache statistics

    Example response:
        {
            "connected": true,
            "keys": 42,
            "memory_used": "2.1MB",
            "hit_rate": 0.85
        }
    """
    try:
        stats = utilities_service.get_cache_stats()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Cache stats error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Pre-Enrichment Status Tracking
# ============================================================================

@utilities_bp.route('/pre-enrichment/summary', methods=['GET'])
def get_pre_enrichment_summary():
    """
    Get summary of identified transactions by vendor.

    'Identified' means transactions that either:
    1. Match vendor patterns in description (Apple, Amazon, etc.)
    2. Are linked in vendor match tables

    This provides a high-level view of how many transactions can be enriched
    with vendor-specific data.

    Returns:
        Dict with counts per vendor

    Example response:
        {
            "AMZN": 245,
            "Apple": 67,
            "AMZN RTN": 12,
            "total": 324
        }
    """
    try:
        summary = utilities_service.get_pre_enrichment_summary()
        return jsonify(summary)

    except Exception as e:
        print(f"❌ Pre-enrichment summary error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@utilities_bp.route('/pre-enrichment/backfill', methods=['POST'])
def backfill_pre_enrichment():
    """
    Backfill pre_enrichment_status for all existing transactions.

    Analyzes all transactions and sets their status based on:
    1. If already matched (in match tables) → 'Matched'
    2. If description matches patterns → 'Apple', 'AMZN', 'AMZN RTN'
    3. Otherwise → 'None'

    This is useful when:
    - New pattern detection logic is added
    - Historical data needs status recalculation
    - Database is migrated or restored

    CAUTION: This updates ALL transactions in the database.
    May take several seconds for large datasets.

    Returns:
        Dict with success status and counts

    Example response:
        {
            "success": true,
            "counts": {
                "None": 1200,
                "Apple": 67,
                "AMZN": 245,
                "AMZN RTN": 12,
                "Matched": 180
            },
            "message": "Analyzed 1704 transactions"
        }
    """
    try:
        counts = utilities_service.backfill_pre_enrichment_status()

        return jsonify({
            'success': True,
            'counts': counts,
            'message': f"Analyzed {sum(counts.values())} transactions"
        })

    except Exception as e:
        print(f"❌ Backfill pre-enrichment error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Active Job Monitoring
# ============================================================================

@utilities_bp.route('/preai/jobs/active', methods=['GET'])
def get_active_preai_jobs():
    """
    Get all active Pre-AI jobs for the current user.

    Returns any running Gmail sync jobs and matching jobs.
    Used by frontend to resume progress tracking after navigation.

    Auto-cleans up stale jobs (stuck > 30 min) before returning.

    Query params:
        user_id (int): User ID to check jobs for (default: 1)

    Returns:
        Dict with gmail_sync and matching job lists

    Example response:
        {
            "gmail_sync": {
                "id": "job-123",
                "status": "running",
                "progress": 450,
                "total": 1000
            },
            "matching": [
                {
                    "id": "match-456",
                    "source": "amazon",
                    "status": "running",
                    "matched": 12
                }
            ]
        }
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        jobs = utilities_service.get_active_jobs(user_id)

        return jsonify(jobs)

    except Exception as e:
        print(f"❌ Active jobs error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Testing Data Cleanup
# ============================================================================

@utilities_bp.route('/testing/clear', methods=['POST'])
def clear_testing_data():
    """
    Clear selected data types for testing purposes.

    DANGER: This permanently deletes data from the database.
    Use with extreme caution - primarily for development/testing.

    Query parameter:
        types (str): Comma-separated list of data type names

    Allowed types:
    - truelayer_transactions
    - amazon_orders
    - truelayer_amazon_matches
    - apple_transactions
    - truelayer_apple_matches
    - enrichment_cache
    - import_history
    - category_rules
    - gmail_receipts
    - gmail_email_content
    - gmail_sync_jobs
    - gmail_transaction_matches

    Returns:
        Dict with success status and cleared counts

    Example request:
        POST /api/testing/clear?types=enrichment_cache,category_rules

    Example response:
        {
            "success": true,
            "cleared": {
                "enrichment_cache": 45,
                "category_rules": 12,
                "truelayer_transactions": 0,
                ...
            }
        }
    """
    try:
        # Get and parse types parameter
        types_str = request.args.get('types', '').strip()
        types_list = [t.strip() for t in types_str.split(',') if t.strip()]

        result = utilities_service.clear_testing_data(types_list)
        return jsonify(result), 200

    except ValueError as e:
        # Validation errors (invalid types, empty list, etc.)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        print(f"❌ Clear testing data error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# Storage Status Monitoring
# ============================================================================

@utilities_bp.route('/storage/status', methods=['GET'])
def get_storage_status():
    """
    Get MinIO storage status and statistics.

    Returns information about:
    - MinIO availability
    - PDF attachment counts in database
    - Storage metrics (if MinIO is available)

    Returns:
        Dict with storage status

    Example response (MinIO available):
        {
            "minio_available": true,
            "database_stats": {
                "total_attachments": 123,
                "total_size_mb": 45.2
            },
            "minio_stats": {
                "bucket": "receipts",
                "objects": 123,
                "size_bytes": 47432704
            }
        }

    Example response (MinIO unavailable):
        {
            "minio_available": false,
            "database_stats": {
                "total_attachments": 0,
                "total_size_mb": 0
            }
        }
    """
    try:
        result = utilities_service.get_storage_status()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Storage status error: {e}")
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'minio_available': False
        }), 500


# ============================================================================
# Enrichment Source Details
# ============================================================================

@utilities_bp.route('/enrichment-sources/<int:source_id>/details', methods=['GET'])
def get_enrichment_source_details(source_id):
    """
    Fetch full details from the source table for an enrichment source.

    Returns the enrichment source metadata plus complete data from the
    appropriate source table (amazon_orders, apple_transactions, gmail_receipts, etc.)
    based on the source_type.

    Path params:
        source_id (int): Enrichment source ID

    Returns:
        Dict with enrichment source metadata and full source details

    Example response:
        {
            "id": 123,
            "transaction_id": 456,
            "source_type": "amazon",
            "source_id": 789,
            "confidence": 0.95,
            "source_data": {
                "order_id": "123-4567890-1234567",
                "order_date": "2025-01-15",
                "total": 29.99,
                "line_items": [...]
            }
        }
    """
    try:
        result = utilities_service.get_enrichment_source_details(source_id)
        return jsonify(result)

    except ValueError as e:
        # Source not found
        return jsonify({'error': str(e)}), 404

    except Exception as e:
        print(f"❌ Enrichment source details error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
