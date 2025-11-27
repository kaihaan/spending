"""
OpenAI Provider Implementation
Uses GPT models via OpenAI API
"""

import time
from typing import List, Dict, Optional
from openai import OpenAI, APIError

from .base_provider import BaseLLMProvider, TransactionEnrichment, ProviderStats


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT LLM provider implementation"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4-turbo",
        timeout: int = 30,
        debug: bool = False,
        api_base_url: Optional[str] = None
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: GPT model to use
            timeout: Request timeout in seconds
            debug: Enable debug logging
            api_base_url: Custom API base URL (for proxies)
        """
        super().__init__(api_key, model, timeout, debug)
        self.client = OpenAI(api_key=api_key)
        if api_base_url:
            self.client.base_url = api_base_url

    def validate_api_key(self) -> bool:
        """
        Validate OpenAI API key by making a simple request.

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
                print(f"OpenAI API validation failed: {e}")
            return False

    def enrich_transactions(
        self,
        transactions: List[Dict[str, str]],
        direction: str = "out"
    ) -> tuple[List[TransactionEnrichment], ProviderStats]:
        """
        Enrich transactions using GPT.

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
                print(f"OpenAI enrichment error: {e}")
            raise

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate cost for OpenAI API call.

        Uses pricing from OpenAI (as of latest update):
        - GPT-4 Turbo: $10/1M input, $30/1M output tokens
        - GPT-4o: $5/1M input, $15/1M output tokens
        - GPT-3.5 Turbo: $0.50/1M input, $1.50/1M output tokens

        Args:
            tokens_in: Input tokens used
            tokens_out: Output tokens generated

        Returns:
            Estimated cost in USD
        """
        # Model-specific pricing
        pricing = {
            "gpt-4-turbo": {"input": 0.010, "output": 0.030},
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        }

        # Find matching model pricing
        input_cost_per_1k = 0.010  # Default to GPT-4 Turbo
        output_cost_per_1k = 0.030

        for model_name, costs in pricing.items():
            if model_name in self.model.lower():
                input_cost_per_1k = costs["input"]
                output_cost_per_1k = costs["output"]
                break

        # Calculate total cost
        total_cost = (tokens_in / 1000) * input_cost_per_1k + (tokens_out / 1000) * output_cost_per_1k

        return round(total_cost, 6)
