import { useState, useEffect } from 'react';
import axios from 'axios';
import AddOllamaModel from './AddOllamaModel';

const API_URL = 'http://localhost:5000/api';

interface EnrichmentConfig {
  configured: boolean;
  config?: {
    provider: string;
    model: string;
    cache_enabled: boolean;
    batch_size?: number;
  };
  message?: string;
}

interface CacheStats {
  total_cached: number;
  providers: Record<string, number>;
  pending_retries: number;
  cache_size_bytes: number;
}

interface EnrichmentStats {
  total_transactions: number;
  successful_enrichments: number;
  failed_enrichments: number;
  cached_hits: number;
  api_calls_made: number;
  total_tokens_used: number;
  total_cost: number;
  retry_queue: number[];
}

interface FailedEnrichment {
  transaction_id: number;
  description: string;
  error_message: string;
  error_type: string;
  provider: string;
  retry_count: number;
}

interface ProgressUpdate {
  type: 'start' | 'progress' | 'complete' | 'error';
  processed?: number;
  total?: number;
  tokens_used?: number;
  cost?: number;
  successful?: number;
  failed?: number;
  percentage?: number;
  message?: string;
  total_tokens?: number;
  total_cost?: number;
  error?: string;
}

interface ModelInfo {
  name: string;
  selected?: boolean;
}

interface AllModelsResponse {
  current_provider: string;
  all_models: {
    anthropic: AvailableModels;
    openai: AvailableModels;
    google: AvailableModels;
    deepseek: AvailableModels;
    ollama: AvailableModels;
  };
}

interface AvailableModels {
  provider: string;
  selected?: string;
  built_in: ModelInfo[];
  custom: ModelInfo[];
  available?: Array<{ name: string; installed: boolean }>;
}

export default function LLMEnrichmentSettings() {
  const [config, setConfig] = useState<EnrichmentConfig | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [failedEnrichments, setFailedEnrichments] = useState<FailedEnrichment[]>([]);
  const [loading, setLoading] = useState(true);
  const [enriching, setEnriching] = useState(false);
  const [validating, setValidating] = useState(false);
  const [showFailedDetails, setShowFailedDetails] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Progress tracking
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);

  // Enrichment options
  const [enrichmentDirection, setEnrichmentDirection] = useState('out');
  const [forceRefresh, setForceRefresh] = useState(false);
  const [lastStats, setLastStats] = useState<EnrichmentStats | null>(null);
  const [transactionCount, setTransactionCount] = useState<number | null>(null);
  const [transactionCountMode, setTransactionCountMode] = useState<'all' | 'unenriched' | 'limit'>('unenriched');

  // Model management
  const [allModels, setAllModels] = useState<AllModelsResponse | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [showAddModel, setShowAddModel] = useState(false);

  useEffect(() => {
    fetchConfig();
    fetchCacheStats();
    fetchFailedEnrichments();
  }, []);

  useEffect(() => {
    if (config?.configured) {
      fetchAvailableModels();
    }
  }, [config?.configured]);

  const fetchConfig = async () => {
    try {
      const response = await axios.get<EnrichmentConfig>(`${API_URL}/enrichment/config`);
      setConfig(response.data);
    } catch (err) {
      console.error('Failed to fetch enrichment config:', err);
      setConfig({
        configured: false,
        message: 'Failed to fetch configuration'
      });
    }
  };

  const fetchCacheStats = async () => {
    try {
      const response = await axios.get<CacheStats>(`${API_URL}/enrichment/cache/stats`);
      setCacheStats(response.data);
    } catch (err) {
      console.error('Failed to fetch cache stats:', err);
    }
  };

  const fetchFailedEnrichments = async () => {
    try {
      const response = await axios.get<{ failed_enrichments: FailedEnrichment[] }>(
        `${API_URL}/enrichment/failed?limit=20`
      );
      setFailedEnrichments(response.data.failed_enrichments);
    } catch (err) {
      console.error('Failed to fetch failed enrichments:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableModels = async () => {
    try {
      setLoadingModels(true);
      const response = await axios.get<AllModelsResponse>(`${API_URL}/llm/available-models`);
      setAllModels(response.data);
    } catch (err) {
      console.error('Failed to fetch available models:', err);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSetModel = async (modelName: string) => {
    try {
      // Find which provider this model belongs to
      let selectedProvider = '';
      for (const [provider, models] of Object.entries(allModels.all_models)) {
        const builtInMatch = models.built_in?.some(m => m.name === modelName);
        const customMatch = models.custom?.some(m => m.name === modelName);
        if (builtInMatch || customMatch) {
          selectedProvider = provider;
          break;
        }
      }

      const response = await axios.post(`${API_URL}/llm/set-model`, {
        model_name: modelName,
        provider: selectedProvider,
      });

      if (response.data.success) {
        // Update config to reflect new model
        if (config?.config) {
          setConfig({
            ...config,
            config: {
              ...config.config,
              model: modelName,
              provider: selectedProvider,
            },
          });
        }
        alert(`✅ Model switched to ${modelName}`);
        fetchAvailableModels(); // Refresh model list
      } else {
        alert(`❌ ${response.data.message || 'Failed to set model'}`);
      }
    } catch (err: any) {
      alert(`❌ Error setting model: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleModelAdded = (modelName: string) => {
    // Refresh available models and switch to new model
    setTimeout(() => {
      fetchAvailableModels();
      handleSetModel(modelName);
    }, 500);
  };

  const handleValidateConfig = async () => {
    try {
      setValidating(true);
      const response = await axios.post(`${API_URL}/enrichment/validate`);
      const { valid, message } = response.data;

      if (valid) {
        alert(`✅ ${message}`);
      } else {
        alert(`❌ ${message}`);
      }
    } catch (err: any) {
      alert(`❌ ${err.response?.data?.error || 'Validation failed'}`);
    } finally {
      setValidating(false);
    }
  };

  const handleEnrichAllTransactions = async () => {
    // Build confirmation message based on mode
    let confirmMsg = 'Enrich transactions with LLM?\n\nThis will use your configured API and may incur costs.';
    if (transactionCountMode === 'limit' && transactionCount) {
      confirmMsg = `Enrich first ${transactionCount} transactions with LLM?\n\nThis will use your configured API and may incur costs.`;
    } else if (transactionCountMode === 'all') {
      confirmMsg = 'Enrich ALL transactions with LLM?\n\nThis will use your configured API and may incur costs.';
    } else if (transactionCountMode === 'unenriched') {
      confirmMsg = 'Enrich only unenriched transactions with LLM?\n\nThis will use your configured API and may incur costs.';
    }

    if (!confirm(confirmMsg)) {
      return;
    }

    // Validate limit if in limit mode
    if (transactionCountMode === 'limit' && (!transactionCount || transactionCount < 1)) {
      alert('Please enter a valid transaction count (minimum 1)');
      return;
    }

    try {
      setEnriching(true);
      setProgress(null);

      const eventSource = new EventSource(`${API_URL}/enrichment/enrich-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          transaction_ids: null, // null means use mode filtering
          direction: enrichmentDirection,
          force_refresh: forceRefresh,
          mode: transactionCountMode,
          limit: transactionCountMode === 'limit' ? transactionCount : undefined
        })
      } as any);

      // For browsers that don't support POST with EventSource, use fetch instead
      const response = await fetch(`${API_URL}/enrichment/enrich-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          transaction_ids: null,
          direction: enrichmentDirection,
          force_refresh: forceRefresh,
          mode: transactionCountMode,
          limit: transactionCountMode === 'limit' ? transactionCount : undefined
        })
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error('Unable to read response');

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const update = JSON.parse(line.slice(6)) as ProgressUpdate;
              setProgress(update);

              if (update.type === 'complete') {
                setLastStats({
                  total_transactions: update.total_transactions || 0,
                  successful_enrichments: update.successful || 0,
                  failed_enrichments: update.failed || 0,
                  cached_hits: update.successful || 0,
                  api_calls_made: 1,
                  total_tokens_used: update.total_tokens || 0,
                  total_cost: update.total_cost || 0,
                  retry_queue: []
                });

                // Refresh cache stats and failed enrichments
                fetchCacheStats();
                fetchFailedEnrichments();

                // Dispatch event to refresh transactions list
                window.dispatchEvent(new Event('transactions-updated'));

                alert(`✅ Enrichment completed!\n\nSuccessful: ${update.successful}\nFailed: ${update.failed}\nTotal tokens: ${update.total_tokens?.toLocaleString()}\nTotal cost: $${update.total_cost?.toFixed(4)}`);
              }
            } catch (e) {
              console.error('Error parsing progress update:', e);
            }
          }
        }
      }
    } catch (err: any) {
      alert(`❌ Enrichment failed: ${err.message}`);
      setProgress(null);
    } finally {
      setEnriching(false);
    }
  };

  const handleRetryFailed = async () => {
    if (failedEnrichments.length === 0) {
      alert('No failed enrichments to retry');
      return;
    }

    if (!confirm(`Retry enrichment for ${failedEnrichments.length} failed transactions?`)) {
      return;
    }

    try {
      setEnriching(true);
      const response = await axios.post<{ stats: EnrichmentStats }>(`${API_URL}/enrichment/retry-failed`, {
        direction: enrichmentDirection,
        limit: 50
      });

      const stats = response.data.stats;
      setLastStats(stats);

      // Refresh cache stats and failed enrichments
      fetchCacheStats();
      fetchFailedEnrichments();

      // Dispatch event to refresh transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      alert(`✅ Retry completed!\n\nSuccessful: ${stats.successful_enrichments}\nFailed: ${stats.failed_enrichments}\nTotal cost: $${stats.total_cost.toFixed(4)}`);
    } catch (err: any) {
      alert(`❌ Retry failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setEnriching(false);
    }
  };

  const handleClearEnrichment = async () => {
    try {
      setClearing(true);
      const response = await axios.post(`${API_URL}/enrichment/clear`);
      const { success, message, enrichments_cleared } = response.data;

      if (success) {
        alert(`✅ ${message}\n\nCleared enrichment data for ${enrichments_cleared} transactions.`);

        // Refresh cache stats and failed enrichments
        fetchCacheStats();
        fetchFailedEnrichments();
        setLastStats(null);

        // Dispatch event to refresh transactions list
        window.dispatchEvent(new Event('transactions-updated'));
      } else {
        alert(`❌ Failed to clear enrichment data`);
      }
    } catch (err: any) {
      alert(`❌ Error: ${err.response?.data?.error || err.message}`);
    } finally {
      setClearing(false);
      setShowClearConfirm(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="alert alert-error mb-8">
        <span>Failed to load LLM enrichment settings</span>
      </div>
    );
  }

  return (
    <div className="mb-8">
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h2 className="text-xl font-semibold">LLM Enrichment</h2>
          <p className="text-sm text-base-content/70">
            Use AI to automatically enrich and categorize transactions
          </p>
        </div>
      </div>

      {/* Configuration Status */}
      {!config.configured ? (
        <div className="alert alert-warning mb-6">
          <span>
            LLM enrichment is not configured. Set the <code>LLM_PROVIDER</code> and <code>LLM_API_KEY</code> environment variables to enable this feature.
            <br />
            <a href="/settings#ollama-setup" className="link link-primary text-sm mt-2 block">See LLM Setup Guide</a>
          </span>
        </div>
      ) : (
        <div className="card bg-base-200 shadow mb-6">
          <div className="card-body">
            <h3 className="card-title text-lg">Configuration Status</h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="bg-base-100 p-4 rounded">
                <div className="text-sm text-base-content/70">Provider</div>
                <div className="text-lg font-semibold">{config.config?.provider || 'Unknown'}</div>
              </div>
              <div className="bg-base-100 p-4 rounded">
                <div className="text-sm text-base-content/70">Model</div>
                <div className="text-lg font-semibold">{config.config?.model || 'Unknown'}</div>
              </div>
              <div className="bg-base-100 p-4 rounded">
                <div className="text-sm text-base-content/70">Cache Status</div>
                <div className="text-lg font-semibold">
                  {config.config?.cache_enabled ? (
                    <span className="badge badge-success">Enabled</span>
                  ) : (
                    <span className="badge badge-ghost">Disabled</span>
                  )}
                </div>
              </div>
            </div>

            <button
              className="btn btn-outline btn-sm"
              onClick={handleValidateConfig}
              disabled={validating}
            >
              {validating ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  Validating...
                </>
              ) : (
                '🔍 Validate Configuration'
              )}
            </button>

            {/* Ollama-specific help */}
            {config.config?.provider === 'ollama' && (
              <div className="alert alert-info mt-4">
                <div>
                  <h4 className="font-semibold mb-2">💻 Running Ollama Locally</h4>
                  <ul className="text-sm space-y-1 list-disc list-inside">
                    <li>Make sure Ollama is running: <code className="bg-base-300 px-2 py-1 rounded text-xs">ollama serve</code></li>
                    <li>Verify your model is available: <code className="bg-base-300 px-2 py-1 rounded text-xs">ollama list</code></li>
                    <li>If model missing, pull it: <code className="bg-base-300 px-2 py-1 rounded text-xs">ollama pull {config.config?.model || 'mistral:7b'}</code></li>
                    <li>No API key needed - all processing happens locally!</li>
                    <li>Batch size can be adjusted in <code className="bg-base-300 px-2 py-1 rounded text-xs">.env</code> to optimize for your hardware</li>
                  </ul>
                  <p className="text-xs mt-3">
                    <a href="https://github.com/ollama/ollama" target="_blank" rel="noopener noreferrer" className="link link-primary">View Ollama docs →</a>
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Model Selection Card */}
      {config.configured && allModels && (
        <div className="card bg-base-200 shadow mb-6">
          <div className="card-body">
            <h3 className="card-title text-lg">🔧 Model Selection</h3>

            {/* Model Selector - All Providers */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-semibold">Active Model (All Providers)</span>
              </label>
              <select
                className="select select-bordered"
                value={config.config?.model || ''}
                onChange={(e) => handleSetModel(e.target.value)}
                disabled={loadingModels}
              >
                <option value="" disabled>
                  Select a model...
                </option>
                {/* Anthropic Models */}
                {allModels.all_models.anthropic?.built_in?.length > 0 && (
                  <optgroup label="🤖 Anthropic Claude">
                    {allModels.all_models.anthropic.built_in.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} {model.selected ? '✓' : ''}
                      </option>
                    ))}
                    {allModels.all_models.anthropic.custom?.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} (custom) {model.selected ? '✓' : ''}
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* OpenAI Models */}
                {allModels.all_models.openai?.built_in?.length > 0 && (
                  <optgroup label="🔴 OpenAI GPT">
                    {allModels.all_models.openai.built_in.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} {model.selected ? '✓' : ''}
                      </option>
                    ))}
                    {allModels.all_models.openai.custom?.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} (custom) {model.selected ? '✓' : ''}
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* Google Models */}
                {allModels.all_models.google?.built_in?.length > 0 && (
                  <optgroup label="🔵 Google Gemini">
                    {allModels.all_models.google.built_in.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} {model.selected ? '✓' : ''}
                      </option>
                    ))}
                    {allModels.all_models.google.custom?.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} (custom) {model.selected ? '✓' : ''}
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* Deepseek Models */}
                {allModels.all_models.deepseek?.built_in?.length > 0 && (
                  <optgroup label="⚡ Deepseek">
                    {allModels.all_models.deepseek.built_in.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} {model.selected ? '✓' : ''}
                      </option>
                    ))}
                    {allModels.all_models.deepseek.custom?.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} (custom) {model.selected ? '✓' : ''}
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* Ollama Models */}
                {allModels.all_models.ollama?.built_in?.length > 0 && (
                  <optgroup label="💻 Ollama (Local)">
                    {allModels.all_models.ollama.built_in.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} {model.selected ? '✓' : ''}
                      </option>
                    ))}
                    {allModels.all_models.ollama.custom?.map((model) => (
                      <option value={model.name} key={model.name}>
                        {model.name} (custom) {model.selected ? '✓' : ''}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>

            {/* Add Model Button (Ollama only) */}
            {config.config?.provider === 'ollama' && (
              <button
                className="btn btn-outline btn-sm mt-4"
                onClick={() => setShowAddModel(true)}
              >
                ➕ Add New Ollama Model
              </button>
            )}

            {/* Available Models List (Ollama) */}
            {config.config?.provider === 'ollama' && allModels.all_models.ollama?.available && allModels.all_models.ollama.available.length > 0 && (
              <div className="mt-4">
                <label className="label">
                  <span className="label-text text-sm">Installed in Ollama:</span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {allModels.all_models.ollama.available.map((model) => (
                    <span
                      key={model.name}
                      className={`badge ${model.installed ? 'badge-success' : 'badge-warning'}`}
                    >
                      {model.name} {model.installed ? '✓' : '⏳'}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Provider Info */}
            <div className="alert alert-info text-sm mt-4">
              <div>
                <p className="font-semibold mb-2">💡 About Model Selection</p>
                <ul className="text-xs space-y-1 list-disc list-inside">
                  <li>Select any model from any provider to switch immediately</li>
                  <li>Models are grouped by provider for easy browsing</li>
                  <li>For Ollama, add new models with the "Add New Ollama Model" button</li>
                  <li>Switching models doesn't require backend restart</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Enrichment Controls */}
      {config.configured && (
        <div className="card bg-base-200 shadow mb-6">
          <div className="card-body">
            <h3 className="card-title text-lg">Enrich Transactions</h3>

            <div className="space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Transaction Direction</span>
                </label>
                <select
                  className="select select-bordered"
                  value={enrichmentDirection}
                  onChange={(e) => setEnrichmentDirection(e.target.value)}
                >
                  <option value="out">Expenses (Out)</option>
                  <option value="in">Income (In)</option>
                </select>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Transactions to Enrich</span>
                </label>
                <select
                  className="select select-bordered"
                  value={transactionCountMode}
                  onChange={(e) => {
                    setTransactionCountMode(e.target.value as 'all' | 'unenriched' | 'limit');
                    if (e.target.value !== 'limit') {
                      setTransactionCount(null);
                    }
                  }}
                >
                  <option value="unenriched">Only Unenriched Transactions (default)</option>
                  <option value="all">All Transactions</option>
                  <option value="limit">First N Transactions</option>
                </select>
                <label className="label">
                  <span className="label-text-alt">
                    {transactionCountMode === 'unenriched' && 'Skip transactions that already have enrichment data'}
                    {transactionCountMode === 'all' && 'Enrich all transactions (may re-enrich already-enriched ones)'}
                    {transactionCountMode === 'limit' && 'Specify a maximum number of transactions to enrich'}
                  </span>
                </label>
              </div>

              {transactionCountMode === 'limit' && (
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Limit to First</span>
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      className="input input-bordered flex-1"
                      placeholder="e.g., 50"
                      value={transactionCount ?? ''}
                      onChange={(e) => setTransactionCount(e.target.value ? parseInt(e.target.value) : null)}
                      min="1"
                      max="10000"
                    />
                    <span className="input input-bordered input-disabled flex-1 flex items-center">
                      transactions
                    </span>
                  </div>
                </div>
              )}

              <div className="form-control">
                <label className="label cursor-pointer">
                  <span className="label-text">Force Refresh</span>
                  <input
                    type="checkbox"
                    className="checkbox"
                    checked={forceRefresh}
                    onChange={(e) => setForceRefresh(e.target.checked)}
                  />
                </label>
                <label className="label">
                  <span className="label-text-alt">
                    Bypass cache and re-query LLM for all transactions
                  </span>
                </label>
              </div>

              {/* Batch size info for Ollama */}
              {config.config?.provider === 'ollama' && (
                <div className="alert alert-info">
                  <div>
                    <p className="text-sm mb-2">
                      <strong>💡 Performance Tip:</strong> Adjust batch size in <code className="bg-base-300 px-1 rounded text-xs">LLM_BATCH_SIZE</code> to find optimal performance:
                    </p>
                    <ul className="text-xs space-y-1 list-disc list-inside">
                      <li>Small batches (1-3): Slower but use less memory, good for testing</li>
                      <li>Medium batches (5-10): Balanced performance and memory usage</li>
                      <li>Large batches (15+): Faster but requires more memory</li>
                    </ul>
                  </div>
                </div>
              )}
            </div>

            <div className="flex gap-2 pt-4">
              <button
                className="btn btn-primary flex-1"
                onClick={handleEnrichAllTransactions}
                disabled={enriching || !config.configured}
              >
                {enriching ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Enriching...
                  </>
                ) : (
                  '✨ Enrich All Transactions'
                )}
              </button>

              {failedEnrichments.length > 0 && (
                <button
                  className="btn btn-warning"
                  onClick={handleRetryFailed}
                  disabled={enriching}
                >
                  🔄 Retry {failedEnrichments.length}
                </button>
              )}
            </div>

            {/* Live Progress Display */}
            {progress && progress.type !== 'complete' && (
              <div className="alert alert-info mt-4">
                <div className="w-full">
                  <h4 className="font-semibold mb-2">
                    {progress.type === 'start' ? '📊 Starting enrichment...' : '⚙️ Enriching transactions...'}
                  </h4>

                  {progress.processed && progress.total && (
                    <>
                      <div className="mb-2">
                        <div className="flex justify-between text-sm mb-1">
                          <span>Progress: {progress.processed}/{progress.total} transactions</span>
                          <span className="font-mono">{progress.percentage}%</span>
                        </div>
                        <progress
                          className="progress progress-primary w-full"
                          value={progress.processed}
                          max={progress.total}
                        ></progress>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                        <div className="bg-base-300 p-2 rounded">
                          <div className="text-xs text-base-content/70">Tokens Used</div>
                          <div className="font-mono font-semibold">{progress.tokens_used?.toLocaleString() || 0}</div>
                        </div>
                        <div className="bg-base-300 p-2 rounded">
                          <div className="text-xs text-base-content/70">Cost</div>
                          <div className="font-mono font-semibold">${progress.cost?.toFixed(4) || '0.0000'}</div>
                        </div>
                        <div className="bg-base-300 p-2 rounded">
                          <div className="text-xs text-base-content/70">Successful</div>
                          <div className="font-mono font-semibold text-success">{progress.successful || 0}</div>
                        </div>
                        <div className="bg-base-300 p-2 rounded">
                          <div className="text-xs text-base-content/70">Failed</div>
                          <div className="font-mono font-semibold text-error">{progress.failed || 0}</div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {lastStats && (
              <div className="alert alert-info mt-4">
                <div>
                  <h4 className="font-semibold mb-2">Last Enrichment Results:</h4>
                  <ul className="text-sm space-y-1">
                    <li>✅ Successful: {lastStats.successful_enrichments}</li>
                    <li>❌ Failed: {lastStats.failed_enrichments}</li>
                    <li>💾 Cached: {lastStats.cached_hits}</li>
                    <li>📡 API Calls: {lastStats.api_calls_made}</li>
                    <li>🔤 Total Tokens: {lastStats.total_tokens_used.toLocaleString()}</li>
                    <li>💰 Cost: ${lastStats.total_cost.toFixed(4)}</li>
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Cache Statistics */}
      {cacheStats && (
        <div className="card bg-base-200 shadow mb-6">
          <div className="card-body">
            <h3 className="card-title text-lg">Cache Statistics</h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="bg-base-100 p-4 rounded">
                <div className="text-sm text-base-content/70">Cached Results</div>
                <div className="text-2xl font-bold">{cacheStats.total_cached}</div>
              </div>
              <div className="bg-base-100 p-4 rounded">
                <div className="text-sm text-base-content/70">Cache Size</div>
                <div className="text-lg font-semibold">
                  {(cacheStats.cache_size_bytes / 1024).toFixed(2)} KB
                </div>
              </div>
              <div className="bg-base-100 p-4 rounded">
                <div className="text-sm text-base-content/70">Pending Retries</div>
                <div className="text-2xl font-bold text-warning">
                  {cacheStats.pending_retries}
                </div>
              </div>
            </div>

            {cacheStats.providers && Object.keys(cacheStats.providers).length > 0 && (
              <div>
                <h4 className="font-semibold mb-2">By Provider:</h4>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(cacheStats.providers).map(([provider, count]) => (
                    <span key={provider} className="badge badge-outline">
                      {provider}: {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Failed Enrichments */}
      {failedEnrichments.length > 0 && (
        <div className="card bg-base-200 shadow mb-6">
          <div className="card-body">
            <div className="flex justify-between items-center mb-4">
              <h3 className="card-title text-lg">Failed Enrichments ({failedEnrichments.length})</h3>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowFailedDetails(!showFailedDetails)}
              >
                {showFailedDetails ? '▼' : '▶'} Details
              </button>
            </div>

            {showFailedDetails && (
              <div className="overflow-x-auto">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>Error Type</th>
                      <th>Retries</th>
                      <th>Provider</th>
                    </tr>
                  </thead>
                  <tbody>
                    {failedEnrichments.map((failed) => (
                      <tr key={failed.transaction_id} className="hover">
                        <td className="max-w-xs truncate">{failed.description}</td>
                        <td>
                          <span className="badge badge-error badge-sm">
                            {failed.error_type}
                          </span>
                        </td>
                        <td>{failed.retry_count}</td>
                        <td className="text-sm text-base-content/70">{failed.provider}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Clear Enrichment Data */}
      {config.configured && (
        <div className="card bg-base-200 shadow">
          <div className="card-body">
            <h3 className="card-title text-lg">Enrichment Management</h3>
            <p className="text-sm text-base-content/70 mb-4">
              Manage enrichment data. This is useful for development and testing purposes.
            </p>

            <div className="flex gap-2">
              <button
                className="btn btn-warning"
                onClick={() => setShowClearConfirm(true)}
                disabled={clearing}
              >
                {clearing ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Clearing...
                  </>
                ) : (
                  '🗑️ Clear All Enrichment Data'
                )}
              </button>
            </div>

            {/* Clear Confirmation Modal */}
            {showClearConfirm && (
              <div className="modal modal-open">
                <div className="modal-box">
                  <h3 className="font-bold text-lg">Clear All Enrichment Data?</h3>
                  <p className="py-4">
                    This will permanently delete all enrichment data (categories, merchant names, confidence scores, etc.) for all transactions.
                  </p>
                  <p className="text-sm text-warning font-semibold mb-4">
                    This action cannot be undone. Only proceed if you're certain you want to re-enrich all transactions from scratch.
                  </p>
                  <div className="modal-action">
                    <button
                      className="btn btn-ghost"
                      onClick={() => setShowClearConfirm(false)}
                      disabled={clearing}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn btn-error"
                      onClick={handleClearEnrichment}
                      disabled={clearing}
                    >
                      {clearing ? (
                        <>
                          <span className="loading loading-spinner loading-sm"></span>
                          Clearing...
                        </>
                      ) : (
                        'Yes, Clear All Data'
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Ollama Model Modal */}
      <AddOllamaModel
        isOpen={showAddModel}
        onClose={() => setShowAddModel(false)}
        onModelAdded={handleModelAdded}
      />
    </div>
  );
}
