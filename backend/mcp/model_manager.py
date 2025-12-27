"""
LLM Model Manager
Handles discovery, management, and persistence of LLM models for different providers.
Supports runtime model switching and custom model addition.
"""

import logging

import requests

import database

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages LLM models across all providers."""

    # Built-in models for each provider (from llm_config)
    BUILT_IN_MODELS = {
        "anthropic": [
            "claude-3-5-opus-20241022",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ],
        "openai": [
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-3.5-turbo",
        ],
        "google": [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro",
        ],
        "deepseek": [
            "deepseek-chat",
            "deepseek-v2",
        ],
        "ollama": [
            "mistral:7b",
            "llama2:7b",
            "llama2:13b",
            "neural-chat:7b",
        ],
    }

    OLLAMA_API_BASE = "http://localhost:11434"

    def __init__(self):
        """Initialize model manager."""
        self.debug = True

    def initialize_provider_models(self, provider: str) -> bool:
        """
        Initialize built-in models for a provider in the database.

        Args:
            provider: Provider name

        Returns:
            True if models were initialized
        """
        if provider not in self.BUILT_IN_MODELS:
            return False

        models = self.BUILT_IN_MODELS[provider]
        added = 0

        for model in models:
            if database.add_llm_model(provider, model, is_custom=False):
                added += 1

        if added > 0 and self.debug:
            logger.info(f"Initialized {added} models for provider: {provider}")

        return added > 0

    def get_available_models(
        self, provider: str, include_ollama_discovery: bool = True
    ) -> dict:
        """
        Get all available models for a provider.

        For Ollama: Auto-discovers models if running
        For cloud providers: Returns configured models

        Args:
            provider: Provider name
            include_ollama_discovery: Whether to query Ollama for installed models

        Returns:
            Dict with 'models', 'selected', 'available' lists
        """
        # Get models from database
        db_models = database.get_provider_models(provider)

        result = {
            "provider": provider,
            "selected": db_models.get("selected"),
            "built_in": db_models.get("built_in", []),
            "custom": db_models.get("custom", []),
            "available": [],  # Only for Ollama
        }

        # For Ollama, also discover installed models
        if provider == "ollama" and include_ollama_discovery:
            available = self.discover_ollama_models()
            result["available"] = available
            result["installed"] = any(m["installed"] for m in available)

        return result

    def discover_ollama_models(self) -> list[dict]:
        """
        Discover models currently installed in Ollama.

        Queries http://localhost:11434/api/tags to get list of installed models.

        Returns:
            List of dicts with 'name' and 'installed' keys
        """
        try:
            response = requests.get(f"{self.OLLAMA_API_BASE}/api/tags", timeout=5)

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])

                return [
                    {
                        "name": m.get("name", ""),
                        "installed": True,
                        "size": m.get("size", 0),
                        "modified": m.get("modified_at", ""),
                    }
                    for m in models
                ]
            if self.debug:
                logger.warning(f"Ollama API returned {response.status_code}")
            return []

        except requests.exceptions.RequestException as e:
            if self.debug:
                logger.warning(f"Failed to discover Ollama models: {e}")
            return []

    def add_custom_ollama_model(self, model_name: str, auto_pull: bool = True) -> dict:
        """
        Add a custom Ollama model and optionally pull it.

        Args:
            model_name: Model name (e.g., 'mistral:7b')
            auto_pull: Whether to attempt to pull the model from Ollama

        Returns:
            Dict with 'success', 'message', and 'model' keys
        """
        # Validate model format
        if ":" not in model_name:
            return {
                "success": False,
                "message": f'Invalid model format: {model_name}. Expected format: "model:tag" (e.g., "mistral:7b")',
                "model": None,
            }

        # Check if model already exists
        existing = database.get_provider_models("ollama")
        all_models = [m["name"] for m in existing["built_in"]] + [
            m["name"] for m in existing["custom"]
        ]

        if model_name in all_models:
            return {
                "success": False,
                "message": f"Model {model_name} already configured",
                "model": {"name": model_name, "is_custom": True},
            }

        # If auto_pull is enabled, try to pull the model
        if auto_pull:
            pull_result = self._pull_ollama_model(model_name)
            if not pull_result["success"]:
                return pull_result

        # Add to database
        database.add_llm_model("ollama", model_name, is_custom=True)

        return {
            "success": True,
            "message": f"Model {model_name} added successfully",
            "model": {"name": model_name, "is_custom": True},
        }

    def _pull_ollama_model(self, model_name: str) -> dict:
        """
        Pull a model from Ollama registry.

        Args:
            model_name: Model name to pull

        Returns:
            Dict with 'success' and 'message' keys
        """
        try:
            response = requests.post(
                f"{self.OLLAMA_API_BASE}/api/pull",
                json={"name": model_name},
                timeout=300,  # 5 minute timeout for pulling large models
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "message": f"Model {model_name} pulled successfully",
                }
            if response.status_code == 404:
                return {
                    "success": False,
                    "message": f"Model {model_name} not found in Ollama registry",
                }
            error_text = response.text[:200]  # First 200 chars of error
            return {
                "success": False,
                "message": f"Failed to pull model: {response.status_code} - {error_text}",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Pull request timed out (5 min). Model may still be downloading.",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Cannot connect to Ollama at http://localhost:11434. Make sure Ollama is running.",
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Error pulling model: {str(e)}"}

    def set_model(self, provider: str, model_name: str) -> dict:
        """
        Set the active model for a provider.

        Args:
            provider: Provider name
            model_name: Model to set as active

        Returns:
            Dict with 'success' and 'message' keys
        """
        success = database.set_selected_model(provider, model_name)

        if success:
            return {
                "success": True,
                "message": f"Model set to {model_name}",
                "model": model_name,
            }
        return {
            "success": False,
            "message": f"Model {model_name} not found for provider {provider}",
            "model": None,
        }

    def delete_custom_model(self, provider: str, model_name: str) -> dict:
        """
        Delete a custom model.

        Args:
            provider: Provider name
            model_name: Model to delete

        Returns:
            Dict with 'success' and 'message' keys
        """
        success = database.delete_custom_model(provider, model_name)

        if success:
            return {"success": True, "message": f"Model {model_name} deleted"}
        return {
            "success": False,
            "message": f"Cannot delete {model_name}: not a custom model or not found",
        }

    def check_ollama_health(self) -> dict:
        """
        Check if Ollama service is running and healthy.

        Returns:
            Dict with 'healthy', 'message', and 'models_count'
        """
        try:
            response = requests.get(f"{self.OLLAMA_API_BASE}/api/tags", timeout=2)

            if response.status_code == 200:
                data = response.json()
                models_count = len(data.get("models", []))
                return {
                    "healthy": True,
                    "message": f"Ollama is running with {models_count} models",
                    "models_count": models_count,
                }
            return {
                "healthy": False,
                "message": f"Ollama returned status {response.status_code}",
                "models_count": 0,
            }

        except requests.exceptions.ConnectionError:
            return {
                "healthy": False,
                "message": "Cannot connect to Ollama at http://localhost:11434",
                "models_count": 0,
            }
        except requests.exceptions.RequestException as e:
            return {
                "healthy": False,
                "message": f"Error checking Ollama: {str(e)}",
                "models_count": 0,
            }


# Global model manager instance
_manager: ModelManager | None = None


def get_model_manager() -> ModelManager:
    """
    Get or create the global model manager instance.

    Returns:
        ModelManager instance
    """
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager
