"""
Deepseek Provider Implementation
Uses Deepseek models via Deepseek API (OpenAI-compatible)
"""

import time
from typing import List, Dict, Optional
from openai import OpenAI, APIError

from .base_provider import BaseLLMProvider, TransactionEnrichment, ProviderStats


class DeepseekProvider(BaseLLMProvider):
    """Deepseek LLM provider implementation"""

    DEEPSEEK_API_BASE = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        timeout: int = 30,
        debug: bool = False,
        api_base_url: Optional[str] = None
    ):
        """
        Initialize Deepseek provider.

        Args:
            api_key: Deepseek API key
            model: Deepseek model to use
            timeout: Request timeout in seconds
            debug: Enable debug logging
            api_base_url: Custom API base URL (default: https://api.deepseek.com)
        """
        super().__init__(api_key, model, timeout, debug)

        # Use provided API base URL or default
        base_url = api_base_url or self.DEEPSEEK_API_BASE

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

    def validate_api_key(self) -> bool:
        """
        Validate Deepseek API key by making a simple request.

        Returns:
            True if valid, False otherwise
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Say 'OK'"}
                ],
                timeout=self.timeout
            )
            return bool(response)
        except APIError as e:
            if self.debug:
                print(f"Deepseek API validation failed: {e}")
            return False

    def enrich_transactions(
        self,
        transactions: List[Dict[str, str]],
        direction: str = "out"
    ) -> tuple[List[TransactionEnrichment], ProviderStats]:
        """
        Enrich transactions using Deepseek.

        Args:
            transactions: List of transaction dicts
            direction: "in" for income, "out" for expenses

        Returns:
            Tuple of (enriched_list, stats)
        """
        if not transactions:
            return [], ProviderStats(
                tokens_used=0,
                estimated_cost=0.0,
                response_time_ms=0,
                batch_size=0,
                success_count=0,
                failure_count=0
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(transactions, direction)

        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.3,  # Lower temperature for more consistent results
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                timeout=self.timeout
            )

            response_time_ms = (time.time() - start_time) * 1000

            # Extract usage information
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens

            # Get response text
            response_text = response.choices[0].message.content

            # Parse enrichments
            enrichments = self._parse_enrichment_response(response_text, len(transactions))

            # Calculate cost
            cost = self.calculate_cost(input_tokens, output_tokens)

            stats = ProviderStats(
                tokens_used=total_tokens,
                estimated_cost=cost,
                response_time_ms=response_time_ms,
                batch_size=len(transactions),
                success_count=len(enrichments),
                failure_count=len(transactions) - len(enrichments)
            )

            return enrichments, stats

        except Exception as e:
            if self.debug:
                print(f"Deepseek enrichment error: {e}")
            raise

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate cost for Deepseek API call.

        Uses pricing from Deepseek (as of latest update):
        - Deepseek Chat: $0.14/1M input, $0.28/1M output tokens
        - Deepseek-V3: $0.14/1M input, $0.28/1M output tokens

        These are among the cheapest available.

        Args:
            tokens_in: Input tokens used
            tokens_out: Output tokens generated

        Returns:
            Estimated cost in USD
        """
        # Deepseek pricing - very affordable
        input_cost_per_1k = 0.00014  # $0.14 per 1M input tokens
        output_cost_per_1k = 0.00028  # $0.28 per 1M output tokens

        # Calculate total cost
        total_cost = (tokens_in / 1000) * input_cost_per_1k + (tokens_out / 1000) * output_cost_per_1k

        return round(total_cost, 6)
