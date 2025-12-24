"""
Ollama Provider Implementation
Uses local Ollama models (Mistral, Llama, etc.) via HTTP API
Supports any Ollama-compatible model running on localhost:11434
"""

import time
import requests
from typing import List, Dict, Optional

from .base_provider import BaseLLMProvider, TransactionEnrichment, ProviderStats, AccountInfo, LLMResponse


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider implementation"""

    OLLAMA_API_BASE = "http://localhost:11434"

    def __init__(
        self,
        api_key: str,
        model: str = "mistral:7b",
        timeout: int = 30,
        debug: bool = False,
        api_base_url: Optional[str] = None,
        cost_per_token: Optional[float] = None
    ):
        """
        Initialize Ollama provider.

        Args:
            api_key: Not used for Ollama (local), but required by base class
            model: Ollama model to use (e.g., "mistral:7b", "llama2:7b")
            timeout: Request timeout in seconds
            debug: Enable debug logging
            api_base_url: Custom Ollama base URL (default: http://localhost:11434)
            cost_per_token: Cost per token for tracking (default: Anthropic Sonnet pricing)
        """
        super().__init__(api_key, model, timeout, debug)

        # Ollama connection
        self.base_url = api_base_url or self.OLLAMA_API_BASE

        # Cost tracking for local models
        # Default: Anthropic Claude 3.5 Sonnet pricing ($0.003/1K input, $0.015/1K output)
        # Average: ~0.009/1K tokens = 0.000009 per token
        self.cost_per_token = cost_per_token or 0.000009

    def validate_api_key(self) -> bool:
        """
        Validate Ollama service is running and model is available.

        Returns:
            True if Ollama is accessible and model is loaded, False otherwise
        """
        try:
            # Check if Ollama service is running
            health_url = f"{self.base_url}/api/tags"
            response = requests.get(health_url, timeout=self.timeout)

            if response.status_code != 200:
                if self.debug:
                    print(f"Ollama health check failed with status {response.status_code}")
                return False

            # Check if model is available
            models = response.json().get("models", [])
            available_models = [m.get("name", "") for m in models]

            # Check if our model is available
            model_available = any(self.model in m for m in available_models)

            if self.debug and not model_available:
                print(f"Model '{self.model}' not found. Available: {available_models}")

            return model_available

        except requests.exceptions.RequestException as e:
            if self.debug:
                print(f"Ollama connection failed: {e}")
            return False

    def enrich_transactions(
        self,
        transactions: List[Dict[str, str]],
        direction: str = "out"
    ) -> tuple[List[TransactionEnrichment], ProviderStats]:
        """
        Enrich transactions using local Ollama model.

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
            # Combine system and user prompts for Ollama
            # Ollama doesn't use separate system message format
            full_prompt = f"{system_prompt}\n\n{user_prompt}"

            # Call Ollama API
            url = f"{self.base_url}/api/generate"

            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temperature for consistent results
                    "top_p": 0.9,
                    "top_k": 40,
                }
            }

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout * 2  # Longer timeout for local inference
            )

            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

            response_data = response.json()
            response_time_ms = (time.time() - start_time) * 1000

            # Get response text
            response_text = response_data.get("response", "")

            # Estimate tokens (1 token ≈ 4 characters)
            input_tokens = self._estimate_tokens(full_prompt)
            output_tokens = self._estimate_tokens(response_text)
            total_tokens = input_tokens + output_tokens

            # Parse enrichments
            enrichments = self._parse_enrichment_response(response_text, len(transactions))

            # Calculate cost based on token usage
            cost = total_tokens * self.cost_per_token

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
                print(f"Ollama enrichment error: {e}")
            raise

    def calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate estimated cost for Ollama inference.

        For local Ollama models, this is a tracking mechanism using a configurable
        cost per token. Default uses Anthropic Claude 3.5 Sonnet pricing as reference.

        Args:
            tokens_in: Input tokens used
            tokens_out: Output tokens generated

        Returns:
            Estimated cost in USD
        """
        total_tokens = tokens_in + tokens_out
        total_cost = total_tokens * self.cost_per_token

        return round(total_cost, 6)

    def get_account_info(self) -> AccountInfo:
        """
        Get account information for local Ollama instance.

        For Ollama, this checks if the service is running and returns
        information about local model availability and system metrics.

        Returns:
            AccountInfo with local instance details (models, VRAM usage)
        """
        try:
            # Check Ollama status - get available models
            tags_response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if tags_response.status_code != 200:
                return AccountInfo(
                    provider="ollama",
                    available=False,
                    error=f"Ollama service returned status {tags_response.status_code}"
                )

            models = tags_response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Get running models and VRAM usage via /api/ps
            running_models = []
            vram_used_gb = None
            try:
                ps_response = requests.get(f"{self.base_url}/api/ps", timeout=5)
                if ps_response.status_code == 200:
                    ps_data = ps_response.json()
                    running = ps_data.get("models", [])
                    running_models = [m.get("name", "") for m in running]
                    # Calculate total VRAM usage
                    total_vram = sum(m.get("size_vram", 0) for m in running)
                    if total_vram > 0:
                        vram_used_gb = round(total_vram / (1024 ** 3), 2)
            except Exception:
                pass  # ps endpoint may not be available in older versions

            extra_data = {
                "status": "running",
                "available_models": len(model_names),
                "running_models": len(running_models),
                "host": self.base_url
            }
            if vram_used_gb is not None:
                extra_data["vram_used_gb"] = vram_used_gb

            return AccountInfo(
                provider="ollama",
                available=True,
                balance=None,  # Local - no billing
                subscription_tier="Local (Free)",
                extra=extra_data
            )

        except requests.exceptions.RequestException as e:
            return AccountInfo(
                provider="ollama",
                available=False,
                error=f"Could not connect to Ollama at {self.base_url}: {str(e)}"
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
            # Combine system and user prompts for Ollama
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # Call Ollama API
            url = f"{self.base_url}/api/generate"

            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "top_k": 40,
                }
            }

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout * 2
            )

            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

            response_data = response.json()

            # Get response text
            content = response_data.get("response", "")

            # Estimate tokens
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
                cost=cost
            )

        except Exception as e:
            if self.debug:
                print(f"Ollama completion error: {e}")
            raise
