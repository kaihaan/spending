from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import database
import re
import os
import json
import threading
import logging
from config import llm_config
from mcp.merchant_normalizer import detect_account_pattern

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Global enrichment progress tracking
enrichment_progress = {}
enrichment_lock = threading.Lock()


@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Backend is running'})


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get all transactions."""
    try:
        transactions = database.get_all_transactions()
        return jsonify(transactions)
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


@app.route('/api/files', methods=['GET'])
def get_files():
    """Get all available Excel files in the data folder."""
    try:
        from mcp.file_manager import list_excel_files
        files = list_excel_files()
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import', methods=['POST'])
def import_file():
    """Import transactions from selected Excel file."""
    try:
        data = request.json

        if 'filename' not in data:
            return jsonify({'error': 'Missing filename'}), 400

        filename = data['filename']

        # Get file path
        from mcp.file_manager import get_file_path
        file_path = get_file_path(filename)

        # Parse Excel file
        from mcp.excel_parser import parse_santander_excel
        transactions = parse_santander_excel(str(file_path))

        # Check if file has already been imported
        from mcp.file_manager import check_if_imported
        if check_if_imported(filename):
            return jsonify({
                'error': 'File already imported',
                'message': f'{filename} has already been imported. Delete existing transactions first if you want to re-import.'
            }), 400

        # Auto-categorize transactions
        from mcp.categorizer import categorize_transactions
        transactions = categorize_transactions(transactions)

        # Extract pattern data from descriptions
        from mcp.pattern_extractor import extract_and_update
        for txn in transactions:
            extracted = extract_and_update(txn['description'])
            txn.update(extracted)

        # Insert transactions into database
        imported_count = 0
        imported_transaction_ids = []
        date_range = {'min': None, 'max': None}

        for txn in transactions:
            try:
                txn_id = database.add_transaction(
                    date=txn['date'],
                    description=txn['description'],
                    amount=txn['amount'],
                    category=txn.get('category', 'Other'),
                    source_file=txn['source_file'],
                    merchant=txn['merchant'],
                    provider=txn.get('provider'),
                    variant=txn.get('variant'),
                    payee=txn.get('payee'),
                    reference=txn.get('reference'),
                    mandate_number=txn.get('mandate_number'),
                    branch=txn.get('branch'),
                    entity=txn.get('entity'),
                    trip_date=txn.get('trip_date'),
                    sender=txn.get('sender'),
                    rate=txn.get('rate'),
                    tax=txn.get('tax'),
                    payment_count=txn.get('payment_count'),
                    extraction_confidence=txn.get('extraction_confidence')
                )
                imported_count += 1
                imported_transaction_ids.append(txn_id)

                # Track date range
                if date_range['min'] is None or txn['date'] < date_range['min']:
                    date_range['min'] = txn['date']
                if date_range['max'] is None or txn['date'] > date_range['max']:
                    date_range['max'] = txn['date']

            except Exception as e:
                print(f"Error importing transaction: {e}")
                continue

        # Auto-match Amazon transactions
        from mcp.amazon_matcher import match_all_amazon_transactions
        match_results = match_all_amazon_transactions()

        # Check Amazon coverage for this date range
        coverage_warning = None
        if date_range['min'] and date_range['max']:
            coverage = database.check_amazon_coverage(date_range['min'], date_range['max'])

            if coverage['amazon_transactions'] > 0 and not coverage['has_coverage']:
                coverage_warning = {
                    'message': f"Found {coverage['amazon_transactions']} Amazon transactions but no order history available for this period.",
                    'date_from': date_range['min'],
                    'date_to': date_range['max'],
                    'amazon_transaction_count': coverage['amazon_transactions']
                }
            elif coverage['amazon_transactions'] > 0 and coverage['match_rate'] < 100:
                coverage_warning = {
                    'message': f"Only {coverage['match_rate']:.0f}% of Amazon transactions could be matched. Consider importing more Amazon order history.",
                    'date_from': date_range['min'],
                    'date_to': date_range['max'],
                    'amazon_transaction_count': coverage['amazon_transactions'],
                    'matched_count': coverage['matched_count']
                }

        # Auto-enrich with LLM (automatic, unless disabled with skip_enrichment)
        llm_enrichment_stats = None
        skip_enrichment = data.get('skip_enrichment', False)

        if not skip_enrichment and imported_transaction_ids:
            try:
                from mcp.llm_enricher import get_enricher
                enricher = get_enricher()

                if enricher:
                    # Enrich only the newly imported transactions
                    enrichment_direction = 'out' if any(t['amount'] < 0 for t in transactions) else 'in'
                    stats = enricher.enrich_transactions(
                        transaction_ids=imported_transaction_ids,
                        direction=enrichment_direction,
                        force_refresh=False
                    )
                    llm_enrichment_stats = {
                        'successful': stats.successful_enrichments,
                        'failed': stats.failed_enrichments,
                        'cached_hits': stats.cached_hits,
                        'api_calls': stats.api_calls_made,
                        'total_cost': stats.total_cost
                    }
            except Exception as e:
                print(f"LLM enrichment during import failed: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the import if enrichment fails

        return jsonify({
            'success': True,
            'imported': imported_count,
            'filename': filename,
            'amazon_matching': match_results,
            'coverage_warning': coverage_warning,
            'llm_enrichment': llm_enrichment_stats
        }), 201

    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


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


@app.route('/api/migrations/fix-card-payment-merchants/preview', methods=['GET'])
def preview_fix_card_payment_merchants():
    """Preview what would change if card payment merchants are extracted from descriptions."""
    try:
        changes = database.fix_card_payment_merchants_preview()

        return jsonify({
            'changes': changes,
            'count': len(changes),
            'message': f'{len(changes)} card payment transaction(s) would be updated'
        })
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
                with database.get_db() as conn:
                    c = conn.cursor()
                    c.execute('''
                        UPDATE transactions
                        SET merchant = ?
                        WHERE id = ?
                    ''', (new_merchant, txn['id']))
                    conn.commit()
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
# LLM Enrichment Endpoints
# ============================================================================

@app.route('/api/enrichment/config', methods=['GET'])
def get_enrichment_config():
    """Get current LLM enrichment configuration."""
    try:
        from mcp.llm_enricher import get_enricher

        # Reload config from environment to get latest changes
        config = llm_config.load_llm_config()

        if not config:
            return jsonify({
                'configured': False,
                'message': 'LLM enrichment not configured. Set LLM_PROVIDER and LLM_API_KEY environment variables.'
            }), 400

        # Return the config directly instead of relying on enricher's cached status
        return jsonify({
            'configured': True,
            'config': {
                'provider': config.provider.value,
                'model': config.model,
                'cache_enabled': config.cache_enabled,
                'configured': True
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/validate', methods=['POST'])
def validate_enrichment_config():
    """Validate LLM configuration by testing API connectivity."""
    try:
        from mcp.llm_enricher import get_enricher
        enricher = get_enricher()

        if not enricher:
            return jsonify({
                'valid': False,
                'message': 'LLM enrichment not configured'
            }), 400

        is_valid = enricher.validate_configuration()

        return jsonify({
            'valid': is_valid,
            'message': 'Configuration is valid' if is_valid else 'Invalid LLM API key or provider not accessible'
        })
    except Exception as e:
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 500


@app.route('/api/enrichment/enrich', methods=['POST'])
def enrich_transactions():
    """
    Enrich transactions with LLM.

    Request body:
    {
        "transaction_ids": [1, 2, 3] or null (for all),
        "direction": "out" or "in",
        "force_refresh": false
    }
    """
    try:
        from mcp.llm_enricher import get_enricher
        enricher = get_enricher()

        if not enricher:
            return jsonify({
                'error': 'LLM enrichment not configured',
                'message': 'Set LLM_PROVIDER and LLM_API_KEY environment variables'
            }), 400

        data = request.json or {}
        transaction_ids = data.get('transaction_ids')  # None means all
        direction = data.get('direction', 'out')
        force_refresh = data.get('force_refresh', False)

        # Validate direction
        if direction not in ['in', 'out']:
            return jsonify({'error': 'Invalid direction. Must be "in" or "out"'}), 400

        # Run enrichment
        stats = enricher.enrich_transactions(
            transaction_ids=transaction_ids,
            direction=direction,
            force_refresh=force_refresh
        )

        return jsonify({
            'success': True,
            'stats': {
                'total_transactions': stats.total_transactions,
                'successful_enrichments': stats.successful_enrichments,
                'failed_enrichments': stats.failed_enrichments,
                'cached_hits': stats.cached_hits,
                'api_calls_made': stats.api_calls_made,
                'total_tokens_used': stats.total_tokens_used,
                'total_cost': stats.total_cost,
                'retry_queue': stats.retry_queue
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/enrich-stream', methods=['POST'])
def enrich_transactions_stream():
    """
    Enrich transactions with real-time progress streaming (Server-Sent Events).

    Request body:
    {
        "transaction_ids": [1, 2, 3] or null (for all),
        "direction": "out" or "in",
        "force_refresh": false,
        "mode": "all", "unenriched", or "limit" (default: "unenriched"),
        "limit": 50 (only used with mode "limit")
    }
    """
    def generate():
        try:
            from mcp.llm_enricher import get_enricher
            enricher = get_enricher()

            if not enricher:
                yield f'data: {json.dumps({"error": "LLM enrichment not configured"})}\n\n'
                return

            data = request.json or {}
            transaction_ids = data.get('transaction_ids')
            direction = data.get('direction', 'out')
            force_refresh = data.get('force_refresh', False)
            mode = data.get('mode', 'unenriched')  # 'all', 'unenriched', or 'limit'
            limit = data.get('limit', None)  # Only used with mode='limit'

            # Validate direction
            if direction not in ['in', 'out']:
                yield f'data: {json.dumps({"error": "Invalid direction"})}\n\n'
                return

            # Get transactions to process
            if transaction_ids:
                transactions = [database.get_transaction_by_id(tid) for tid in transaction_ids]
                transactions = [t for t in transactions if t]
            else:
                all_transactions = database.get_all_transactions()

                # Apply mode filtering
                if mode == 'unenriched':
                    # Skip already enriched transactions
                    transactions = [t for t in all_transactions if not database.is_transaction_enriched(t['id'])]
                elif mode == 'limit' and limit:
                    # Limit to first N UNENRICHED transactions
                    unenriched = [t for t in all_transactions if not database.is_transaction_enriched(t['id'])]
                    transactions = unenriched[:limit]
                else:
                    # 'all' mode - use all transactions
                    transactions = all_transactions

            total = len(transactions)

            yield f'data: {json.dumps({
                "type": "start",
                "total_transactions": total,
                "message": f"Starting enrichment of {total} transactions..."
            })}\n\n'

            # Track progress
            processed = 0
            total_tokens = 0
            total_cost = 0.0
            successful = 0
            failed = 0

            # Process in batches
            batch_size = enricher._calculate_batch_size(total)

            for i in range(0, total, batch_size):
                batch = transactions[i:i + batch_size]
                batch_num = (i // batch_size) + 1

                try:
                    # Prepare batch data with enrichment context
                    batch_data = []
                    for txn in batch:
                        txn_data = {
                            "description": txn["description"],
                            "date": txn.get("date", ""),
                        }

                        # Include lookup_description if available (from Amazon/Apple matches)
                        if txn.get("lookup_description"):
                            txn_data["lookup_description"] = txn["lookup_description"]

                        # Include merchant name if available for additional context
                        # Note: this would be extracted merchant names from pattern extraction or enrichment
                        # For now we only include it if explicitly provided in the transaction data

                        batch_data.append(txn_data)

                    # Query LLM
                    enrichments, stats = enricher.provider.enrich_transactions(batch_data, direction)

                    # Process results
                    for txn, enrichment in zip(batch, enrichments):
                        # Add provider and model info to enrichment
                        enrichment.llm_provider = enricher.config.provider.value
                        enrichment.llm_model = enricher.config.model
                        database.update_transaction_with_enrichment(txn["id"], enrichment)
                        if enricher.config.cache_enabled:
                            database.cache_enrichment(
                                description=txn["description"],
                                direction=direction,
                                enrichment=enrichment,
                                provider=enricher.config.provider.value,
                                model=enricher.config.model,
                            )
                        successful += 1

                    # Update metrics
                    processed += len(batch)
                    total_tokens += stats.tokens_used
                    total_cost += stats.estimated_cost
                    failed += len(batch) - len(enrichments)

                    # Send progress update
                    yield f'data: {json.dumps({
                        "type": "progress",
                        "processed": processed,
                        "total": total,
                        "batch_num": batch_num,
                        "tokens_used": total_tokens,
                        "cost": round(total_cost, 4),
                        "successful": successful,
                        "failed": failed,
                        "percentage": round((processed / total) * 100, 1) if total > 0 else 0
                    })}\n\n'

                except Exception as e:
                    failed += len(batch)
                    processed += len(batch)
                    yield f'data: {json.dumps({
                        "type": "progress",
                        "processed": processed,
                        "total": total,
                        "tokens_used": total_tokens,
                        "cost": round(total_cost, 4),
                        "successful": successful,
                        "failed": failed,
                        "error": str(e),
                        "percentage": round((processed / total) * 100, 1) if total > 0 else 0
                    })}\n\n'

            # Send completion
            yield f'data: {json.dumps({
                "type": "complete",
                "total_transactions": total,
                "successful": successful,
                "failed": failed,
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
                "cached_hits": total - successful - failed
            })}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@app.route('/api/enrichment/enrich-batch', methods=['POST'])
def enrich_specific_transactions():
    """
    Enrich specific transactions by ID.

    Request body:
    {
        "transaction_ids": [1, 2, 3],
        "direction": "out" or "in",
        "force_refresh": false
    }
    """
    try:
        from mcp.llm_enricher import get_enricher
        enricher = get_enricher()

        if not enricher:
            return jsonify({
                'error': 'LLM enrichment not configured',
                'message': 'Set LLM_PROVIDER and LLM_API_KEY environment variables'
            }), 400

        data = request.json or {}
        transaction_ids = data.get('transaction_ids', [])
        direction = data.get('direction', 'out')
        force_refresh = data.get('force_refresh', False)

        if not transaction_ids:
            return jsonify({'error': 'transaction_ids array is required'}), 400

        if direction not in ['in', 'out']:
            return jsonify({'error': 'Invalid direction. Must be "in" or "out"'}), 400

        # Run enrichment
        stats = enricher.enrich_transactions(
            transaction_ids=transaction_ids,
            direction=direction,
            force_refresh=force_refresh
        )

        return jsonify({
            'success': True,
            'stats': {
                'total_transactions': stats.total_transactions,
                'successful_enrichments': stats.successful_enrichments,
                'failed_enrichments': stats.failed_enrichments,
                'cached_hits': stats.cached_hits,
                'api_calls_made': stats.api_calls_made,
                'total_tokens_used': stats.total_tokens_used,
                'total_cost': stats.total_cost,
                'retry_queue': stats.retry_queue
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/cache/stats', methods=['GET'])
def get_enrichment_cache_stats():
    """Get enrichment cache statistics."""
    try:
        stats = database.get_cache_stats()
        # Transform to match frontend expectations
        return jsonify({
            'total_cached': stats.get('cache_size', 0),
            'providers': stats.get('provider_breakdown', {}),
            'pending_retries': stats.get('pending_retries', 0),
            'cache_size_bytes': stats.get('cache_size_bytes', 0)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/failed', methods=['GET'])
def get_failed_enrichments():
    """Get list of failed enrichments pending retry."""
    try:
        limit = int(request.args.get('limit', 50))
        failed = database.get_failed_enrichments(limit)

        return jsonify({
            'failed_enrichments': failed,
            'count': len(failed)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/retry-failed', methods=['POST'])
def retry_failed_enrichments():
    """
    Retry enrichment for failed transactions.

    Request body:
    {
        "direction": "out" or "in",
        "limit": 50
    }
    """
    try:
        from mcp.llm_enricher import get_enricher
        enricher = get_enricher()

        if not enricher:
            return jsonify({
                'error': 'LLM enrichment not configured',
                'message': 'Set LLM_PROVIDER and LLM_API_KEY environment variables'
            }), 400

        data = request.json or {}
        direction = data.get('direction', 'out')
        limit = data.get('limit', 50)

        if direction not in ['in', 'out']:
            return jsonify({'error': 'Invalid direction. Must be "in" or "out"'}), 400

        # Get failed enrichments
        failed = database.get_failed_enrichments(limit)

        if not failed:
            return jsonify({
                'success': True,
                'message': 'No failed enrichments to retry',
                'retried': 0,
                'stats': None
            })

        # Extract transaction IDs from failed records
        transaction_ids = [f['transaction_id'] for f in failed]

        # Retry enrichment
        stats = enricher.enrich_transactions(
            transaction_ids=transaction_ids,
            direction=direction,
            force_refresh=True  # Force refresh to re-query LLM
        )

        return jsonify({
            'success': True,
            'retried': len(transaction_ids),
            'stats': {
                'total_transactions': stats.total_transactions,
                'successful_enrichments': stats.successful_enrichments,
                'failed_enrichments': stats.failed_enrichments,
                'cached_hits': stats.cached_hits,
                'api_calls_made': stats.api_calls_made,
                'total_tokens_used': stats.total_tokens_used,
                'total_cost': stats.total_cost,
                'retry_queue': stats.retry_queue
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/analytics', methods=['GET'])
def get_enrichment_analytics():
    """Get comprehensive enrichment analytics and coverage metrics."""
    try:
        analytics = database.get_enrichment_analytics()
        return jsonify(analytics), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/quality-report', methods=['GET'])
def get_enrichment_quality_report():
    """Get detailed enrichment quality report with confidence distribution."""
    try:
        report = database.get_enrichment_quality_report()
        return jsonify(report), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/cost-tracking', methods=['GET'])
def get_enrichment_cost_tracking():
    """Get cost tracking and efficiency metrics for enrichment."""
    try:
        days_back = request.args.get('days_back', type=int, default=None)
        cost_data = database.get_enrichment_cost_tracking(days_back)
        return jsonify(cost_data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/by-source', methods=['GET'])
def get_enrichment_by_source():
    """Get data source attribution for enrichment."""
    try:
        source_data = database.get_enrichment_by_source()
        return jsonify(source_data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enrichment/clear', methods=['POST'])
def clear_enrichment_data():
    """Clear all enrichment data from database. Use with caution (dev purposes)."""
    try:
        result = database.clear_all_enrichments()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/enrichment/refresh-lookup-descriptions', methods=['POST'])
def refresh_lookup_descriptions_for_enrichment():
    """Refresh lookup_description for all transactions from Amazon/Apple matches."""
    try:
        result = database.refresh_lookup_descriptions()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# LLM Model Management Routes
# ============================================================================

@app.route('/api/llm/available-models', methods=['GET'])
def get_available_models():
    """Get available models for all LLM providers."""
    try:
        from mcp.model_manager import get_model_manager

        config = llm_config.load_llm_config()
        if not config:
            return jsonify({'error': 'LLM not configured'}), 400

        manager = get_model_manager()

        # Initialize models for ALL providers
        all_providers = ['anthropic', 'openai', 'google', 'deepseek', 'ollama']
        for provider in all_providers:
            manager.initialize_provider_models(provider)

        # Get models for all providers
        all_models = {}
        current_provider = config.provider.value

        for provider in all_providers:
            try:
                models = manager.get_available_models(provider, include_ollama_discovery=(provider == 'ollama'))
                all_models[provider] = models
            except Exception as e:
                logger.warning(f"Error getting models for {provider}: {e}")
                all_models[provider] = {'provider': provider, 'selected': None, 'built_in': [], 'custom': []}

        return jsonify({
            'current_provider': current_provider,
            'all_models': all_models
        }), 200
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/models/<provider>', methods=['GET'])
def get_provider_models(provider):
    """Get all models for a specific provider."""
    try:
        from mcp.model_manager import get_model_manager

        manager = get_model_manager()
        manager.initialize_provider_models(provider)

        models = manager.get_available_models(provider)
        return jsonify(models), 200
    except Exception as e:
        logger.error(f"Error getting provider models: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/set-model', methods=['POST'])
def set_active_model():
    """Set the active model for specified provider (or current provider if not specified)."""
    try:
        from mcp.model_manager import get_model_manager
        from config.llm_config import LLMProvider

        config = llm_config.load_llm_config()
        if not config:
            return jsonify({'error': 'LLM not configured'}), 400

        data = request.get_json()
        model_name = data.get('model_name')
        provider = data.get('provider')  # Optional: provider to set model for

        if not model_name:
            return jsonify({'error': 'model_name required'}), 400

        # If provider is specified, use it; otherwise use current provider
        target_provider = provider if provider else config.provider.value

        manager = get_model_manager()
        # Initialize models for this provider if not already done
        manager.initialize_provider_models(target_provider)
        result = manager.set_model(target_provider, model_name)

        if result['success']:
            # Update os.environ and .env file
            try:
                # Update environment variables directly for immediate effect
                os.environ['LLM_MODEL'] = model_name

                # If we're switching to a different provider, update that too
                if provider and provider != config.provider.value:
                    os.environ['LLM_PROVIDER'] = provider

                # Also update .env file for persistence
                import os
                env_file = os.path.join(os.path.dirname(__file__), '.env')
                if os.path.exists(env_file):
                    # Read current env content
                    with open(env_file, 'r') as f:
                        lines = f.readlines()

                    # Update or add LLM_PROVIDER and LLM_MODEL lines
                    updated_lines = []
                    found_provider = False
                    found_model = False
                    for line in lines:
                        if line.startswith('LLM_PROVIDER='):
                            updated_lines.append(f'LLM_PROVIDER={provider or config.provider.value}\n')
                            found_provider = True
                        elif line.startswith('LLM_MODEL='):
                            updated_lines.append(f'LLM_MODEL={model_name}\n')
                            found_model = True
                        else:
                            updated_lines.append(line)

                    if not found_provider and provider:
                        updated_lines.append(f'LLM_PROVIDER={provider}\n')
                    if not found_model:
                        updated_lines.append(f'LLM_MODEL={model_name}\n')

                    with open(env_file, 'w') as f:
                        f.writelines(updated_lines)
            except Exception as e:
                logger.warning(f"Could not update environment/config: {e}")

            # Force reload the enricher with new config
            try:
                from mcp.llm_enricher import get_enricher, _enricher as enricher_ref
                import mcp.llm_enricher as enricher_module
                # Reset the global enricher instance
                enricher_module._enricher = None
                # Get fresh enricher with new config
                new_enricher = get_enricher()
                if new_enricher:
                    logger.info(f"Reloaded enricher with model: {model_name} from provider: {os.environ.get('LLM_PROVIDER')}")
            except Exception as e:
                logger.warning(f"Could not reload enricher: {e}")

        return jsonify(result), 200 if result['success'] else 400
    except Exception as e:
        logger.error(f"Error setting model: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/add-ollama-model', methods=['POST'])
def add_ollama_model():
    """Add a custom Ollama model."""
    try:
        from mcp.model_manager import get_model_manager

        config = llm_config.load_llm_config()
        if not config or config.provider.value != 'ollama':
            return jsonify({'error': 'Ollama provider not configured'}), 400

        data = request.get_json()
        model_name = data.get('model_name')
        auto_pull = data.get('auto_pull', True)

        if not model_name:
            return jsonify({'error': 'model_name required'}), 400

        manager = get_model_manager()
        result = manager.add_custom_ollama_model(model_name, auto_pull=auto_pull)

        return jsonify(result), 200 if result['success'] else 400
    except Exception as e:
        logger.error(f"Error adding Ollama model: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/delete-custom-model', methods=['POST'])
def delete_custom_model():
    """Delete a custom model."""
    try:
        from mcp.model_manager import get_model_manager

        config = llm_config.load_llm_config()
        if not config:
            return jsonify({'error': 'LLM not configured'}), 400

        data = request.get_json()
        model_name = data.get('model_name')

        if not model_name:
            return jsonify({'error': 'model_name required'}), 400

        manager = get_model_manager()
        result = manager.delete_custom_model(config.provider.value, model_name)

        return jsonify(result), 200 if result['success'] else 400
    except Exception as e:
        logger.error(f"Error deleting custom model: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/ollama-health', methods=['GET'])
def check_ollama_health():
    """Check Ollama service health."""
    try:
        from mcp.model_manager import get_model_manager

        manager = get_model_manager()
        health = manager.check_ollama_health()

        return jsonify(health), 200
    except Exception as e:
        logger.error(f"Error checking Ollama health: {e}")
        return jsonify({'healthy': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # Initialize database on startup
    database.init_db()
    # Run migration to add huququllah column if needed
    database.migrate_add_huququllah_column()

    print("\n" + "="*50)
    print("🚀 Personal Finance Backend Starting...")
    print("="*50)
    print("📍 API available at: http://localhost:5000")
    print("💡 Test health: http://localhost:5000/api/health")
    print("="*50 + "\n")

    app.run(debug=True, port=5000)
