"""
Database Layer - Public API

This module provides the public interface for all database operations.
It imports and re-exports functions from domain-specific modules.

Usage:
    from database import get_db, save_gmail_receipt, get_truelayer_accounts
    # or
    import database

Organization:
    - base.py: Connection pool and utilities
    - gmail.py: Gmail receipt operations
    - truelayer.py: TrueLayer bank sync operations
    - amazon.py: Amazon order operations
    - apple.py: Apple transaction operations
    - categories.py: Category and rule operations
    - transactions.py: Transaction CRUD operations
    - matching.py: Cross-source matching operations
    - statistics.py: Analytics queries
    - webhooks.py: Webhook handling
    - import_jobs.py: Import job tracking
    - direct_debit.py: Direct debit mappings
    - merchant_normalization.py: Merchant name normalization
"""

# Core connection utilities (always available)
from .base import (
    init_pool,
    get_db,
    close_pool,
    execute_query,
    DB_CONFIG
)

# Domain-specific modules
# Gmail operations
from .gmail import (
    # Connection management
    save_gmail_connection,
    get_gmail_connection,
    get_gmail_connection_by_id,
    update_gmail_tokens,
    update_gmail_connection_status,
    update_gmail_history_id,
    delete_gmail_connection,
    # OAuth state
    store_gmail_oauth_state,
    get_gmail_oauth_state,
    delete_gmail_oauth_state,
    cleanup_expired_gmail_oauth_states,
    # Receipt operations
    save_gmail_receipt,
    save_gmail_receipt_bulk,
    get_gmail_receipts,
    get_gmail_receipt_by_id,
    get_gmail_receipt_by_message_id,
    get_unmatched_gmail_receipts,
    soft_delete_gmail_receipt,
    get_pending_gmail_receipts,
    delete_old_unmatched_gmail_receipts,
    # Email content
    save_gmail_email_content,
    save_gmail_email_content_bulk,
    get_gmail_email_content,
    get_receipt_with_email_content,
    get_receipts_by_domain_with_content,
    # Receipt updates
    update_gmail_receipt_parsed,
    update_gmail_receipt_status,
    update_gmail_receipt_pdf_status,
    update_gmail_receipt_from_pdf,
    # Matching
    save_gmail_match,
    get_gmail_matches_for_transaction,
    get_amazon_order_for_transaction,
    get_apple_transaction_for_match,
    get_gmail_matches,
    confirm_gmail_match,
    delete_gmail_match,
    # Sync jobs
    create_gmail_sync_job,
    update_gmail_sync_job_progress,
    update_gmail_sync_job_dates,
    complete_gmail_sync_job,
    cleanup_stale_gmail_jobs,
    get_gmail_sync_job,
    get_latest_gmail_sync_job,
    get_latest_active_gmail_sync_job,
    # Statistics
    get_gmail_statistics,
    get_source_coverage_dates,
    get_gmail_sender_pattern,
    # Merchant aggregation
    get_gmail_merchants_summary,
    get_receipts_by_domain,
    get_gmail_sender_patterns_list,
    get_transactions_for_matching,
    get_gmail_merchant_alias,
    # LLM queue
    get_unparseable_receipts_for_llm_queue,
    get_llm_queue_summary,
    update_receipt_llm_status,
    get_receipt_for_llm_processing,
    # PDF attachments
    save_pdf_attachment,
    get_pdf_attachment_by_hash,
    get_pdf_attachments_for_receipt,
    get_pdf_attachment_by_id,
    get_pdf_storage_stats,
    delete_pdf_attachment,
    # Error tracking
    save_gmail_error,
    save_gmail_parse_statistic,
    update_gmail_sync_job_stats,
    get_gmail_error_summary,
    get_gmail_merchant_statistics,
    # Matching jobs
    create_matching_job,
    update_matching_job_status,
    update_matching_job_progress,
    get_matching_job,
    get_active_matching_jobs,
    cleanup_stale_matching_jobs,
)

# TrueLayer operations
from .truelayer import (
    # Connection management
    get_user_connections,
    get_connection,
    get_connection_accounts,
    get_account_by_truelayer_id,
    save_bank_connection,
    update_connection_status,
    update_connection_provider_name,
    update_connection_provider,
    update_connection_last_synced,
    update_connection_tokens,
    update_account_last_synced,
    save_connection_account,
    # Transaction operations
    get_truelayer_transaction_by_id,
    get_truelayer_transaction_by_pk,
    insert_truelayer_transaction,
    get_all_truelayer_transactions,
    get_all_truelayer_transactions_with_enrichment,
    # Webhook operations
    insert_webhook_event,
    mark_webhook_processed,
    get_webhook_events,
    # Balance snapshots
    insert_balance_snapshot,
    get_latest_balance_snapshots,
    # Card operations
    save_connection_card,
    get_connection_cards,
    get_card_by_truelayer_id,
    update_card_last_synced,
    get_card_transaction_by_id,
    insert_truelayer_card_transaction,
    get_all_truelayer_card_transactions,
    insert_card_balance_snapshot,
    get_latest_card_balance_snapshots,
    # OAuth state
    store_oauth_state,
    get_oauth_state,
    delete_oauth_state,
    # Import job management
    create_import_job,
    get_import_job,
    update_import_job_status,
    add_import_progress,
    get_import_progress,
    mark_job_completed,
    get_user_import_history,
    get_job_transaction_ids,
    # Enrichment
    create_enrichment_job,
    update_enrichment_job,
    get_unenriched_truelayer_transactions,
    get_transaction_enrichment,
    count_enriched_truelayer_transactions,
)

# Categories & Rules operations
from .categories import (
    # Category promotion
    get_custom_categories,
    get_category_spending_summary,
    get_subcategory_spending,
    create_promoted_category,
    hide_category,
    unhide_category,
    get_mapped_subcategories,
    # Rules testing
    test_rule_pattern,
    get_rules_statistics,
    test_all_rules,
    apply_all_rules_to_transactions,
    # Normalized categories
    get_normalized_categories,
    get_normalized_category_by_id,
    get_normalized_category_by_name,
    create_normalized_category,
    update_normalized_category,
    delete_normalized_category,
    get_normalized_subcategories,
    get_normalized_subcategory_by_id,
    create_normalized_subcategory,
    update_normalized_subcategory,
    delete_normalized_subcategory,
    get_essential_category_names,
)

# Apple transactions operations
from .apple import (
    import_apple_transactions,
    get_apple_order_ids,
    get_apple_transactions,
    get_apple_transaction_by_id,
    get_apple_statistics,
    clear_apple_transactions,
)

# Direct debit mapping operations
from .direct_debit import (
    get_direct_debit_payees,
    get_direct_debit_mappings,
    save_direct_debit_mapping,
    delete_direct_debit_mapping,
    apply_direct_debit_mappings,
    detect_new_direct_debits,
)

# PDF attachment operations
from .pdf import (
    save_pdf_attachment,
    get_pdf_attachment_by_hash,
    get_pdf_attachments_for_receipt,
    get_pdf_attachment_by_id,
    get_pdf_storage_stats,
    delete_pdf_attachment,
)

# Amazon operations
from .amazon import (
    # Order management
    import_amazon_orders,
    get_amazon_orders,
    get_amazon_order_by_id,
    get_unmatched_truelayer_amazon_transactions,
    get_truelayer_transaction_for_matching,
    match_truelayer_amazon_transaction,
    get_unmatched_truelayer_apple_transactions,
    match_truelayer_apple_transaction,
    check_amazon_coverage,
    get_amazon_statistics,
    # Returns management
    import_amazon_returns,
    get_amazon_returns,
    link_return_to_transactions,
    get_returns_statistics,
    clear_amazon_returns,
    # Business account
    save_amazon_business_connection,
    get_amazon_business_connection,
    update_amazon_business_tokens,
    import_amazon_business_orders,
    import_amazon_business_line_items,
    get_amazon_business_orders,
    get_amazon_business_statistics,
    get_unmatched_truelayer_amazon_business_transactions,
    match_truelayer_amazon_business_transaction,
    delete_amazon_business_connection,
    clear_amazon_business_data,
    get_amazon_business_order_by_id,
    insert_amazon_business_order,
    insert_amazon_business_line_item,
    update_amazon_business_product_summaries,
)

# Enrichment operations
from .enrichment import (
    # Multi-source enrichment
    add_enrichment_source,
    get_transaction_enrichment_sources,
    get_all_enrichment_sources_for_transactions,
    set_primary_enrichment_source,
    get_primary_enrichment_description,
    get_llm_enrichment_context,
    get_batch_llm_enrichment_context,
    delete_enrichment_source,
    get_enrichment_source_full_details,
    clear_amazon_orders,
    # Enrichment status
    toggle_enrichment_required,
    set_enrichment_required,
    get_required_unenriched_transactions,
    clear_enrichment_required_after_success,
)

# Matching & consistency operations
from .matching import (
    get_category_rules,
    get_merchant_normalizations,
    increment_rule_usage,
    increment_merchant_normalization_usage,
    add_category_rule,
    add_merchant_normalization,
    delete_category_rule,
    delete_merchant_normalization,
    update_category_rule,
    update_merchant_normalization,
)

# Core transaction operations
from .transactions import (
    # Category keywords (legacy)
    get_all_categories,
    get_category_keywords,
    add_category_keyword,
    remove_category_keyword,
    create_custom_category,
    delete_custom_category,
    # Transaction enrichment utilities
    update_transaction_with_enrichment,
    is_transaction_enriched,
    get_enrichment_from_cache,
    cache_enrichment,
    log_enrichment_failure,
    # Account mappings
    get_all_account_mappings,
    add_account_mapping,
    update_account_mapping,
    delete_account_mapping,
    get_account_mapping_by_details,
    # Transaction operations
    update_truelayer_transaction_merchant,
    update_transaction_huququllah,
    get_unclassified_transactions,
    get_huququllah_summary,
    get_transaction_by_id,
    get_all_transactions,
)

# Temporary: Until all modules are created, provide backward compatibility
# by importing from the old database_postgres.py file
import sys
import os

# Add parent directory to path to import database_postgres
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    # Import all functions from old module for backward compatibility
    # This will be removed once all domain modules are created
    from database_postgres import *  # noqa: F401, F403
    print("⚠️  Database layer: Using legacy database_postgres.py (refactoring in progress)")
except ImportError:
    # If database_postgres doesn't exist yet, that's fine
    pass

# Public API
__all__ = [
    # Core utilities
    'init_pool',
    'get_db',
    'close_pool',
    'execute_query',
    'DB_CONFIG',

    # Gmail operations
    'save_gmail_connection',
    'get_gmail_connection',
    'get_gmail_connection_by_id',
    'update_gmail_tokens',
    'update_gmail_connection_status',
    'update_gmail_history_id',
    'delete_gmail_connection',
    'store_gmail_oauth_state',
    'get_gmail_oauth_state',
    'delete_gmail_oauth_state',
    'cleanup_expired_gmail_oauth_states',
    'save_gmail_receipt',
    'save_gmail_receipt_bulk',
    'get_gmail_receipts',
    'get_gmail_receipt_by_id',
    'get_gmail_receipt_by_message_id',
    'get_unmatched_gmail_receipts',
    'soft_delete_gmail_receipt',
    'get_pending_gmail_receipts',
    'delete_old_unmatched_gmail_receipts',
    'save_gmail_email_content',
    'save_gmail_email_content_bulk',
    'get_gmail_email_content',
    'get_receipt_with_email_content',
    'get_receipts_by_domain_with_content',
    'update_gmail_receipt_parsed',
    'update_gmail_receipt_status',
    'update_gmail_receipt_pdf_status',
    'update_gmail_receipt_from_pdf',
    'save_gmail_match',
    'get_gmail_matches_for_transaction',
    'get_amazon_order_for_transaction',
    'get_apple_transaction_for_match',
    'get_gmail_matches',
    'confirm_gmail_match',
    'delete_gmail_match',
    'create_gmail_sync_job',
    'update_gmail_sync_job_progress',
    'update_gmail_sync_job_dates',
    'complete_gmail_sync_job',
    'cleanup_stale_gmail_jobs',
    'get_gmail_sync_job',
    'get_latest_gmail_sync_job',
    'get_latest_active_gmail_sync_job',
    'get_gmail_statistics',
    'get_source_coverage_dates',
    'get_gmail_sender_pattern',
    'get_gmail_merchants_summary',
    'get_receipts_by_domain',
    'get_gmail_sender_patterns_list',
    'get_transactions_for_matching',
    'get_gmail_merchant_alias',
    'get_unparseable_receipts_for_llm_queue',
    'get_llm_queue_summary',
    'update_receipt_llm_status',
    'get_receipt_for_llm_processing',
    'save_pdf_attachment',
    'get_pdf_attachment_by_hash',
    'get_pdf_attachments_for_receipt',
    'get_pdf_attachment_by_id',
    'get_pdf_storage_stats',
    'delete_pdf_attachment',
    'save_gmail_error',
    'save_gmail_parse_statistic',
    'update_gmail_sync_job_stats',
    'get_gmail_error_summary',
    'get_gmail_merchant_statistics',
    'create_matching_job',
    'update_matching_job_status',
    'update_matching_job_progress',
    'get_matching_job',
    'get_active_matching_jobs',
    'cleanup_stale_matching_jobs',

    # TrueLayer operations
    'get_user_connections',
    'get_connection',
    'get_connection_accounts',
    'get_account_by_truelayer_id',
    'save_bank_connection',
    'update_connection_status',
    'update_connection_provider_name',
    'update_connection_provider',
    'update_connection_last_synced',
    'update_connection_tokens',
    'update_account_last_synced',
    'save_connection_account',
    'get_truelayer_transaction_by_id',
    'get_truelayer_transaction_by_pk',
    'insert_truelayer_transaction',
    'get_all_truelayer_transactions',
    'get_all_truelayer_transactions_with_enrichment',
    'insert_webhook_event',
    'mark_webhook_processed',
    'get_webhook_events',
    'insert_balance_snapshot',
    'get_latest_balance_snapshots',
    'save_connection_card',
    'get_connection_cards',
    'get_card_by_truelayer_id',
    'update_card_last_synced',
    'get_card_transaction_by_id',
    'insert_truelayer_card_transaction',
    'get_all_truelayer_card_transactions',
    'insert_card_balance_snapshot',
    'get_latest_card_balance_snapshots',
    'store_oauth_state',
    'get_oauth_state',
    'delete_oauth_state',
    'create_import_job',
    'get_import_job',
    'update_import_job_status',
    'add_import_progress',
    'get_import_progress',
    'mark_job_completed',
    'get_user_import_history',
    'get_job_transaction_ids',
    'create_enrichment_job',
    'update_enrichment_job',
    'get_unenriched_truelayer_transactions',
    'get_transaction_enrichment',
    'count_enriched_truelayer_transactions',

    # Categories & Rules operations
    'get_custom_categories',
    'get_category_spending_summary',
    'get_subcategory_spending',
    'create_promoted_category',
    'hide_category',
    'unhide_category',
    'get_mapped_subcategories',
    'test_rule_pattern',
    'get_rules_statistics',
    'test_all_rules',
    'apply_all_rules_to_transactions',
    'get_normalized_categories',
    'get_normalized_category_by_id',
    'get_normalized_category_by_name',
    'create_normalized_category',
    'update_normalized_category',
    'delete_normalized_category',
    'get_normalized_subcategories',
    'get_normalized_subcategory_by_id',
    'create_normalized_subcategory',
    'update_normalized_subcategory',
    'delete_normalized_subcategory',
    'get_essential_category_names',

    # Apple transactions operations
    'import_apple_transactions',
    'get_apple_order_ids',
    'get_apple_transactions',
    'get_apple_transaction_by_id',
    'get_apple_statistics',
    'clear_apple_transactions',

    # Direct debit mapping operations
    'get_direct_debit_payees',
    'get_direct_debit_mappings',
    'save_direct_debit_mapping',
    'delete_direct_debit_mapping',
    'apply_direct_debit_mappings',
    'detect_new_direct_debits',

    # PDF attachment operations
    'save_pdf_attachment',
    'get_pdf_attachment_by_hash',
    'get_pdf_attachments_for_receipt',
    'get_pdf_attachment_by_id',
    'get_pdf_storage_stats',
    'delete_pdf_attachment',

    # Amazon operations
    'import_amazon_orders',
    'get_amazon_orders',
    'get_amazon_order_by_id',
    'get_unmatched_truelayer_amazon_transactions',
    'get_truelayer_transaction_for_matching',
    'match_truelayer_amazon_transaction',
    'get_unmatched_truelayer_apple_transactions',
    'match_truelayer_apple_transaction',
    'check_amazon_coverage',
    'get_amazon_statistics',
    'import_amazon_returns',
    'get_amazon_returns',
    'link_return_to_transactions',
    'get_returns_statistics',
    'clear_amazon_returns',
    'save_amazon_business_connection',
    'get_amazon_business_connection',
    'update_amazon_business_tokens',
    'import_amazon_business_orders',
    'import_amazon_business_line_items',
    'get_amazon_business_orders',
    'get_amazon_business_statistics',
    'get_unmatched_truelayer_amazon_business_transactions',
    'match_truelayer_amazon_business_transaction',
    'delete_amazon_business_connection',
    'clear_amazon_business_data',
    'get_amazon_business_order_by_id',
    'insert_amazon_business_order',
    'insert_amazon_business_line_item',
    'update_amazon_business_product_summaries',

    # Enrichment operations
    'add_enrichment_source',
    'get_transaction_enrichment_sources',
    'get_all_enrichment_sources_for_transactions',
    'set_primary_enrichment_source',
    'get_primary_enrichment_description',
    'get_llm_enrichment_context',
    'get_batch_llm_enrichment_context',
    'delete_enrichment_source',
    'get_enrichment_source_full_details',
    'clear_amazon_orders',
    'toggle_enrichment_required',
    'set_enrichment_required',
    'get_required_unenriched_transactions',
    'clear_enrichment_required_after_success',

    # Matching & consistency operations
    'get_category_rules',
    'get_merchant_normalizations',
    'increment_rule_usage',
    'increment_merchant_normalization_usage',
    'add_category_rule',
    'add_merchant_normalization',
    'delete_category_rule',
    'delete_merchant_normalization',
    'update_category_rule',
    'update_merchant_normalization',

    # Core transaction operations
    'get_all_categories',
    'get_category_keywords',
    'add_category_keyword',
    'remove_category_keyword',
    'create_custom_category',
    'delete_custom_category',
    'update_transaction_with_enrichment',
    'is_transaction_enriched',
    'get_enrichment_from_cache',
    'cache_enrichment',
    'log_enrichment_failure',
    'get_all_account_mappings',
    'add_account_mapping',
    'update_account_mapping',
    'delete_account_mapping',
    'get_account_mapping_by_details',
    'update_truelayer_transaction_merchant',
    'update_transaction_huququllah',
    'get_unclassified_transactions',
    'get_huququllah_summary',
    'get_transaction_by_id',
    'get_all_transactions',
]
