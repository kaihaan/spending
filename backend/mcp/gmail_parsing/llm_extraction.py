"""
Gmail LLM-based Extraction

LLM-powered receipt data extraction as a fallback method.
Supports multiple LLM providers (Anthropic, OpenAI, Google, DeepSeek, Ollama).
"""

import json
from typing import Optional

from mcp.logging_config import get_logger
from .utilities import normalize_merchant_name

# Initialize logger
logger = get_logger(__name__)


def extract_with_llm(
    subject: str,
    sender: str,
    body_text: str
) -> Optional[dict]:
    """
    Extract receipt data using LLM.

    Uses the configured LLM provider to parse unstructured receipt emails.
    Returns parsed data with cost tracking.

    Args:
        subject: Email subject
        sender: Sender email/name
        body_text: Plain text body

    Returns:
        Parsed receipt dictionary or None
    """
    try:
        from config.llm_config import load_llm_config, LLMProvider
        from mcp.llm_providers import (
            AnthropicProvider,
            OpenAIProvider,
            GoogleProvider,
            DeepseekProvider,
            OllamaProvider,
        )
    except ImportError as e:
        logger.warning(f"LLM providers not available: {e}")
        return None

    config = load_llm_config()
    if not config:
        logger.debug("LLM not configured for Gmail parsing")
        return None

    # Build provider
    providers = {
        LLMProvider.ANTHROPIC: AnthropicProvider,
        LLMProvider.OPENAI: OpenAIProvider,
        LLMProvider.GOOGLE: GoogleProvider,
        LLMProvider.DEEPSEEK: DeepseekProvider,
        LLMProvider.OLLAMA: OllamaProvider,
    }

    ProviderClass = providers.get(config.provider)
    if not ProviderClass:
        logger.warning(f"Unknown LLM provider: {config.provider}")
        return None

    try:
        provider_kwargs = {
            "api_key": config.api_key,
            "model": config.model,
            "timeout": config.timeout,
            "debug": config.debug,
            "api_base_url": config.api_base_url,
        }

        if config.provider == LLMProvider.OLLAMA:
            provider_kwargs["cost_per_token"] = config.ollama_cost_per_token
        if config.provider == LLMProvider.ANTHROPIC:
            provider_kwargs["admin_api_key"] = config.anthropic_admin_api_key

        provider = ProviderClass(**provider_kwargs)
    except Exception as e:
        logger.error(f"Failed to initialize LLM provider: {e}", exc_info=True)
        return None

    # Truncate body to avoid token limits (max ~2000 chars)
    truncated_body = body_text[:2000] if body_text else ""

    # Build prompt for receipt extraction with enhanced line item details
    prompt = f"""Extract receipt/purchase information from this email. Return JSON only, no explanation.

Subject: {subject}
From: {sender}
Body:
{truncated_body}

Extract and return this JSON structure (use null for missing fields):
{{
  "merchant_name": "Store name",
  "order_id": "Order/confirmation number",
  "total_amount": 12.34,
  "currency_code": "GBP",
  "receipt_date": "YYYY-MM-DD",
  "line_items": [
    {{
      "name": "Full product name as shown",
      "description": "Brief description of what this item IS (e.g., 'wireless earbuds', 'monthly subscription')",
      "category_hint": "groceries|electronics|clothing|entertainment|food_delivery|transport|subscription|services|health|home|other",
      "quantity": 1,
      "price": 12.34
    }}
  ]
}}

Important:
- total_amount must be a number (no currency symbols)
- receipt_date must be YYYY-MM-DD format
- For line_items: extract ALL items if visible, include price per item when shown
- category_hint should be one of: groceries, electronics, clothing, entertainment, food_delivery, transport, subscription, services, health, home, other
- Return only valid JSON, no markdown or explanation"""

    try:
        response = provider.complete(prompt)

        if not response or not response.content:
            return None

        # Parse JSON from response
        content = response.content.strip()

        # Handle markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()

        parsed = json.loads(content)

        # Calculate cost in cents
        cost_cents = 0
        if hasattr(response, 'total_tokens') and hasattr(response, 'cost_per_1k_tokens'):
            cost_cents = int((response.total_tokens / 1000) * response.cost_per_1k_tokens * 100)
        elif hasattr(response, 'cost'):
            cost_cents = int(response.cost * 100)

        return {
            'merchant_name': parsed.get('merchant_name'),
            'merchant_name_normalized': normalize_merchant_name(parsed.get('merchant_name')),
            'order_id': parsed.get('order_id'),
            'total_amount': float(parsed['total_amount']) if parsed.get('total_amount') else None,
            'currency_code': parsed.get('currency_code', 'GBP'),
            'receipt_date': parsed.get('receipt_date'),
            'line_items': parsed.get('line_items'),
            'parse_method': 'llm',
            'parse_confidence': 70,
            'parsing_status': 'parsed',
            'llm_cost_cents': cost_cents,
        }

    except json.JSONDecodeError as e:
        logger.warning(f"LLM returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}", exc_info=True)
        return None
