"""
Direct Debit Mapping - Database Operations

Handles mapping between merchant names in bank statements and normalized names
for direct debit transactions.
"""

from .base import get_db
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


# ============================================================================
# DIRECT DEBIT MAPPING FUNCTIONS
# ============================================================================


def get_direct_debit_payees() -> list:
    """
    Extract unique payees from DIRECT DEBIT transactions.

    Uses the pattern extractor to parse payee names from transaction descriptions.
    Groups by payee and includes transaction counts and current enrichment status.

    Returns:
        List of payee dictionaries with:
        - payee: Extracted payee name
        - transaction_count: Number of transactions
        - sample_description: Example transaction description
        - current_category: Most common category for this payee
        - current_subcategory: Most common subcategory for this payee
        - mapping_id: ID of existing mapping if configured
    """
    # Import pattern extractor here to avoid circular imports
    from mcp.pattern_extractor import extract_variables, extract_direct_debit_payee_fallback

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all direct debit transactions
            cursor.execute('''
                SELECT id, description,
                       metadata->'enrichment'->>'primary_category' as category,
                       metadata->'enrichment'->>'subcategory' as subcategory,
                       metadata->'enrichment'->>'merchant_clean_name' as merchant
                FROM truelayer_transactions
                WHERE description LIKE 'DIRECT DEBIT PAYMENT TO%'
                ORDER BY timestamp DESC
            ''')
            transactions = cursor.fetchall()

            # Group by extracted payee
            payee_data = {}
            for txn in transactions:
                extracted = extract_variables(txn['description'])
                payee = extracted.get('payee')

                # Fallback extraction if strict pattern fails
                if not payee:
                    extracted = extract_direct_debit_payee_fallback(txn['description'])
                    payee = extracted.get('payee')

                if payee:
                    payee_upper = payee.upper().strip()
                    if payee_upper not in payee_data:
                        payee_data[payee_upper] = {
                            'payee': payee.strip(),
                            'transaction_count': 0,
                            'sample_description': txn['description'],
                            'categories': {},
                            'subcategories': {},
                        }
                    payee_data[payee_upper]['transaction_count'] += 1

                    # Track category frequency
                    cat = txn['category'] or 'Uncategorized'
                    payee_data[payee_upper]['categories'][cat] = \
                        payee_data[payee_upper]['categories'].get(cat, 0) + 1

                    subcat = txn['subcategory'] or 'None'
                    payee_data[payee_upper]['subcategories'][subcat] = \
                        payee_data[payee_upper]['subcategories'].get(subcat, 0) + 1

            # Find existing mappings for these payees
            cursor.execute('''
                SELECT id, pattern, normalized_name, default_category, merchant_type
                FROM merchant_normalizations
                WHERE source = 'direct_debit'
                ORDER BY priority DESC
            ''')
            mappings = {row['pattern'].upper(): dict(row) for row in cursor.fetchall()}

            # Build result list
            result = []
            for payee_upper, data in payee_data.items():
                # Find most common category/subcategory
                most_common_cat = max(data['categories'].keys(),
                                     key=lambda k: data['categories'][k])
                most_common_subcat = max(data['subcategories'].keys(),
                                        key=lambda k: data['subcategories'][k])

                payee_info = {
                    'payee': data['payee'],
                    'transaction_count': data['transaction_count'],
                    'sample_description': data['sample_description'],
                    'current_category': most_common_cat if most_common_cat != 'Uncategorized' else None,
                    'current_subcategory': most_common_subcat if most_common_subcat != 'None' else None,
                    'mapping_id': None,
                    'mapped_name': None,
                    'mapped_category': None,
                    'mapped_subcategory': None,
                }

                # Check if there's an existing mapping
                if payee_upper in mappings:
                    mapping = mappings[payee_upper]
                    payee_info['mapping_id'] = mapping['id']
                    payee_info['mapped_name'] = mapping['normalized_name']
                    payee_info['mapped_category'] = mapping['default_category']
                    payee_info['mapped_subcategory'] = mapping['normalized_name']  # Subcategory = normalized name

                result.append(payee_info)

            # Sort alphabetically by payee name
            result.sort(key=lambda x: x['payee'].upper())
            return result


def get_direct_debit_mappings() -> list:
    """
    Fetch merchant normalizations configured for direct debit payees.

    Returns:
        List of mapping dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, pattern, pattern_type, normalized_name, merchant_type,
                       default_category, priority, source, usage_count,
                       created_at, updated_at
                FROM merchant_normalizations
                WHERE source = 'direct_debit'
                ORDER BY priority DESC, pattern ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]


def save_direct_debit_mapping(payee_pattern: str, normalized_name: str,
                               category: str, subcategory: str = None,
                               merchant_type: str = None) -> int:
    """
    Save a direct debit payee mapping.

    Creates or updates a merchant_normalization entry with source='direct_debit'.

    Args:
        payee_pattern: Pattern to match (the extracted payee name)
        normalized_name: Clean merchant name
        category: Category to assign
        subcategory: Optional subcategory (stored in metadata)
        merchant_type: Optional merchant type

    Returns:
        ID of the created/updated mapping
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Use upsert to create or update
            cursor.execute('''
                INSERT INTO merchant_normalizations
                (pattern, pattern_type, normalized_name, merchant_type,
                 default_category, priority, source)
                VALUES (%s, 'exact', %s, %s, %s, 100, 'direct_debit')
                ON CONFLICT (pattern, pattern_type) DO UPDATE SET
                    normalized_name = EXCLUDED.normalized_name,
                    merchant_type = EXCLUDED.merchant_type,
                    default_category = EXCLUDED.default_category,
                    priority = EXCLUDED.priority,
                    source = 'direct_debit',
                    updated_at = NOW()
                RETURNING id
            ''', (payee_pattern.upper(), normalized_name, merchant_type, category))
            mapping_id = cursor.fetchone()[0]
            conn.commit()
            return mapping_id


def delete_direct_debit_mapping(mapping_id: int) -> bool:
    """
    Delete a direct debit mapping.

    Args:
        mapping_id: ID of the mapping to delete

    Returns:
        True if deleted successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                DELETE FROM merchant_normalizations
                WHERE id = %s AND source = 'direct_debit'
            ''', (mapping_id,))
            conn.commit()
            return cursor.rowcount > 0


def apply_direct_debit_mappings() -> dict:
    """
    Re-enrich all direct debit transactions using current mappings.

    For each direct debit transaction:
    1. Extract payee using pattern extractor
    2. Match against merchant_normalizations with source='direct_debit'
    3. Apply enrichment data to matching transactions

    Returns:
        Dict with: updated_count, transactions (list of updated IDs)
    """
    from mcp.pattern_extractor import extract_variables, extract_direct_debit_payee_fallback

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all direct debit mappings
            cursor.execute('''
                SELECT id, pattern, normalized_name, merchant_type, default_category
                FROM merchant_normalizations
                WHERE source = 'direct_debit'
            ''')
            mappings = {row['pattern'].upper(): dict(row) for row in cursor.fetchall()}

            if not mappings:
                return {'updated_count': 0, 'transactions': []}

            # Get direct debit transactions
            cursor.execute('''
                SELECT id, description, metadata
                FROM truelayer_transactions
                WHERE description LIKE 'DIRECT DEBIT PAYMENT TO%'
            ''')
            transactions = cursor.fetchall()

            updated_ids = []
            for txn in transactions:
                extracted = extract_variables(txn['description'])
                payee = extracted.get('payee')

                # Fallback extraction if strict pattern fails
                if not payee:
                    extracted = extract_direct_debit_payee_fallback(txn['description'])
                    payee = extracted.get('payee')

                if payee and payee.upper() in mappings:
                    mapping = mappings[payee.upper()]

                    # Build enrichment data
                    metadata = txn['metadata'] or {}
                    enrichment = metadata.get('enrichment', {})
                    enrichment.update({
                        'primary_category': mapping['default_category'],
                        'subcategory': mapping['normalized_name'],  # Use merchant as subcategory
                        'merchant_clean_name': mapping['normalized_name'],
                        'merchant_type': mapping.get('merchant_type'),
                        'confidence_score': 1.0,
                        'llm_model': 'direct_debit_rule',
                        'enrichment_source': 'rule',
                    })
                    metadata['enrichment'] = enrichment

                    # Update transaction
                    cursor.execute('''
                        UPDATE truelayer_transactions
                        SET metadata = %s
                        WHERE id = %s
                    ''', (json.dumps(metadata), txn['id']))
                    updated_ids.append(txn['id'])

            conn.commit()
            return {
                'updated_count': len(updated_ids),
                'transactions': updated_ids
            }


def detect_new_direct_debits() -> dict:
    """
    Detect new direct debit payees that haven't been mapped yet.

    Returns:
        {
            'new_payees': [{'payee': str, 'first_seen': str, 'transaction_count': int, 'mandate_numbers': list}],
            'total_unmapped': int
        }
    """
    from mcp.pattern_extractor import extract_variables, extract_direct_debit_payee_fallback

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all mapped payees
            cursor.execute('''
                SELECT UPPER(pattern) as pattern FROM merchant_normalizations
                WHERE source = 'direct_debit'
            ''')
            mapped_payees = {row['pattern'] for row in cursor.fetchall()}

            # Get all direct debit transactions
            cursor.execute('''
                SELECT description, timestamp
                FROM truelayer_transactions
                WHERE description LIKE 'DIRECT DEBIT PAYMENT TO%'
                ORDER BY timestamp ASC
            ''')

            # Track payees and their mandates
            payee_info = {}  # payee -> {first_seen, mandates: set(), count}

            for txn in cursor.fetchall():
                extracted = extract_variables(txn['description'])
                if not extracted.get('payee'):
                    extracted = extract_direct_debit_payee_fallback(txn['description'])

                payee = extracted.get('payee')
                if not payee:
                    continue

                payee_upper = payee.upper().strip()
                mandate = extracted.get('mandate_number')

                if payee_upper not in payee_info:
                    payee_info[payee_upper] = {
                        'payee': payee.strip(),
                        'first_seen': txn['timestamp'],
                        'mandates': set(),
                        'count': 0
                    }

                payee_info[payee_upper]['count'] += 1
                if mandate:
                    payee_info[payee_upper]['mandates'].add(mandate)

            # Find unmapped payees
            new_payees = []
            for payee_upper, info in payee_info.items():
                if payee_upper not in mapped_payees:
                    new_payees.append({
                        'payee': info['payee'],
                        'first_seen': info['first_seen'].isoformat() if info['first_seen'] else None,
                        'transaction_count': info['count'],
                        'mandate_numbers': list(info['mandates'])
                    })

            return {
                'new_payees': sorted(new_payees, key=lambda x: x['payee'].upper()),
                'total_unmapped': len(new_payees)
            }


# ============================================================================
