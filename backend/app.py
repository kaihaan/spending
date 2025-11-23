from flask import Flask, jsonify, request
from flask_cors import CORS
import database_init as database
import re
import os
from mcp.merchant_normalizer import detect_account_pattern
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Get frontend URL from environment, default to localhost:5173
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')


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
                    merchant=txn['merchant']
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

        return jsonify({
            'success': True,
            'imported': imported_count,
            'filename': filename,
            'amazon_matching': match_results,
            'coverage_warning': coverage_warning
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


@app.route('/api/rules', methods=['GET'])
def get_rules():
    """Get all categorization rules (merged from DB and defaults)."""
    try:
        from mcp.categorizer import get_category_rules
        rules = get_category_rules()

        # Get list of all categories
        categories = database.get_all_categories()

        return jsonify({
            'rules': rules,
            'categories': [cat['name'] for cat in categories]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/keywords', methods=['POST'])
def add_keyword():
    """Add a keyword to a category."""
    try:
        data = request.json

        if 'category' not in data or 'keyword' not in data:
            return jsonify({'error': 'Missing category or keyword'}), 400

        category = data['category']
        keyword = data['keyword']

        success = database.add_category_keyword(category, keyword)

        if success:
            # Reload rules in categorizer
            from mcp.categorizer import rebuild_keyword_lookup
            rebuild_keyword_lookup()

            return jsonify({'success': True, 'category': category, 'keyword': keyword})
        else:
            return jsonify({'error': 'Keyword already exists for this category'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/keywords', methods=['DELETE'])
def remove_keyword():
    """Remove a keyword from a category."""
    try:
        data = request.json

        if 'category' not in data or 'keyword' not in data:
            return jsonify({'error': 'Missing category or keyword'}), 400

        category = data['category']
        keyword = data['keyword']

        success = database.remove_category_keyword(category, keyword)

        if success:
            # Reload rules in categorizer
            from mcp.categorizer import rebuild_keyword_lookup
            rebuild_keyword_lookup()

            return jsonify({'success': True, 'category': category, 'keyword': keyword})
        else:
            return jsonify({'error': 'Keyword not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/categories', methods=['POST'])
def create_category():
    """Create a new custom category."""
    try:
        data = request.json

        if 'name' not in data:
            return jsonify({'error': 'Missing category name'}), 400

        name = data['name']

        success = database.create_custom_category(name)

        if success:
            return jsonify({'success': True, 'name': name}), 201
        else:
            return jsonify({'error': 'Category already exists'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/categories/<string:name>', methods=['DELETE'])
def delete_category(name):
    """Delete a custom category."""
    try:
        success = database.delete_custom_category(name)

        if success:
            # Reload rules in categorizer
            from mcp.categorizer import rebuild_keyword_lookup
            rebuild_keyword_lookup()

            return jsonify({'success': True, 'name': name})
        else:
            return jsonify({'error': 'Cannot delete default category or category not found'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/preview', methods=['POST'])
def preview_rules():
    """Preview what would change if rules are re-applied."""
    try:
        data = request.json
        filters = data.get('filters', {'only_other': True})

        transactions = database.get_all_transactions()

        from mcp.categorizer import preview_recategorization
        changes = preview_recategorization(transactions, filters)

        return jsonify({
            'changes': changes,
            'count': len(changes)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/apply', methods=['POST'])
def apply_rules():
    """Apply rules to selected transactions."""
    try:
        data = request.json
        transaction_ids = data.get('transaction_ids', [])

        if not transaction_ids:
            return jsonify({'error': 'No transactions selected'}), 400

        # Get transactions and re-categorize
        transactions = database.get_all_transactions()
        txn_map = {txn['id']: txn for txn in transactions}

        from mcp.categorizer import categorize_transaction

        updated_count = 0
        for txn_id in transaction_ids:
            if txn_id in txn_map:
                txn = txn_map[txn_id]
                new_category = categorize_transaction(
                    description=txn.get('description', ''),
                    merchant=txn.get('merchant', ''),
                    amount=txn.get('amount', 0.0)
                )

                # Update in database
                database.update_transaction_category(txn_id, new_category)
                updated_count += 1

        return jsonify({
            'success': True,
            'updated': updated_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rules/suggestions', methods=['GET'])
def get_keyword_suggestions():
    """Get AI-powered keyword suggestions from 'Other' category transactions."""
    try:
        # Get query parameters
        min_frequency = int(request.args.get('min_frequency', 3))
        min_confidence = float(request.args.get('min_confidence', 40.0))
        max_doc_frequency = float(request.args.get('max_doc_frequency', 0.3))

        # Get transactions and rules
        transactions = database.get_all_transactions()
        from mcp.categorizer import get_category_rules
        rules = get_category_rules()

        # Analyze and get suggestions
        from mcp.keyword_analyzer import get_keyword_suggestions as get_suggestions
        suggestions_data = get_suggestions(
            transactions,
            rules,
            min_frequency=min_frequency,
            min_confidence=min_confidence,
            max_doc_frequency=max_doc_frequency
        )

        return jsonify(suggestions_data)
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
                    database.update_merchant(txn['id'], normalized_merchant)

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


@app.route('/api/huququllah/category-patterns', methods=['GET'])
def get_category_patterns():
    """Get classification patterns for each category."""
    try:
        from mcp.huququllah_classifier import get_category_classification_patterns
        patterns = get_category_classification_patterns()
        return jsonify(patterns)
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
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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

    app.run(debug=True, port=5000)
