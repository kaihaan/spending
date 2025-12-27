"""
Gmail LLM Queue Manager

Handles queuing and processing of unparseable Gmail receipts for LLM parsing.
Key features:
- Cost estimation before processing
- Re-fetches emails from Gmail (no body storage required)
- Progress tracking during batch processing
"""

from typing import Generator, Optional
import database_postgres as database
from config.llm_config import load_llm_config, LLMProvider
from mcp.gmail_auth import get_gmail_credentials
from mcp.gmail_client import (
    build_gmail_service,
    get_message_content,
    parse_sender_email,
    extract_sender_domain,
)
from mcp.gmail_parsing.orchestrator import parse_receipt_content


# Estimated output tokens for a parsed receipt JSON response
ESTIMATED_OUTPUT_TOKENS = 200

# Provider-specific cost per 1M tokens (input/output)
# These are approximations - actual costs may vary
PROVIDER_COSTS = {
    LLMProvider.ANTHROPIC: {
        'input_per_1m': 3.0,   # Claude Haiku pricing
        'output_per_1m': 15.0,
    },
    LLMProvider.OPENAI: {
        'input_per_1m': 0.15,   # GPT-3.5-turbo pricing
        'output_per_1m': 0.60,
    },
    LLMProvider.GOOGLE: {
        'input_per_1m': 0.0,   # Gemini free tier
        'output_per_1m': 0.0,
    },
    LLMProvider.DEEPSEEK: {
        'input_per_1m': 0.14,   # DeepSeek pricing
        'output_per_1m': 0.28,
    },
    LLMProvider.OLLAMA: {
        'input_per_1m': 0.0,   # Local - no API cost
        'output_per_1m': 0.0,
    },
}


def estimate_tokens_from_text(text: str) -> int:
    """
    Estimate token count from text.
    Rough approximation: 1 token ≈ 4 characters.
    Cap at 2000 to match typical context limits.
    """
    if not text:
        return 100  # Minimum estimate
    return min(len(text) // 4, 2000)


def get_current_llm_config() -> dict:
    """
    Get current LLM configuration for cost estimation.

    Returns:
        Dict with provider, model, and cost info
    """
    try:
        config = load_llm_config()
        if not config:
            raise ValueError("LLM not configured")
        costs = PROVIDER_COSTS.get(config.provider, PROVIDER_COSTS[LLMProvider.ANTHROPIC])

        return {
            'provider': config.provider.value,
            'model': config.model,
            'input_cost_per_1m': costs['input_per_1m'],
            'output_cost_per_1m': costs['output_per_1m'],
            'is_free': costs['input_per_1m'] == 0 and costs['output_per_1m'] == 0,
        }
    except Exception as e:
        print(f"⚠️ Could not get LLM config: {e}")
        return {
            'provider': 'unknown',
            'model': 'unknown',
            'input_cost_per_1m': 3.0,
            'output_cost_per_1m': 15.0,
            'is_free': False,
        }


def estimate_llm_cost_cents(text_length: int) -> int:
    """
    Estimate LLM cost in cents for parsing text of given length.

    Args:
        text_length: Character count of text to parse

    Returns:
        Estimated cost in cents (rounded up)
    """
    config = get_current_llm_config()

    if config['is_free']:
        return 0

    input_tokens = estimate_tokens_from_text('x' * text_length)
    output_tokens = ESTIMATED_OUTPUT_TOKENS

    # Calculate cost: (tokens / 1M) * cost_per_1M * 100 (to cents)
    input_cost = (input_tokens / 1_000_000) * config['input_cost_per_1m'] * 100
    output_cost = (output_tokens / 1_000_000) * config['output_cost_per_1m'] * 100

    total_cents = input_cost + output_cost

    # Round up to nearest cent, minimum 1 cent if not free
    return max(1, int(total_cents + 0.99)) if total_cents > 0 else 0


def estimate_receipt_cost(receipt: dict) -> int:
    """
    Estimate LLM cost for a specific receipt based on snippet length.

    Since we don't have the full body stored, we estimate based on:
    - Snippet length (typically 200-300 chars)
    - Average email body is ~10x snippet

    Args:
        receipt: Receipt dict with 'snippet' field

    Returns:
        Estimated cost in cents
    """
    snippet = receipt.get('snippet', '')
    # Estimate full body as 10x snippet length (conservative)
    estimated_body_length = max(len(snippet) * 10, 2000)
    return estimate_llm_cost_cents(estimated_body_length)


def get_queue_with_estimates(connection_id: int = None, limit: int = 100) -> dict:
    """
    Get unparseable receipts with cost estimates.

    Args:
        connection_id: Optional filter by Gmail connection
        limit: Maximum receipts to return

    Returns:
        Dict with receipts list and summary
    """
    receipts = database.get_unparseable_receipts_for_llm_queue(
        connection_id=connection_id,
        limit=limit
    )

    # Add cost estimate to each receipt
    total_estimated_cost = 0
    for receipt in receipts:
        estimated_cost = estimate_receipt_cost(receipt)
        receipt['estimated_cost_cents'] = estimated_cost
        total_estimated_cost += estimated_cost

    llm_config = get_current_llm_config()

    summary = database.get_llm_queue_summary(connection_id)
    summary['total_estimated_cost_cents'] = total_estimated_cost
    summary['provider'] = llm_config['provider']
    summary['model'] = llm_config['model']
    summary['is_free_provider'] = llm_config['is_free']

    return {
        'receipts': receipts,
        'summary': summary,
    }


def fetch_and_parse_receipt_with_llm(receipt_id: int) -> dict:
    """
    Fetch email from Gmail and parse with LLM.

    Args:
        receipt_id: Database receipt ID

    Returns:
        Dict with success, parsed_data, actual_cost_cents, error
    """
    # Get receipt info
    receipt = database.get_receipt_for_llm_processing(receipt_id)
    if not receipt:
        return {
            'success': False,
            'error': 'Receipt not found',
            'receipt_id': receipt_id,
        }

    connection_id = receipt['gmail_connection_id']
    message_id = receipt['message_id']

    try:
        # Mark as processing
        database.update_receipt_llm_status(receipt_id, 'processing')

        # Get Gmail credentials
        access_token, refresh_token = get_gmail_credentials(connection_id)

        # Build Gmail service
        service = build_gmail_service(access_token, refresh_token)

        # Fetch email content
        message = get_message_content(service, message_id)

        if not message:
            database.update_receipt_llm_status(receipt_id, 'failed')
            return {
                'success': False,
                'error': 'Could not fetch email from Gmail',
                'receipt_id': receipt_id,
            }

        # Parse sender info
        sender_email, sender_name = parse_sender_email(message.get('from', ''))
        sender_domain = extract_sender_domain(sender_email)

        # Parse with LLM enabled
        parsed_data = parse_receipt_content(
            html_body=message.get('body_html'),
            text_body=message.get('body_text'),
            subject=message.get('subject', ''),
            sender_email=sender_email,
            sender_domain=sender_domain,
            sender_name=sender_name,
            list_unsubscribe=message.get('list_unsubscribe', ''),
            skip_llm=False  # Enable LLM for this parse
        )

        # Get actual cost from parsed data
        actual_cost = parsed_data.get('llm_cost_cents', 0)

        # Check if parsing succeeded
        if parsed_data.get('parsing_status') == 'parsed':
            # Update with parsed data
            database.update_receipt_llm_status(
                receipt_id,
                status='completed',
                actual_cost=actual_cost,
                parsed_data=parsed_data
            )

            return {
                'success': True,
                'receipt_id': receipt_id,
                'parsed_data': parsed_data,
                'actual_cost_cents': actual_cost,
            }
        else:
            # LLM parsing also failed
            database.update_receipt_llm_status(
                receipt_id,
                status='failed',
                actual_cost=actual_cost
            )

            return {
                'success': False,
                'receipt_id': receipt_id,
                'error': parsed_data.get('parsing_error', 'LLM parsing failed'),
                'actual_cost_cents': actual_cost,
            }

    except Exception as e:
        print(f"❌ LLM queue processing error for receipt {receipt_id}: {e}")
        database.update_receipt_llm_status(receipt_id, 'failed')
        return {
            'success': False,
            'receipt_id': receipt_id,
            'error': str(e),
        }


def process_llm_queue(
    receipt_ids: list,
    connection_id: int = None
) -> Generator[dict, None, dict]:
    """
    Process multiple receipts with LLM, yielding progress updates.

    Args:
        receipt_ids: List of receipt IDs to process
        connection_id: Optional connection ID for credential lookup

    Yields:
        Progress dicts with status, processed, succeeded, failed, current_receipt

    Returns:
        Final results dict
    """
    total = len(receipt_ids)
    processed = 0
    succeeded = 0
    failed = 0
    total_cost = 0
    results = []

    yield {
        'status': 'started',
        'total': total,
        'processed': 0,
        'succeeded': 0,
        'failed': 0,
        'total_cost_cents': 0,
    }

    for receipt_id in receipt_ids:
        # Process this receipt
        result = fetch_and_parse_receipt_with_llm(receipt_id)
        results.append(result)

        processed += 1
        if result.get('success'):
            succeeded += 1
        else:
            failed += 1

        total_cost += result.get('actual_cost_cents', 0)

        yield {
            'status': 'processing',
            'total': total,
            'processed': processed,
            'succeeded': succeeded,
            'failed': failed,
            'total_cost_cents': total_cost,
            'current_receipt': {
                'id': receipt_id,
                'success': result.get('success'),
                'error': result.get('error'),
            },
        }

    final_result = {
        'status': 'completed',
        'total': total,
        'processed': processed,
        'succeeded': succeeded,
        'failed': failed,
        'total_cost_cents': total_cost,
        'results': results,
    }

    yield final_result
    return final_result
