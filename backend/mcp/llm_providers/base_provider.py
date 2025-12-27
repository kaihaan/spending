"""
Base LLM Provider Abstract Class
Defines the interface that all LLM provider implementations must follow
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class TransactionEnrichment:
    """Enriched transaction data from LLM"""

    primary_category: str
    subcategory: str
    merchant_clean_name: str
    merchant_type: str
    essential_discretionary: str  # "Essential" or "Discretionary"
    payment_method: str
    payment_method_subtype: str | None
    purchase_date: str
    confidence_score: float  # 0-1
    raw_response: str  # Store original LLM response for debugging
    llm_provider: str | None = None  # e.g., "anthropic", "openai"
    llm_model: str | None = None  # e.g., "claude-3-5-sonnet-20241022"


@dataclass
class ProviderStats:
    """Statistics from a provider query"""

    tokens_used: int
    estimated_cost: float
    response_time_ms: float
    batch_size: int
    success_count: int
    failure_count: int


@dataclass
class AccountInfo:
    """Provider account information for billing/subscription status"""

    provider: str
    available: bool  # Whether account info API is available for this provider
    balance: float | None = None  # Remaining credits/balance in USD
    subscription_tier: str | None = None  # e.g., "Free", "Pay-as-you-go", "Scale"
    usage_this_month: float | None = None  # Current month spend in USD
    error: str | None = None  # Error message if fetch failed
    extra: dict[str, Any] | None = None  # Provider-specific extra data


@dataclass
class LLMResponse:
    """Simple response from LLM completion"""

    content: str  # The text content of the response
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0  # Cost in USD


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(
        self, api_key: str, model: str, timeout: int = 30, debug: bool = False
    ):
        """
        Initialize LLM provider.

        Args:
            api_key: API key for the provider
            model: Model name/ID
            timeout: Request timeout in seconds
            debug: Enable debug logging
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.debug = debug

    @abstractmethod
    def enrich_transactions(
        self, transactions: list[dict[str, str]], direction: str = "out"
    ) -> tuple[list[TransactionEnrichment], ProviderStats]:
        """
        Enrich a batch of transactions.

        Args:
            transactions: List of transaction dicts with:
                - description: Transaction description
                - (optional) date: Transaction date
            direction: "in" for income, "out" for expenses

        Returns:
            Tuple of (enriched_list, stats)
        """

    @abstractmethod
    def validate_api_key(self) -> bool:
        """
        Validate that the API key is valid and the provider is accessible.

        Returns:
            True if valid, False otherwise
        """

    @abstractmethod
    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate estimated cost for a request.

        Args:
            tokens_in: Input tokens
            tokens_out: Output tokens

        Returns:
            Estimated cost in USD
        """

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        Fetch account information from the provider.

        Returns:
            AccountInfo object with balance, tier, and usage data.
            If the provider doesn't support account APIs, returns
            AccountInfo with available=False and an error message.
        """

    @abstractmethod
    def complete(self, prompt: str, system_prompt: str = None) -> LLMResponse:
        """
        Simple completion API for single prompt.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with content and token/cost info
        """

    # Base categories (fallback only - prefer normalized_categories table)
    BASE_CATEGORIES = [
        "Groceries",
        "Transportation",
        "Clothing",
        "Dining",
        "Entertainment",
        "Shopping",
        "Healthcare",
        "Utilities",
        "Income",
        "Taxes",
        "Subscriptions",
        "Insurance",
        "Education",
        "Travel",
        "Personal Care",
        "Gifts",
        "Pet Care",
        "Home & Garden",
        "Electronics",
        "Sports & Outdoors",
        "Books & Media",
        "Office Supplies",
        "Automotive",
        "Banking Fees",
        "Other",
    ]

    def _get_active_categories(self) -> list[str]:
        """
        Get the list of active categories for LLM enrichment.
        Returns: List of category names from normalized_categories table (active only)
        Falls back to BASE_CATEGORIES if database unavailable.
        """
        try:
            # Import here to avoid circular imports
            import os
            import sys

            sys.path.insert(
                0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            import database_postgres as database

            # Get active categories from normalized table
            categories_data = database.get_normalized_categories(active_only=True)
            if categories_data:
                return [cat["name"] for cat in categories_data]

        except Exception as e:
            # If we can't load from database, use base categories
            if self.debug:
                print(f"Could not load normalized categories: {e}")

        return list(self.BASE_CATEGORIES)

    def _get_category_context(self) -> str:
        """
        Get category names with descriptions for LLM context.
        Returns formatted string with categories and their descriptions.
        """
        try:
            # Import here to avoid circular imports
            import os
            import sys

            sys.path.insert(
                0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            import database_postgres as database

            # Get active categories with descriptions
            categories_data = database.get_normalized_categories(active_only=True)
            if categories_data:
                lines = []
                for cat in categories_data:
                    if cat.get("description"):
                        lines.append(f"- {cat['name']}: {cat['description']}")
                    else:
                        lines.append(f"- {cat['name']}")
                return "\n".join(lines)

        except Exception as e:
            if self.debug:
                print(f"Could not load category context: {e}")

        # Fallback to simple list
        return "\n".join(f"- {cat}" for cat in self.BASE_CATEGORIES)

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt for transaction enrichment.

        Returns:
            System prompt string
        """
        # Get dynamic category list with descriptions for better LLM context
        categories = self._get_active_categories()
        category_list = ", ".join(categories)
        category_context = self._get_category_context()

        return f"""You are a financial transaction classification expert. Your task is to analyze transaction descriptions and enrich them with structured data.

IMPORTANT: When enrichment details are provided (product names from Amazon, apps from Apple, or email receipt contents), prioritize using that information for classification. This provides accurate insight into what was actually purchased and should override generic merchant-based assumptions. Multiple sources may be provided for the same transaction - consider all of them.

AVAILABLE CATEGORIES:
{category_context}

For each transaction, you must return a JSON object with the following fields:
- primary_category: One of: {category_list}
- subcategory: More specific classification (e.g., "Coffee Shop", "Supermarket", "Taxi Service", "Electronics - Audio Equipment")
- merchant_clean_name: Standardized merchant name (e.g., "Amazon", "Starbucks", "TfL", not "AMZN*MKTP" or "TESCO STORES")
- merchant_type: Type of merchant (e.g., "supermarket", "coffee shop", "public transport", "utility provider", "council tax", "restaurant", "music streaming", "airline", "electronics retailer")
- essential_discretionary: Either "Essential" (necessary for living) or "Discretionary" (optional/luxury)
- payment_method: The payment method (Credit Card, Debit Card, Faster Payment, Bank Giro, Apple Pay, Direct Debit, Transfer, Cash, Check)
- payment_method_subtype: Subtype if applicable (e.g., "Apple Pay via Zettle", "Apple Pay via Sumup", "Visa", "Mastercard")
- purchase_date: The date the purchase was made (YYYY-MM-DD), may differ from the transaction date shown with the bank
- confidence_score: Your confidence in this classification from 0.0 to 1.0

CLASSIFICATION GUIDELINES:
- When you see product/app details: Use them to determine the most specific category (e.g., "Music streamer" → Electronics, "Coffee maker" → Appliances → Electronics)
- For marketplace transactions without product details: Default to "Shopping" category with "Online Marketplace" subcategory
- Always be specific: Instead of generic "Shopping", use "Electronics", "Sports & Outdoors", "Books & Media", etc. when the product type is clear
- Use the category descriptions above to understand what each category encompasses

Return ONLY valid JSON. Return an array of objects, one per transaction.
Never include amounts or actual monetary values in your analysis."""

    # Source type to human-readable label mapping for LLM prompts
    SOURCE_TYPE_LABELS = {
        "amazon": "Amazon Products",
        "amazon_business": "Amazon Business",
        "apple": "Apple/App Store",
        "gmail": "Email Receipt",
        "manual": "Manual Entry",
    }

    def _build_user_prompt(
        self, transactions: list[dict[str, str]], direction: str
    ) -> str:
        """
        Build the user prompt with transactions to classify.

        Args:
            transactions: List of transaction dicts with keys:
                - description: Transaction description (required)
                - date: Transaction date (optional)
                - merchant: Extracted/normalized merchant name (optional)
                - enrichment_sources: List of enrichment source dicts (optional)
                    Each source has: source_type, description, order_id, confidence
            direction: "in" for income, "out" for expenses

        Returns:
            User prompt string
        """
        transaction_lines = []
        for i, txn in enumerate(transactions, 1):
            desc = txn.get("description", "").strip()
            # Handle date as either string or date object
            date_val = txn.get("date", "")
            date = str(date_val).strip() if date_val else ""
            merchant = txn.get("merchant", "").strip()

            direction_label = "INCOME" if direction.lower() == "in" else "EXPENSE"
            line = f"{i}. [{direction_label}] {desc}"

            # Add optional context
            context_parts = []
            if date:
                context_parts.append(f"Date: {date}")
            if merchant:
                context_parts.append(f"Merchant: {merchant}")

            # Add all enrichment sources with labeled context
            enrichment_sources = txn.get("enrichment_sources", [])
            if enrichment_sources and isinstance(enrichment_sources, list):
                for source in enrichment_sources:
                    source_type = source.get("source_type", "unknown")
                    source_desc = source.get("description", "").strip()
                    if source_desc:
                        label = self.SOURCE_TYPE_LABELS.get(source_type, "Details")
                        context_parts.append(f"{label}: {source_desc}")

            if context_parts:
                line += f" ({', '.join(context_parts)})"

            transaction_lines.append(line)

        return f"""Please classify the following transactions. Use the additional context (merchant name, product details from order history, email receipts) if provided to improve accuracy:

{chr(10).join(transaction_lines)}

Return the enriched data as a JSON array with one object per transaction, in the same order."""

    def _parse_enrichment_response(
        self, response_text: str, num_transactions: int
    ) -> list[TransactionEnrichment]:
        """
        Parse enrichment response from LLM.

        Args:
            response_text: Raw response from LLM
            num_transactions: Expected number of transactions

        Returns:
            List of TransactionEnrichment objects
        """
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = response_text
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())

            # Ensure it's a list
            if not isinstance(data, list):
                data = [data]

            enrichments = []
            for item in data:
                enrichments.append(
                    TransactionEnrichment(
                        primary_category=item.get("primary_category", "Other"),
                        subcategory=item.get("subcategory", ""),
                        merchant_clean_name=item.get("merchant_clean_name", ""),
                        merchant_type=item.get("merchant_type", ""),
                        essential_discretionary=item.get(
                            "essential_discretionary", "Discretionary"
                        ),
                        payment_method=item.get("payment_method", "Unknown"),
                        payment_method_subtype=item.get("payment_method_subtype"),
                        purchase_date=item.get("purchase_date", ""),
                        confidence_score=float(item.get("confidence_score", 0.5)),
                        raw_response=response_text,
                    )
                )

            return enrichments

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            if self.debug:
                print(f"Error parsing enrichment response: {e}")
                print(f"Response was: {response_text}")
            raise ValueError(f"Failed to parse LLM response: {e}")

    @staticmethod
    def _estimate_tokens(text: str, is_output: bool = False) -> int:
        """
        Rough estimate of tokens (1 token ≈ 4 characters).
        This is a rough approximation; actual token counts may vary.

        Args:
            text: Text to estimate tokens for
            is_output: Whether this is output tokens (may have different ratio)

        Returns:
            Estimated token count
        """
        # Rough approximation: 1 token ≈ 4 characters
        return max(1, len(text) // 4)
