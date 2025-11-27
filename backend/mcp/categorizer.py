"""
Categorizer MCP Component
Auto-categorizes transactions using rule-based keyword matching.
"""

import re
import sys
import os

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

# Default category rules: category -> list of keywords
DEFAULT_CATEGORY_RULES = {
    'Groceries': [
        'tesco', 'sainsbury', 'asda', 'morrisons', 'aldi', 'lidl',
        'waitrose', 'marks & spencer', 'm&s', 'co-op', 'iceland',
        'ocado', 'whole foods'
    ],
    'Transport': [
        'tfl', 'transport for london', 'uber', 'trainline', 'national rail',
        'shell', 'bp', 'esso', 'petrol', 'fuel', 'parking', 'lime',
        'bolt', 'gett', 'addison lee'
    ],
    'Dining': [
        'restaurant', 'cafe', 'coffee', 'pizza', 'mcdonalds', 'kfc',
        'nando', 'nandos', 'wagamama', 'pret', 'starbucks', 'costa',
        'nero', 'greggs', 'subway', 'burger', 'dominos', 'pizza hut',
        'pizza express', 'gourmet burger', 'five guys', 'gails',
        'food & mood', 'hill food', 'dishoom', 'honest burger'
    ],
    'Entertainment': [
        'cinema', 'spotify', 'netflix', 'amazon prime', 'apple music',
        'disney', 'youtube', 'xbox', 'playstation', 'steam',
        'odeon', 'vue', 'cineworld', 'theatre', 'concert', 'subscription'
    ],
    'Utilities': [
        'thames water', 'british gas', 'edf', 'eon', 'octopus energy',
        'vodafone', 'ee', 'o2', 'three', 'bt', 'sky', 'virgin media',
        'council tax', 'water', 'electricity', 'gas'
    ],
    'Shopping': [
        'amazon', 'amzn', 'ebay', 'argos', 'john lewis', 'zara', 'h&m',
        'next', 'primark', 'uniqlo', 'asos', 'boots', 'superdrug',
        'wilko', 'tk maxx', 'debenhams', 'jeanstore'
    ],
    'Health': [
        'pharmacy', 'doctor', 'dentist', 'hospital', 'gym', 'fitness',
        'boots pharmacy', 'lloyds pharmacy', 'pure gym', 'david lloyd'
    ],
    'Income': [
        'salary', 'transfer from', 'payment from', 'refund'
    ],
}

# Reverse lookup for faster matching - will be populated dynamically
KEYWORD_TO_CATEGORY = {}


def load_rules_from_db():
    """
    Load and merge rules from database with default rules.
    DB keywords take precedence and are added to defaults.

    Returns:
        Dictionary of category -> keywords (merged)
    """
    # Start with default rules
    merged_rules = {}
    for category, keywords in DEFAULT_CATEGORY_RULES.items():
        merged_rules[category] = keywords.copy()

    # Add custom keywords from database
    try:
        db_keywords = database.get_category_keywords()
        for category, keywords in db_keywords.items():
            if category not in merged_rules:
                merged_rules[category] = []
            # Add DB keywords (avoid duplicates)
            for keyword in keywords:
                if keyword.lower() not in [k.lower() for k in merged_rules[category]]:
                    merged_rules[category].append(keyword.lower())
    except Exception as e:
        print(f"Warning: Could not load custom keywords from database: {e}")

    return merged_rules


def rebuild_keyword_lookup():
    """
    Rebuild the KEYWORD_TO_CATEGORY lookup dictionary with current rules.
    """
    global KEYWORD_TO_CATEGORY
    KEYWORD_TO_CATEGORY = {}

    rules = load_rules_from_db()
    for category, keywords in rules.items():
        for keyword in keywords:
            KEYWORD_TO_CATEGORY[keyword.lower()] = category


# Initialize the lookup on module load
rebuild_keyword_lookup()


def categorize_transaction(description, merchant=None, amount=0.0):
    """
    Categorize a transaction based on description and merchant.

    Args:
        description: Transaction description
        merchant: Extracted merchant name (optional)
        amount: Transaction amount (positive for income, negative for expenses)

    Returns:
        Category name (string)
    """
    # Combine description and merchant for matching
    search_text = f"{description} {merchant or ''}".lower()

    # Check if it's income (positive amount)
    if amount > 0:
        # Check if it's a transfer/income keyword
        rules = load_rules_from_db()
        for keyword in rules.get('Income', []):
            if keyword in search_text:
                return 'Income'

    # Check each keyword
    for keyword, category in KEYWORD_TO_CATEGORY.items():
        if keyword in search_text:
            return category

    # Default category
    return 'Other'


def categorize_transactions(transactions):
    """
    Bulk categorize a list of transactions.

    Args:
        transactions: List of transaction dictionaries

    Returns:
        List of transactions with 'category' field added/updated
    """
    for txn in transactions:
        # Only categorize if not already categorized or if category is 'Other'
        if not txn.get('category') or txn.get('category') == 'Other':
            txn['category'] = categorize_transaction(
                description=txn.get('description', ''),
                merchant=txn.get('merchant', ''),
                amount=txn.get('amount', 0.0)
            )

    return transactions


def get_category_rules():
    """
    Get all category rules for display/editing (merged from DB and defaults).

    Returns:
        Dictionary of category -> keywords
    """
    return load_rules_from_db()


def add_category_rule(category, keyword):
    """
    Add a new keyword rule for a category.

    Args:
        category: Category name
        keyword: Keyword to match

    Returns:
        Boolean indicating success
    """
    keyword_lower = keyword.lower()

    if category not in CATEGORY_RULES:
        CATEGORY_RULES[category] = []

    if keyword_lower not in [k.lower() for k in CATEGORY_RULES[category]]:
        CATEGORY_RULES[category].append(keyword_lower)
        KEYWORD_TO_CATEGORY[keyword_lower] = category
        return True

    return False


def get_category_stats(transactions):
    """
    Get statistics about categories.

    Args:
        transactions: List of transaction dictionaries

    Returns:
        Dictionary with category statistics
    """
    stats = {}

    for txn in transactions:
        category = txn.get('category', 'Other')
        amount = txn.get('amount', 0.0)

        if category not in stats:
            stats[category] = {
                'count': 0,
                'total': 0.0,
                'expenses': 0.0,
                'income': 0.0
            }

        stats[category]['count'] += 1
        stats[category]['total'] += amount

        if amount < 0:
            stats[category]['expenses'] += abs(amount)
        else:
            stats[category]['income'] += amount

    return stats


def preview_recategorization(transactions, filters=None):
    """
    Preview what would change if rules are re-applied to transactions.

    Args:
        transactions: List of transaction dictionaries
        filters: Dict with options like:
            - 'all': Boolean - re-categorize all transactions
            - 'only_other': Boolean - only re-categorize 'Other' category
            - 'categories': List - specific categories to re-categorize

    Returns:
        List of dicts with transaction changes:
        {
            'id': transaction_id,
            'description': description,
            'merchant': merchant,
            'current_category': current category,
            'new_category': suggested category,
            'amount': amount
        }
    """
    if filters is None:
        filters = {'only_other': True}

    changes = []

    # Rebuild keyword lookup to ensure latest rules
    rebuild_keyword_lookup()

    for txn in transactions:
        current_category = txn.get('category', 'Other')
        txn_id = txn.get('id')

        # Apply filters
        if filters.get('only_other') and current_category != 'Other':
            continue

        if filters.get('categories') and current_category not in filters['categories']:
            continue

        # Get new category
        new_category = categorize_transaction(
            description=txn.get('description', ''),
            merchant=txn.get('merchant', ''),
            amount=txn.get('amount', 0.0)
        )

        # Only include if category would change
        if new_category != current_category:
            changes.append({
                'id': txn_id,
                'description': txn.get('description', ''),
                'merchant': txn.get('merchant', ''),
                'current_category': current_category,
                'new_category': new_category,
                'amount': txn.get('amount', 0.0),
                'date': txn.get('date', '')
            })

    return changes
