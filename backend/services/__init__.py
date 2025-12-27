"""
Services Package - Business Logic Layer

This package contains service modules that encapsulate business logic,
separating it from HTTP routing concerns.

Services can be called from:
- Flask routes (HTTP requests)
- CLI commands
- Background tasks (Celery)
- Tests

Available services:
- gmail_service: Gmail integration orchestration
- truelayer_service: TrueLayer bank integration orchestration
- amazon_service: Amazon integration (orders, returns, business API)
- enrichment_service: LLM enrichment orchestration
- rules_service: Category and merchant rule management
"""

from . import gmail_service, truelayer_service, amazon_service, enrichment_service, rules_service, apple_service, transactions_service, categories_service, huququllah_service, direct_debit_service, matching_service, settings_service, migrations_service, utilities_service

__all__ = [
    'gmail_service',
    'truelayer_service',
    'amazon_service',
    'enrichment_service',
    'rules_service',
    'apple_service',
    'transactions_service',
    'categories_service',
    'huququllah_service',
    'direct_debit_service',
    'matching_service',
    'settings_service',
    'migrations_service',
    'utilities_service',
]
