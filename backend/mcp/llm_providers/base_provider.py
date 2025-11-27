"""
Base LLM Provider Abstract Class
Defines the interface that all LLM provider implementations must follow
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json


@dataclass
class TransactionEnrichment:
    """Enriched transaction data from LLM"""
    primary_category: str
    subcategory: str
    merchant_clean_name: str
    merchant_type: str
    essential_discretionary: str  # "Essential" or "Discretionary"
    payment_method: str
    payment_method_subtype: Optional[str]
    purchase_date: str
    confidence_score: float  # 0-1
    raw_response: str  # Store original LLM response for debugging
    llm_provider: Optional[str] = None  # e.g., "anthropic", "openai"
    llm_model: Optional[str] = None  # e.g., "claude-3-5-sonnet-20241022"


@dataclass
class ProviderStats:
    """Statistics from a provider query"""
    tokens_used: int
    estimated_cost: float
    response_time_ms: float
    batch_size: int
    success_count: int
    failure_count: int


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, api_key: str, model: str, timeout: int = 30, debug: bool = False):
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
        self,
        transactions: List[Dict[str, str]],
        direction: str = "out"
    ) -> tuple[List[TransactionEnrichment], ProviderStats]:
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
        pass

    @abstractmethod
    def validate_api_key(self) -> bool:
        """
        Validate that the API key is valid and the provider is accessible.

        Returns:
            True if valid, False otherwise
        """
        pass

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
        pass

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt for transaction enrichment.

        Returns:
            System prompt string
        """
        return """You are a financial transaction classification expert. Your task is to analyze transaction descriptions and enrich them with structured data.

IMPORTANT: When "Details:" information is provided (e.g., product names from Amazon orders or apps from Apple), prioritize using that information for classification. This provides accurate insight into what was actually purchased and should override generic merchant-based assumptions.

For each transaction, you must return a JSON object with the following fields:
- primary_category: One of: Groceries, Transportation, Clothing, Dining, Entertainment, Shopping, Healthcare, Utilities, Income, Taxes, Subscriptions, Insurance, Education, Travel, Personal Care, Gifts, Pet Care, Home & Garden, Electronics, Sports & Outdoors, Books & Media, Office Supplies, Automotive, Banking Fees, Other
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

Return ONLY valid JSON. Return an array of objects, one per transaction.
Never include amounts or actual monetary values in your analysis."""

    def _build_user_prompt(self, transactions: List[Dict[str, str]], direction: str) -> str:
        """
        Build the user prompt with transactions to classify.

        Args:
            transactions: List of transaction dicts with keys:
                - description: Transaction description (required)
                - date: Transaction date (optional)
                - lookup_description: Product/service from Amazon/Apple lookup (optional)
                - merchant: Extracted/normalized merchant name (optional)
            direction: "in" for income, "out" for expenses

        Returns:
            User prompt string
        """
        transaction_lines = []
        for i, txn in enumerate(transactions, 1):
            desc = txn.get('description', '').strip()
            # Handle date as either string or date object
            date_val = txn.get('date', '')
            date = str(date_val).strip() if date_val else ''
            lookup_desc = txn.get('lookup_description', '').strip()
            merchant = txn.get('merchant', '').strip()

            direction_label = "INCOME" if direction.lower() == "in" else "EXPENSE"
            line = f"{i}. [{direction_label}] {desc}"

            # Add optional context
            context_parts = []
            if date:
                context_parts.append(f"Date: {date}")
            if merchant:
                context_parts.append(f"Merchant: {merchant}")
            if lookup_desc:
                context_parts.append(f"Details: {lookup_desc}")

            if context_parts:
                line += f" ({', '.join(context_parts)})"

            transaction_lines.append(line)

        return f"""Please classify the following transactions. Use the additional context (merchant name, product details from order history) if provided to improve accuracy:

{chr(10).join(transaction_lines)}

Return the enriched data as a JSON array with one object per transaction, in the same order."""

    def _parse_enrichment_response(self, response_text: str, num_transactions: int) -> List[TransactionEnrichment]:
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
                        essential_discretionary=item.get("essential_discretionary", "Discretionary"),
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
