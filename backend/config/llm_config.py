"""
LLM Configuration Management
Handles environment variables, validation, and provider configuration
"""

import os
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path

# Try to load from .env file if available
try:
    from dotenv import load_dotenv
    # Load from .env in the backend directory
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, will use environment variables directly
    pass


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"


class LLMModel(str, Enum):
    """Supported LLM models by provider"""
    # Anthropic
    CLAUDE_OPUS = "claude-3-5-opus-20241022"
    CLAUDE_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_HAIKU = "claude-3-5-haiku-20241022"

    # OpenAI
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_4O = "gpt-4o"
    GPT_3_5_TURBO = "gpt-3.5-turbo"

    # Google
    GEMINI_PRO = "gemini-pro"
    GEMINI_FLASH = "gemini-1.5-flash"
    GEMINI_PRO_VISION = "gemini-pro-vision"

    # Deepseek
    DEEPSEEK_V3 = "deepseek-chat"
    DEEPSEEK_V2 = "deepseek-v2"

    # Ollama (local models)
    OLLAMA_MISTRAL_7B = "mistral:7b"
    OLLAMA_LLAMA2_7B = "llama2:7b"
    OLLAMA_LLAMA2_13B = "llama2:13b"
    OLLAMA_NEURAL_CHAT = "neural-chat:7b"


@dataclass
class LLMConfig:
    """LLM Configuration object"""
    provider: LLMProvider
    model: str
    api_key: str
    api_base_url: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    batch_size_initial: int = 10
    batch_size_override: Optional[int] = None  # Override provider-specific batch size
    cache_enabled: bool = True
    debug: bool = False
    ollama_cost_per_token: Optional[float] = None  # Cost per token for local Ollama models

    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()

    def validate(self):
        """Validate LLM configuration"""
        if not self.provider:
            raise ValueError("LLM_PROVIDER is required")

        if not self.api_key:
            raise ValueError(f"API key required for provider: {self.provider}")

        if self.timeout <= 0:
            raise ValueError("LLM_TIMEOUT must be greater than 0")

        if self.batch_size_initial <= 0:
            raise ValueError("LLM_BATCH_SIZE_INITIAL must be greater than 0")

        # Provider-specific validation
        if self.provider == LLMProvider.ANTHROPIC:
            if not self.model.startswith("claude"):
                raise ValueError(f"Invalid Anthropic model: {self.model}")

        elif self.provider == LLMProvider.OPENAI:
            valid_models = ["gpt-4", "gpt-3.5-turbo"]
            if not any(m in self.model for m in valid_models):
                raise ValueError(f"Invalid OpenAI model: {self.model}")

        elif self.provider == LLMProvider.GOOGLE:
            if not self.model.startswith("gemini"):
                raise ValueError(f"Invalid Google model: {self.model}")

        elif self.provider == LLMProvider.DEEPSEEK:
            if not ("deepseek" in self.model.lower()):
                raise ValueError(f"Invalid Deepseek model: {self.model}")

        elif self.provider == LLMProvider.OLLAMA:
            # Ollama models are flexible, just ensure model name is provided
            # Common formats: "mistral:7b", "llama2:7b", etc.
            if not self.model or ":" not in self.model:
                raise ValueError(f"Invalid Ollama model format: {self.model} (expected format: 'model:tag' like 'mistral:7b')")

            # Validate cost per token if provided
            if self.ollama_cost_per_token is not None and self.ollama_cost_per_token < 0:
                raise ValueError(f"Ollama cost per token must be non-negative: {self.ollama_cost_per_token}")


def load_llm_config() -> Optional[LLMConfig]:
    """
    Load LLM configuration from environment variables.

    Environment Variables:
    - LLM_PROVIDER: anthropic|openai|google|deepseek|ollama (required if LLM enrichment enabled)
    - LLM_MODEL: Model name (required if LLM enrichment enabled)
    - LLM_API_KEY: API key (required if LLM enrichment enabled; can be dummy for Ollama)
    - LLM_API_BASE_URL: Custom API endpoint (optional)
    - LLM_TIMEOUT: Request timeout in seconds (default: 30)
    - LLM_MAX_RETRIES: Number of retries (default: 3)
    - LLM_BATCH_SIZE_INITIAL: Initial batch size (default: 10)
    - LLM_BATCH_SIZE: Override batch size for all providers (optional)
    - LLM_CACHE_ENABLED: Enable caching (default: true)
    - LLM_DEBUG: Debug mode (default: false)
    - LLM_OLLAMA_COST_PER_TOKEN: Cost per token for tracking local Ollama inference (optional)

    Returns:
        LLMConfig object or None if LLM enrichment is not configured
    """
    # Reload .env file to pick up any changes
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
    except (ImportError, Exception):
        pass

    provider_str = os.getenv("LLM_PROVIDER", "").lower()

    # If no provider is set, LLM enrichment is disabled
    if not provider_str:
        return None

    # Validate provider
    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        raise ValueError(
            f"Invalid LLM_PROVIDER: {provider_str}. "
            f"Must be one of: {', '.join([p.value for p in LLMProvider])}"
        )

    # Get API key - try generic LLM_API_KEY first, then provider-specific keys
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        # Try provider-specific API keys
        provider_api_key_map = {
            LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            LLMProvider.OPENAI: "OPENAI_API_KEY",
            LLMProvider.GOOGLE: "GOOGLE_API_KEY",
            LLMProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
            LLMProvider.OLLAMA: "OLLAMA_API_KEY",  # Optional for Ollama (local)
        }
        api_key_env_var = provider_api_key_map.get(provider)
        if api_key_env_var:
            api_key = os.getenv(api_key_env_var, "").strip()

        # Ollama doesn't require an API key (local inference)
        if not api_key and provider == LLMProvider.OLLAMA:
            api_key = "ollama-local"  # Dummy key for local Ollama

    # Get model with provider-specific defaults
    model = os.getenv("LLM_MODEL", "").strip()
    if not model:
        # Use provider-specific defaults
        model_defaults = {
            LLMProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
            LLMProvider.OPENAI: "gpt-4-turbo",
            LLMProvider.GOOGLE: "gemini-1.5-flash",
            LLMProvider.DEEPSEEK: "deepseek-chat",
            LLMProvider.OLLAMA: "mistral:7b",
        }
        model = model_defaults.get(provider, "")
        if not model:
            raise ValueError(f"LLM_MODEL is required for provider: {provider.value}")

    # Optional config
    api_base_url = os.getenv("LLM_API_BASE_URL")
    timeout = int(os.getenv("LLM_TIMEOUT", "30"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
    batch_size_initial = int(os.getenv("LLM_BATCH_SIZE_INITIAL", "10"))

    # Batch size override (applies to all providers)
    batch_size_override = None
    batch_size_env = os.getenv("LLM_BATCH_SIZE", "").strip()
    if batch_size_env:
        batch_size_override = int(batch_size_env)

    cache_enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
    debug = os.getenv("LLM_DEBUG", "false").lower() == "true"

    # Ollama-specific configuration
    ollama_cost_per_token = None
    if provider == LLMProvider.OLLAMA:
        cost_env = os.getenv("LLM_OLLAMA_COST_PER_TOKEN", "").strip()
        if cost_env:
            ollama_cost_per_token = float(cost_env)

    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base_url=api_base_url,
        timeout=timeout,
        max_retries=max_retries,
        batch_size_initial=batch_size_initial,
        batch_size_override=batch_size_override,
        cache_enabled=cache_enabled,
        debug=debug,
        ollama_cost_per_token=ollama_cost_per_token,
    )

    return config


def get_provider_info(provider: LLMProvider) -> Dict[str, Any]:
    """Get provider-specific information like rate limits, costs, etc."""

    provider_info = {
        LLMProvider.ANTHROPIC: {
            "name": "Anthropic",
            "rate_limit_rpm": None,  # Varies by tier
            "rate_limit_tpm": None,
            "cost_per_1k_input_tokens": 0.003,
            "cost_per_1k_output_tokens": 0.015,
            "recommended_batch_size": 10,
            "max_batch_size": 50,
            "supported_models": [m.value for m in LLMModel if "CLAUDE" in m.name],
        },
        LLMProvider.OPENAI: {
            "name": "OpenAI",
            "rate_limit_rpm": 3500,
            "rate_limit_tpm": 90000,
            "cost_per_1k_input_tokens": 0.01,
            "cost_per_1k_output_tokens": 0.03,
            "recommended_batch_size": 15,
            "max_batch_size": 100,
            "supported_models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
        },
        LLMProvider.GOOGLE: {
            "name": "Google Gemini",
            "rate_limit_rpm": 60,
            "rate_limit_tpm": None,
            "cost_per_1k_input_tokens": 0.00035,
            "cost_per_1k_output_tokens": 0.0007,
            "recommended_batch_size": 5,
            "max_batch_size": 30,
            "supported_models": ["gemini-1.5-flash", "gemini-pro", "gemini-pro-vision"],
        },
        LLMProvider.DEEPSEEK: {
            "name": "Deepseek",
            "rate_limit_rpm": None,
            "rate_limit_tpm": None,
            "cost_per_1k_input_tokens": 0.00014,
            "cost_per_1k_output_tokens": 0.00028,
            "recommended_batch_size": 20,
            "max_batch_size": 200,
            "supported_models": ["deepseek-chat"],
        },
        LLMProvider.OLLAMA: {
            "name": "Ollama (Local)",
            "rate_limit_rpm": None,  # No rate limits for local
            "rate_limit_tpm": None,
            "cost_per_1k_input_tokens": 0.000003,  # Default: Anthropic Sonnet avg
            "cost_per_1k_output_tokens": 0.000009,
            "recommended_batch_size": 5,
            "max_batch_size": 50,
            "supported_models": ["mistral:7b", "llama2:7b", "llama2:13b", "neural-chat:7b"],
            "info": "Local models via Ollama - no API key required, free inference"
        },
    }

    return provider_info.get(provider, {})
