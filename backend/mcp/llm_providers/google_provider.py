"""
Google Gemini Provider Implementation
Uses Google Gemini models via Google API
"""

import time

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from .base_provider import (
    AccountInfo,
    BaseLLMProvider,
    LLMResponse,
    ProviderStats,
    TransactionEnrichment,
)


class GoogleProvider(BaseLLMProvider):
    """Google Gemini LLM provider implementation"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        timeout: int = 30,
        debug: bool = False,
        api_base_url: str | None = None,
    ):
        """
        Initialize Google Gemini provider.

        Args:
            api_key: Google API key
            model: Gemini model to use
            timeout: Request timeout in seconds
            debug: Enable debug logging
            api_base_url: Custom API base URL (for proxies)
        """
        super().__init__(api_key, model, timeout, debug)

        if genai is None:
            raise ImportError(
                "google-generativeai package required for Google provider"
            )

        genai.configure(api_key=api_key)
        self.model_obj = genai.GenerativeModel(model)

    def validate_api_key(self) -> bool:
        """
        Validate Google API key by making a simple request.

        Returns:
            True if valid, False otherwise
        """
        try:
            response = self.model_obj.generate_content("Say 'OK'")
            return bool(response.text)
        except Exception as e:
            if self.debug:
                print(f"Google API validation failed: {e}")
            return False

    def enrich_transactions(
        self, transactions: list[dict[str, str]], direction: str = "out"
    ) -> tuple[list[TransactionEnrichment], ProviderStats]:
        """
        Enrich transactions using Gemini.

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
                failure_count=0,
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(transactions, direction)

        # Combine system and user prompts for Gemini (which doesn't have separate system messages)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        start_time = time.time()

        try:
            response = self.model_obj.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                ),
            )

            response_time_ms = (time.time() - start_time) * 1000

            # Get response text
            response_text = response.text

            # Note: Google Gemini doesn't directly provide token counts in the response
            # We estimate based on text length
            input_tokens = self._estimate_tokens(full_prompt)
            output_tokens = self._estimate_tokens(response_text)
            total_tokens = input_tokens + output_tokens

            # Parse enrichments
            enrichments = self._parse_enrichment_response(
                response_text, len(transactions)
            )

            # Calculate cost
            cost = self.calculate_cost(input_tokens, output_tokens)

            stats = ProviderStats(
                tokens_used=total_tokens,
                estimated_cost=cost,
                response_time_ms=response_time_ms,
                batch_size=len(transactions),
                success_count=len(enrichments),
                failure_count=len(transactions) - len(enrichments),
            )

            return enrichments, stats

        except Exception as e:
            if self.debug:
                print(f"Google Gemini enrichment error: {e}")
            raise

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate cost for Google Gemini API call.

        Uses pricing from Google (as of latest update):
        - Gemini 1.5 Pro: $3.50/1M input, $10.50/1M output tokens
        - Gemini 1.5 Flash: $0.075/1M input, $0.30/1M output tokens
        - Gemini Pro: $0.5/1M input, $1.50/1M output tokens

        Args:
            tokens_in: Input tokens used
            tokens_out: Output tokens generated

        Returns:
            Estimated cost in USD
        """
        # Model-specific pricing
        pricing = {
            "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
            "gemini-1.5-flash": {"input": 0.000075, "output": 0.00030},
            "gemini-pro": {"input": 0.0005, "output": 0.0015},
            "gemini-pro-vision": {"input": 0.0005, "output": 0.0015},
        }

        # Find matching model pricing
        input_cost_per_1k = 0.000075  # Default to Flash (cheapest)
        output_cost_per_1k = 0.00030

        for model_name, costs in pricing.items():
            if model_name in self.model.lower():
                input_cost_per_1k = costs["input"]
                output_cost_per_1k = costs["output"]
                break

        # Calculate total cost
        total_cost = (tokens_in / 1000) * input_cost_per_1k + (
            tokens_out / 1000
        ) * output_cost_per_1k

        return round(total_cost, 6)

    def get_account_info(self) -> AccountInfo:
        """
        Fetch account information from Google.

        Note: Google Gemini does not provide a public API for checking
        account balance or usage.

        Returns:
            AccountInfo with available=False
        """
        return AccountInfo(
            provider="google",
            available=False,
            error="Google does not provide a public API for Gemini account balance/usage information. "
            "Check your account at console.cloud.google.com for billing details.",
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
            # Gemini doesn't have separate system messages, combine them
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            response = self.model_obj.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                ),
            )

            # Get response text
            content = response.text

            # Estimate tokens (Gemini doesn't always provide counts)
            input_tokens = self._estimate_tokens(full_prompt)
            output_tokens = self._estimate_tokens(content)
            total_tokens = input_tokens + output_tokens

            # Calculate cost
            cost = self.calculate_cost(input_tokens, output_tokens)

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost,
            )

        except Exception as e:
            if self.debug:
                print(f"Google Gemini completion error: {e}")
            raise
