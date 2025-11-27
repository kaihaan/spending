"""
LLM Transaction Enricher Tool
Main orchestrator for transaction enrichment using configurable LLM providers
Handles batching, caching, error handling, and cost tracking
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import database
from config.llm_config import LLMConfig, LLMProvider, load_llm_config
from mcp.llm_providers import (
    BaseLLMProvider,
    AnthropicProvider,
    OpenAIProvider,
    GoogleProvider,
    DeepseekProvider,
    OllamaProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentStats:
    """Statistics from a complete enrichment operation"""
    total_transactions: int
    successful_enrichments: int
    failed_enrichments: int
    cached_hits: int
    api_calls_made: int
    total_tokens_used: int
    total_cost: float
    retry_queue: List[int]  # Transaction IDs to retry


class LLMEnricher:
    """Main LLM enrichment orchestrator"""

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize LLM enricher.

        Args:
            config: LLM configuration. If None, loads from environment.
        """
        self.config = config or load_llm_config()

        if not self.config:
            raise ValueError(
                "LLM enrichment not configured. Set LLM_PROVIDER and LLM_API_KEY environment variables."
            )

        # Set debug early so it's always available
        self.debug = self.config.debug
        self.provider = self._get_provider()

    def _get_provider(self) -> BaseLLMProvider:
        """
        Get configured LLM provider instance.

        Returns:
            Instantiated LLM provider
        """
        providers = {
            LLMProvider.ANTHROPIC: AnthropicProvider,
            LLMProvider.OPENAI: OpenAIProvider,
            LLMProvider.GOOGLE: GoogleProvider,
            LLMProvider.DEEPSEEK: DeepseekProvider,
            LLMProvider.OLLAMA: OllamaProvider,
        }

        ProviderClass = providers.get(self.config.provider)
        if not ProviderClass:
            raise ValueError(f"Unknown LLM provider: {self.config.provider}")

        # Build provider kwargs
        provider_kwargs = {
            "api_key": self.config.api_key,
            "model": self.config.model,
            "timeout": self.config.timeout,
            "debug": self.debug,
            "api_base_url": self.config.api_base_url,
        }

        # Add Ollama-specific parameters
        if self.config.provider == LLMProvider.OLLAMA:
            provider_kwargs["cost_per_token"] = self.config.ollama_cost_per_token

        return ProviderClass(**provider_kwargs)

    def enrich_transactions(
        self,
        transaction_ids: Optional[List[int]] = None,
        direction: str = "out",
        force_refresh: bool = False,
    ) -> EnrichmentStats:
        """
        Enrich transactions with LLM.

        Args:
            transaction_ids: Specific transaction IDs to enrich. If None, enriches all.
            direction: "in" for income, "out" for expenses
            force_refresh: Bypass cache and re-query LLM

        Returns:
            EnrichmentStats with results
        """
        # Get transactions to enrich
        if transaction_ids:
            transactions = [database.get_transaction_by_id(tid) for tid in transaction_ids]
            transactions = [t for t in transactions if t]
        else:
            transactions = database.get_all_transactions()

        if not transactions:
            logger.info("No transactions to enrich")
            return EnrichmentStats(
                total_transactions=0,
                successful_enrichments=0,
                failed_enrichments=0,
                cached_hits=0,
                api_calls_made=0,
                total_tokens_used=0,
                total_cost=0.0,
                retry_queue=[],
            )

        logger.info(f"Enriching {len(transactions)} transactions")

        # Separate transactions into cached, already enriched, and non-cached
        cached_enrichments = {}
        txns_to_enrich = []
        already_enriched = 0

        for txn in transactions:
            # Skip if already enriched in database (unless force_refresh)
            if not force_refresh and database.is_transaction_enriched(txn["id"]):
                already_enriched += 1
                logger.debug(f"Transaction {txn['id']} already enriched, skipping")
                continue

            # Check cache if enabled
            if self.config.cache_enabled and not force_refresh:
                cached = database.get_enrichment_from_cache(
                    txn["description"], direction
                )
                if cached:
                    cached_enrichments[txn["id"]] = cached
                    continue

            # Otherwise, need to enrich
            txns_to_enrich.append(txn)

        if already_enriched > 0:
            logger.info(f"Skipped {already_enriched} already-enriched transactions")

        # Enrich non-cached transactions in batches
        enrichment_map = {}  # transaction_id -> enrichment
        retry_queue = []
        total_tokens = 0
        total_cost = 0.0
        api_calls = 0

        if txns_to_enrich:
            # Calculate dynamic batch size
            batch_size = self._calculate_batch_size(len(txns_to_enrich))

            # Process in batches
            for i in range(0, len(txns_to_enrich), batch_size):
                batch = txns_to_enrich[i : i + batch_size]
                logger.debug(f"Processing batch {i // batch_size + 1} with {len(batch)} transactions")

                try:
                    # Prepare batch data with lookup context
                    batch_data = []
                    for txn in batch:
                        txn_data = {
                            "description": txn["description"],
                            "date": txn.get("date", ""),
                        }

                        # Include lookup_description if available (from Amazon/Apple matches)
                        if txn.get("lookup_description"):
                            txn_data["lookup_description"] = txn["lookup_description"]

                        # Include merchant name if already normalized
                        if txn.get("merchant"):
                            txn_data["merchant"] = txn["merchant"]

                        batch_data.append(txn_data)

                    # Query LLM
                    enrichments, stats = self.provider.enrich_transactions(
                        batch_data, direction
                    )

                    api_calls += 1
                    total_tokens += stats.tokens_used
                    total_cost += stats.estimated_cost

                    # Map enrichments back to transactions
                    for txn, enrichment in zip(batch, enrichments):
                        # Add provider and model info to enrichment
                        enrichment.llm_provider = self.config.provider.value
                        enrichment.llm_model = self.config.model
                        enrichment_map[txn["id"]] = enrichment

                        # Cache if enabled
                        if self.config.cache_enabled:
                            database.cache_enrichment(
                                description=txn["description"],
                                direction=direction,
                                enrichment=enrichment,
                                provider=self.config.provider.value,
                                model=self.config.model,
                            )

                except Exception as e:
                    logger.error(f"Error enriching batch: {e}")
                    # Mark these transactions for retry
                    for txn in batch:
                        retry_queue.append(txn["id"])
                        database.log_enrichment_failure(
                            transaction_id=txn["id"],
                            description=txn["description"],
                            error_type="api_error",
                            error_message=str(e),
                            provider=self.config.provider.value,
                        )

        # Combine cached and newly enriched
        enrichment_map.update(cached_enrichments)

        # Update transactions with enriched data
        successful_count = 0
        for txn_id, enrichment in enrichment_map.items():
            try:
                # Determine enrichment source: 'llm' for API-enriched, 'cache' for cached
                enrichment_source = 'cache' if txn_id in cached_enrichments else 'llm'
                database.update_transaction_with_enrichment(
                    txn_id, enrichment,
                    enrichment_source=enrichment_source
                )
                successful_count += 1
            except Exception as e:
                logger.error(f"Error saving enrichment for transaction {txn_id}: {e}")
                retry_queue.append(txn_id)

        return EnrichmentStats(
            total_transactions=len(transactions),
            successful_enrichments=successful_count,
            failed_enrichments=len(transactions) - successful_count,
            cached_hits=len(cached_enrichments),
            api_calls_made=api_calls,
            total_tokens_used=total_tokens,
            total_cost=total_cost,
            retry_queue=list(set(retry_queue)),  # Remove duplicates
        )

    def _calculate_batch_size(self, num_transactions: int) -> int:
        """
        Calculate dynamic batch size based on provider and transaction count.

        Args:
            num_transactions: Number of transactions to process

        Returns:
            Optimal batch size
        """
        # Check for explicit batch size override first
        if self.config.batch_size_override is not None:
            batch_size = self.config.batch_size_override
            if self.debug:
                logger.debug(f"Using override batch size: {batch_size}")
            return batch_size

        # Base batch size from config
        batch_size = self.config.batch_size_initial

        # Adjust based on provider rate limits and cost
        provider_limits = {
            LLMProvider.ANTHROPIC: 20,
            LLMProvider.OPENAI: 15,
            LLMProvider.GOOGLE: 5,  # Lower limit due to free tier restrictions
            LLMProvider.DEEPSEEK: 25,
            LLMProvider.OLLAMA: 5,  # Conservative for local inference
        }

        if self.config.provider in provider_limits:
            batch_size = min(batch_size, provider_limits[self.config.provider])

        # Reduce batch size for small transaction counts to avoid unnecessary API calls
        if num_transactions < batch_size:
            batch_size = max(1, num_transactions)

        # Conservative batching for expensive models
        if "opus" in self.config.model.lower():
            batch_size = max(5, batch_size // 2)

        if self.debug:
            logger.debug(f"Calculated batch size: {batch_size}")

        return batch_size

    def validate_configuration(self) -> bool:
        """
        Validate that the LLM provider is accessible.

        Returns:
            True if valid, False otherwise
        """
        try:
            is_valid = self.provider.validate_api_key()
            if not is_valid:
                logger.error("Invalid LLM API key or provider not accessible")
            return is_valid
        except Exception as e:
            logger.error(f"Error validating LLM configuration: {e}")
            return False

    def get_status(self) -> Dict:
        """
        Get current enrichment configuration and statistics.

        Returns:
            Status dictionary with provider info and stats
        """
        return {
            "provider": self.config.provider.value,
            "model": self.config.model,
            "cache_enabled": self.config.cache_enabled,
            "configured": True,
        }


# Global enricher instance (lazy loaded)
_enricher: Optional[LLMEnricher] = None


def get_enricher() -> Optional[LLMEnricher]:
    """
    Get or create the global LLM enricher instance.

    Returns:
        LLMEnricher instance or None if not configured
    """
    global _enricher

    if _enricher is not None:
        return _enricher

    try:
        _enricher = LLMEnricher()
        return _enricher
    except ValueError:
        # LLM not configured
        return None
