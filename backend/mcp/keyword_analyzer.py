"""
Keyword Analyzer MCP Component
Analyzes 'Other' category transactions to suggest new categorization keywords.
Uses pattern matching and similarity scoring for smart category suggestions.
"""

import re
import math
from collections import Counter
from typing import List, Dict, Tuple, Set
import difflib


def clean_text(text: str) -> str:
    """Clean and normalize text for analysis."""
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Remove common payment prefixes
    prefixes = [
        'card payment to ',
        'payment to ',
        'transfer to ',
        'via apple pay',
        'via google pay',
        'via paypal',
        'online payment',
        'direct debit',
        'standing order',
    ]
    for prefix in prefixes:
        text = text.replace(prefix, '')

    # Remove dates (various formats)
    text = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', '', text)
    text = re.sub(r'\b\d{2,4}[-/]\d{1,2}[-/]\d{1,2}\b', '', text)

    # Remove reference numbers
    text = re.sub(r'\bref\s*\d+\b', '', text)
    text = re.sub(r'\b[a-z]{2,3}\d{4,}\b', '', text)

    # Remove extra whitespace
    text = ' '.join(text.split())

    return text.strip()


def extract_keywords_from_transactions(
    transactions: List[Dict],
    min_frequency: int = 3,
    max_doc_frequency: float = 0.3
) -> Dict[str, Dict]:
    """
    Extract common keywords/phrases from transactions using TF-IDF filtering.

    Args:
        transactions: List of transaction dictionaries
        min_frequency: Minimum number of occurrences to include
        max_doc_frequency: Maximum fraction of transactions a term can appear in (0.0-1.0)
                          Default 0.3 = exclude terms in >30% of transactions

    Returns:
        Dictionary of keyword -> {frequency, sample_transactions}
    """
    # First, identify high-frequency boilerplate terms to exclude
    excluded_terms = filter_terms_by_document_frequency(transactions, max_doc_frequency)

    keyword_counts = Counter()
    keyword_samples = {}

    for txn in transactions:
        merchant = txn.get('merchant', '')
        description = txn.get('description', '')

        # Prioritize merchant name
        if merchant and merchant.strip():
            keyword = clean_text(merchant)
            if keyword and len(keyword) > 2:  # At least 3 characters
                # Skip if it's a high-frequency term
                if keyword not in excluded_terms:
                    keyword_counts[keyword] += 1
                    if keyword not in keyword_samples:
                        keyword_samples[keyword] = []
                    if len(keyword_samples[keyword]) < 3:
                        keyword_samples[keyword].append({
                            'description': description,
                            'amount': txn.get('amount', 0),
                            'date': txn.get('date', '')
                        })

        # Also extract phrases from description
        cleaned_desc = clean_text(description)
        words = cleaned_desc.split()

        # Extract 1-3 word phrases
        for n in [1, 2, 3]:
            for i in range(len(words) - n + 1):
                phrase = ' '.join(words[i:i+n])
                phrase_words = phrase.split()

                # Skip if phrase contains only digits, punctuation, or very short terms
                if all(word.isdigit() or len(word) <= 2 for word in phrase_words):
                    continue

                # Count noise words in phrase
                noise_count = sum(1 for word in phrase_words if is_noise_word(word))

                # Stricter filtering for multi-word phrases:
                # Skip if ANY word is a noise word OR if phrase length check fails
                if n == 1:
                    # Single words: just check if it's a noise word
                    has_noise = is_noise_word(phrase)
                else:
                    # Multi-word: skip if ANY word is noise (very strict)
                    has_noise = noise_count > 0

                # Filter: length check, noise words, and high-frequency terms
                if (len(phrase) > 3 and
                    not has_noise and
                    phrase not in excluded_terms):
                    keyword_counts[phrase] += 1
                    if phrase not in keyword_samples:
                        keyword_samples[phrase] = []
                    if len(keyword_samples[phrase]) < 3:
                        keyword_samples[phrase].append({
                            'description': description,
                            'amount': txn.get('amount', 0),
                            'date': txn.get('date', '')
                        })

    # Filter by minimum frequency and return structured data
    result = {}
    for keyword, count in keyword_counts.items():
        if count >= min_frequency:
            result[keyword] = {
                'frequency': count,
                'sample_transactions': keyword_samples.get(keyword, [])[:3]
            }

    return result


def is_noise_word(word: str) -> bool:
    """Check if a word is common noise that should be filtered."""
    noise_words = {
        # Common words
        'the', 'and', 'for', 'from', 'with', 'ltd', 'limited', 'inc',
        'on', 'at', 'to', 'in', 'of', 'a', 'an', 'by', 'via', 'per',
        'no', 'ref', 'app', 'num', 'id',
        # Payment/transaction terms
        'payment', 'payments', 'card', 'debit', 'credit', 'purchase', 'transaction',
        'atm', 'cash', 'withdrawal', 'deposit', 'balance', 'fee', 'fees',
        'transfer', 'mandate', 'faster', 'amount', 'account', 'receipt',
        # Banking terminology
        'direct', 'standing', 'order', 'bacs', 'chaps', 'reference',
        'sort', 'code', 'iban', 'swift', 'payee', 'remittance',
        'regular', 'bill', 'cashback',
        # Common descriptors
        'online', 'mobile', 'branch', 'counter', 'automatic',
        'recurring', 'scheduled', 'pending', 'cleared', 'processed'
    }
    return word.lower() in noise_words


def calculate_tfidf_scores(transactions: List[Dict]) -> Dict[str, float]:
    """
    Calculate TF-IDF scores for all terms across transactions.

    TF-IDF (Term Frequency-Inverse Document Frequency) identifies terms that are:
    - Frequent in specific transactions (high TF)
    - Rare across all transactions (high IDF)

    This helps filter out banking boilerplate that appears everywhere.

    Args:
        transactions: List of transaction dictionaries

    Returns:
        Dictionary of term -> TF-IDF score (lower = more common/less useful)
    """
    if not transactions:
        return {}

    # Count document frequency (how many transactions contain each term)
    doc_frequency: Dict[str, int] = Counter()
    term_documents: Dict[str, Set[int]] = {}

    for idx, txn in enumerate(transactions):
        merchant = txn.get('merchant', '')
        description = txn.get('description', '')

        # Extract unique terms from this transaction
        text = f"{merchant} {description}"
        cleaned = clean_text(text)
        words = cleaned.split()

        # Track unique terms in this "document"
        unique_terms = set()

        # Single words
        for word in words:
            if len(word) > 2 and not is_noise_word(word):
                unique_terms.add(word)

        # 2-3 word phrases
        for n in [2, 3]:
            for i in range(len(words) - n + 1):
                phrase = ' '.join(words[i:i+n])
                if len(phrase) > 3:
                    unique_terms.add(phrase)

        # Update document frequency
        for term in unique_terms:
            doc_frequency[term] += 1
            if term not in term_documents:
                term_documents[term] = set()
            term_documents[term].add(idx)

    # Calculate IDF scores
    num_docs = len(transactions)
    idf_scores: Dict[str, float] = {}

    for term, df in doc_frequency.items():
        # IDF = log(total_documents / documents_containing_term)
        # Higher IDF = term appears in fewer documents = more distinctive
        idf = math.log(num_docs / df) if df > 0 else 0
        idf_scores[term] = idf

    return idf_scores


def filter_terms_by_document_frequency(
    transactions: List[Dict],
    max_doc_frequency: float = 0.3
) -> Set[str]:
    """
    Filter out terms that appear in too many transactions (likely boilerplate).

    Args:
        transactions: List of transaction dictionaries
        max_doc_frequency: Maximum fraction of documents a term can appear in (0.0-1.0)
                          Default 0.3 = filter terms appearing in >30% of transactions

    Returns:
        Set of terms that should be EXCLUDED (high frequency, low value)
    """
    if not transactions:
        return set()

    # Count how many transactions contain each term
    doc_frequency: Dict[str, int] = Counter()

    for txn in transactions:
        merchant = txn.get('merchant', '')
        description = txn.get('description', '')

        text = f"{merchant} {description}"
        cleaned = clean_text(text)
        words = cleaned.split()

        # Track unique terms in this transaction
        seen_terms = set()

        # Single words and phrases
        for word in words:
            if len(word) > 2:
                seen_terms.add(word)

        for n in [2, 3]:
            for i in range(len(words) - n + 1):
                phrase = ' '.join(words[i:i+n])
                if len(phrase) > 3:
                    seen_terms.add(phrase)

        # Increment document frequency for each unique term
        for term in seen_terms:
            doc_frequency[term] += 1

    # Identify high-frequency terms to exclude
    num_docs = len(transactions)
    threshold = int(num_docs * max_doc_frequency)

    excluded_terms = set()
    for term, count in doc_frequency.items():
        if count > threshold:
            excluded_terms.add(term)

    return excluded_terms


def calculate_similarity(keyword: str, target: str) -> float:
    """
    Calculate similarity score between two strings.

    Returns score from 0-100.
    """
    keyword_lower = keyword.lower()
    target_lower = target.lower()

    # Exact match
    if keyword_lower == target_lower:
        return 100.0

    # Substring match
    if keyword_lower in target_lower or target_lower in keyword_lower:
        return 90.0

    # Fuzzy matching using difflib
    ratio = difflib.SequenceMatcher(None, keyword_lower, target_lower).ratio()

    # Word overlap
    keyword_words = set(keyword_lower.split())
    target_words = set(target_lower.split())
    if keyword_words and target_words:
        overlap = len(keyword_words & target_words) / len(keyword_words | target_words)
        ratio = max(ratio, overlap)

    return ratio * 100


def suggest_category_for_keyword(keyword: str, category_rules: Dict[str, List[str]]) -> Tuple[str, float]:
    """
    Suggest the best category for a keyword using similarity matching.

    Args:
        keyword: The keyword to categorize
        category_rules: Dictionary of category -> list of keywords

    Returns:
        Tuple of (suggested_category, confidence_score)
    """
    best_category = 'Other'
    best_score = 0.0

    for category, rule_keywords in category_rules.items():
        if category == 'Other':
            continue

        # Calculate maximum similarity to any keyword in this category
        max_similarity = 0.0
        for rule_keyword in rule_keywords:
            similarity = calculate_similarity(keyword, rule_keyword)
            max_similarity = max(max_similarity, similarity)

        # Track best match
        if max_similarity > best_score:
            best_score = max_similarity
            best_category = category

    # Only suggest if confidence is reasonable
    if best_score < 40:
        best_category = 'Other'
        best_score = 0.0

    return best_category, best_score


def analyze_other_transactions(
    transactions: List[Dict],
    category_rules: Dict[str, List[str]],
    min_frequency: int = 3,
    min_confidence: float = 40.0,
    max_doc_frequency: float = 0.3
) -> List[Dict]:
    """
    Analyze 'Other' category transactions and generate keyword suggestions.

    Args:
        transactions: All transactions
        category_rules: Current categorization rules
        min_frequency: Minimum occurrences for a keyword
        min_confidence: Minimum confidence score to include suggestion
        max_doc_frequency: Maximum fraction of transactions a term can appear in

    Returns:
        List of suggestion dictionaries with keyword, frequency, category, confidence
    """
    # Filter to only 'Other' category transactions
    other_transactions = [txn for txn in transactions if txn.get('category') == 'Other']

    if not other_transactions:
        return []

    # Extract keywords with TF-IDF filtering
    keywords_data = extract_keywords_from_transactions(
        other_transactions,
        min_frequency,
        max_doc_frequency
    )

    # Generate suggestions with category matching
    suggestions = []
    for keyword, data in keywords_data.items():
        suggested_category, confidence = suggest_category_for_keyword(keyword, category_rules)

        # Only include if meets confidence threshold
        if confidence >= min_confidence:
            suggestions.append({
                'keyword': keyword,
                'frequency': data['frequency'],
                'suggested_category': suggested_category,
                'confidence': round(confidence, 1),
                'sample_transactions': [
                    txn['description'] for txn in data['sample_transactions']
                ]
            })

    # Sort by frequency (most common first)
    suggestions.sort(key=lambda x: x['frequency'], reverse=True)

    return suggestions


def get_keyword_suggestions(
    transactions: List[Dict],
    category_rules: Dict[str, List[str]],
    min_frequency: int = 3,
    min_confidence: float = 40.0,
    max_doc_frequency: float = 0.3
) -> Dict:
    """
    Main function to get keyword suggestions with metadata.

    Args:
        transactions: List of transaction dictionaries
        category_rules: Current categorization rules
        min_frequency: Minimum occurrences for a keyword
        min_confidence: Minimum confidence score to include suggestion
        max_doc_frequency: Maximum fraction of transactions a term can appear in

    Returns:
        Dictionary with suggestions and metadata
    """
    from datetime import datetime

    suggestions = analyze_other_transactions(
        transactions,
        category_rules,
        min_frequency,
        min_confidence,
        max_doc_frequency
    )

    other_count = len([txn for txn in transactions if txn.get('category') == 'Other'])

    return {
        'suggestions': suggestions,
        'total_other_transactions': other_count,
        'analyzed_at': datetime.now().isoformat(),
        'parameters': {
            'min_frequency': min_frequency,
            'min_confidence': min_confidence
        }
    }
