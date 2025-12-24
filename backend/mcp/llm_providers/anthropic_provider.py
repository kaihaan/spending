"""
Anthropic Provider Implementation
Uses Claude models via Anthropic API
"""

import time
from typing import List, Dict, Optional
from datetime import datetime
import anthropic
import requests

from .base_provider import BaseLLMProvider, TransactionEnrichment, ProviderStats, AccountInfo, LLMResponse


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude LLM provider implementation"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        timeout: int = 30,
        debug: bool = False,
        api_base_url: Optional[str] = None,
        admin_api_key: Optional[str] = None
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            timeout: Request timeout in seconds
            debug: Enable debug logging
            api_base_url: Custom API base URL (for proxies)
            admin_api_key: Anthropic Admin API key for billing/usage data
        """
        super().__init__(api_key, model, timeout, debug)
        self.client = anthropic.Anthropic(api_key=api_key)
        self.admin_api_key = admin_api_key
        if api_base_url:
            self.client.base_url = api_base_url

    def validate_api_key(self) -> bool:
        """
        Validate Anthropic API key by making a simple request.

        Returns:
            True if valid, False otherwise
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Say 'OK'"}
                ]
            )
            return bool(response)
        except Exception as e:
            if self.debug:
                print(f"Anthropic API validation failed: {e}")
            return False

    def enrich_transactions(
        self,
        transactions: List[Dict[str, str]],
        direction: str = "out"
    ) -> tuple[List[TransactionEnrichment], ProviderStats]:
        """
        Enrich transactions using Claude.

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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                timeout=self.timeout
            )

            response_time_ms = (time.time() - start_time) * 1000

            # Extract usage information
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Get response text
            response_text = response.content[0].text

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
                print(f"Anthropic enrichment error: {e}")
            raise

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate cost for Anthropic API call.

        Uses pricing from Anthropic (as of latest update):
        - Claude 3.5 Sonnet: $3/1M input, $15/1M output tokens
        - Claude 3.5 Haiku: $0.80/1M input, $4/1M output tokens
        - Claude 3.5 Opus: $15/1M input, $75/1M output tokens

        Args:
            tokens_in: Input tokens used
            tokens_out: Output tokens generated

        Returns:
            Estimated cost in USD
        """
        # Model-specific pricing
        pricing = {
            "claude-3-5-opus": {"input": 0.015, "output": 0.075},
            "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-5-haiku": {"input": 0.0008, "output": 0.004},
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00024, "output": 0.00012},
        }

        # Find matching model pricing
        input_cost_per_1k = 0.003  # Default to Sonnet
        output_cost_per_1k = 0.015

        for model_name, costs in pricing.items():
            if model_name in self.model:
                input_cost_per_1k = costs["input"]
                output_cost_per_1k = costs["output"]
                break

        # Calculate total cost
        total_cost = (tokens_in / 1000) * input_cost_per_1k + (tokens_out / 1000) * output_cost_per_1k

        return round(total_cost, 6)

    def get_account_info(self) -> AccountInfo:
        """
        Fetch account billing info from Anthropic Admin API.

        Uses the /v1/organizations/cost_report endpoint to get
        current month's usage costs. Requires an Admin API key
        (starts with sk-ant-admin...) set via ANTHROPIC_ADMIN_API_KEY.

        Returns:
            AccountInfo with usage_this_month if admin key configured,
            otherwise guidance message to set the key.
        """
        # Check if admin API key is configured
        if not self.admin_api_key:
            return AccountInfo(
                provider="anthropic",
                available=False,
                error="Set ANTHROPIC_ADMIN_API_KEY for billing data"
            )

        try:
            # Get first day of current month
            now = datetime.now()
            month_start = datetime(now.year, now.month, 1).strftime("%Y-%m-%dT00:00:00Z")

            # Call cost report API
            response = requests.get(
                "https://api.anthropic.com/v1/organizations/cost_report",
                headers={
                    "x-api-key": self.admin_api_key,
                    "anthropic-version": "2023-06-01"
                },
                params={"starting_at": month_start, "bucket_width": "1d"},
                timeout=10
            )

            if response.status_code != 200:
                # Try to get error details from response
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", str(response.status_code))
                except Exception:
                    error_msg = str(response.status_code)
                return AccountInfo(
                    provider="anthropic",
                    available=False,
                    error=f"Admin API error: {error_msg}"
                )

            # Sum all costs (amount is in cents as string)
            data = response.json()
            total_cents = sum(
                float(result.get("amount", "0"))
                for bucket in data.get("data", [])
                for result in bucket.get("results", [])
            )
            total_dollars = total_cents / 100

            return AccountInfo(
                provider="anthropic",
                available=True,
                subscription_tier="Pay-as-you-go",
                usage_this_month=total_dollars
            )

        except Exception as e:
            if self.debug:
                print(f"Anthropic Admin API error: {e}")
            return AccountInfo(
                provider="anthropic",
                available=False,
                error=f"Failed to fetch: {str(e)}"
            )

    def complete(self, prompt: str, system_prompt: str = None) -> LLMResponse:
        """
        Simple completion API for single prompt.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with content and token/cost info
        """
        try:
            messages = [{"role": "user", "content": prompt}]

            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": messages,
                "timeout": self.timeout
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            # Extract usage information
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Get response text
            content = response.content[0].text

            # Calculate cost
            cost = self.calculate_cost(input_tokens, output_tokens)

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost
            )

        except Exception as e:
            if self.debug:
                print(f"Anthropic completion error: {e}")
            raise
