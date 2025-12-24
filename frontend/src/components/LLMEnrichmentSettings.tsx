import { useState, useEffect } from 'react';
import axios from 'axios';

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

interface ProviderAccountInfo {
  available: boolean;
  balance?: number | null;
  subscription_tier?: string | null;
  usage_this_month?: number | null;
  error?: string | null;
  extra?: Record<string, any> | null;
}

interface AccountInfoResponse {
  configured: boolean;
  provider?: string;
  account?: ProviderAccountInfo;
  error?: string;
}

export default function LLMEnrichmentSettings() {
  const [config, setConfig] = useState<EnrichmentConfig | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [failedEnrichments, setFailedEnrichments] = useState<FailedEnrichment[]>([]);
  const [loading, setLoading] = useState(true);
  const [enriching, setEnriching] = useState(false);
  const [validating, setValidating] = useState(false);
  const [showFailedDetails, setShowFailedDetails] = useState(false);

  // Progress tracking
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);

  // Account info
  const [accountInfo, setAccountInfo] = useState<ProviderAccountInfo | null>(null);
  const [loadingAccountInfo, setLoadingAccountInfo] = useState(false);

  // Enrichment options
  const [enrichmentMode, setEnrichmentMode] = useState<'required' | 'unenriched' | 'all'>('required');
  const [transactionLimit, setTransactionLimit] = useState<number | null>(null);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [lastStats, setLastStats] = useState<EnrichmentStats | null>(null);

  useEffect(() => {
    fetchConfig();
    fetchCacheStats();
    fetchFailedEnrichments();
  }, []);

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

  const fetchAccountInfo = async () => {
    setLoadingAccountInfo(true);
    try {
      const response = await axios.get<AccountInfoResponse>(`${API_URL}/enrichment/account-info`);
      if (response.data.account) {
        setAccountInfo(response.data.account);
      }
    } catch (err) {
      console.error('Failed to fetch account info:', err);
      setAccountInfo({ available: false, error: 'Failed to fetch account info' });
    } finally {
      setLoadingAccountInfo(false);
    }
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
    // Build confirmation message based on options
    const modeLabels = {
      required: 'marked as required',
      unenriched: 'unenriched',
      all: 'ALL'
    };
    let confirmMsg = `Enrich ${modeLabels[enrichmentMode]} transactions with LLM?`;
    if (transactionLimit) {
      confirmMsg = `Enrich up to ${transactionLimit} ${modeLabels[enrichmentMode]} transactions with LLM?`;
    }
    confirmMsg += '\n\nThis will use your configured API and may incur costs.';

    if (!confirm(confirmMsg)) {
      return;
    }

    // Create abort controller with 15-minute timeout for long enrichment jobs
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15 * 60 * 1000);

    try {
      setEnriching(true);
      setProgress(null);

      // Use fetch for POST with EventSource-style streaming
      const response = await fetch(`${API_URL}/enrichment/enrich-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          transaction_ids: null,
          force_refresh: forceRefresh,
          mode: enrichmentMode,
          limit: transactionLimit || undefined
        }),
        signal: controller.signal
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
      // Check if this was a timeout abort
      if (err.name === 'AbortError') {
        alert(`❌ Enrichment timed out after 15 minutes. The process may still be running on the server. Check back in a few minutes.`);
      } else {
        alert(`❌ Enrichment failed: ${err.message}`);
      }
      setProgress(null);
    } finally {
      clearTimeout(timeoutId);
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
    <div className="mb-6">
      <h3 className="text-lg font-semibold mb-4">LLM Enrichment</h3>

      {/* Configuration Status */}
      {!config.configured ? (
        <div className="alert alert-warning mb-4">
          <span>
            Not configured. Set <code>LLM_PROVIDER</code> and <code>LLM_API_KEY</code> environment variables.
          </span>
        </div>
      ) : (
        <div className="border border-base-300 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 mb-3 text-sm">
            <span className="font-medium">Provider:</span> <span>{config.config?.provider}</span>
            <span className="text-base-content/50">|</span>
            <span className="font-medium">Model:</span> <span>{config.config?.model}</span>
            <span className="text-base-content/50">|</span>
            <span className="font-medium">Cache:</span>
            {config.config?.cache_enabled ? (
              <span className="badge badge-success badge-sm">Enabled</span>
            ) : (
              <span className="badge badge-ghost badge-sm">Disabled</span>
            )}
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
              'Validate Config'
            )}
          </button>

        </div>
      )}

      {/* Account Info */}
      {config?.configured && (
        <div className="border border-base-300 rounded-lg p-4 mb-4">
          <div className="flex justify-between items-center mb-3">
            <h4 className="font-semibold">Account</h4>
            <button
              className="btn btn-ghost btn-xs"
              onClick={fetchAccountInfo}
              disabled={loadingAccountInfo}
            >
              {loadingAccountInfo ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                'Refresh'
              )}
            </button>
          </div>

          {accountInfo === null ? (
            <p className="text-sm text-base-content/60">Click Refresh to load account info</p>
          ) : !accountInfo.available ? (
            <div className="text-sm text-warning">{accountInfo.error}</div>
          ) : (
            <div className="flex flex-wrap gap-4 text-sm">
              {accountInfo.subscription_tier && (
                <span>
                  <span className="font-medium">Tier:</span>{' '}
                  <span className="badge badge-outline badge-sm">{accountInfo.subscription_tier}</span>
                </span>
              )}
              {accountInfo.balance !== undefined && accountInfo.balance !== null && (
                <span><span className="font-medium">Balance:</span> ${accountInfo.balance.toFixed(2)}</span>
              )}
              {accountInfo.usage_this_month !== undefined && accountInfo.usage_this_month !== null && (
                <span><span className="font-medium">This Month:</span> ${accountInfo.usage_this_month.toFixed(2)}</span>
              )}
              {/* Ollama-specific: show system metrics */}
              {accountInfo.extra?.vram_used_gb !== undefined && (
                <span><span className="font-medium">VRAM:</span> {accountInfo.extra.vram_used_gb} GB</span>
              )}
              {accountInfo.extra?.running_models !== undefined && (
                <span><span className="font-medium">Models Loaded:</span> {accountInfo.extra.running_models}</span>
              )}
              {accountInfo.extra?.available_models !== undefined && (
                <span><span className="font-medium">Available:</span> {accountInfo.extra.available_models}</span>
              )}
              {accountInfo.extra?.organization && (
                <span><span className="font-medium">Org:</span> {accountInfo.extra.organization}</span>
              )}
            </div>
          )}

          {/* Anthropic Admin Key hint */}
          {config.config?.provider === 'anthropic' && accountInfo?.error?.includes('Admin API key') && (
            <p className="text-xs text-base-content/50 mt-2">
              Set <code className="bg-base-200 px-1 rounded">ANTHROPIC_ADMIN_API_KEY</code> environment variable for billing data.
            </p>
          )}
        </div>
      )}

      {/* Enrichment Controls */}
      {config.configured && (
        <div className="border border-base-300 rounded-lg p-4 mb-4">
          <h4 className="font-semibold mb-3">Enrich Transactions</h4>

          {/* Controls Row */}
          <div className="flex items-center gap-6 mb-3">
            <div className="flex items-center gap-2">
              <span className="text-sm">Mode:</span>
              <select
                className="select select-sm select-bordered"
                value={enrichmentMode}
                onChange={(e) => setEnrichmentMode(e.target.value as 'required' | 'unenriched' | 'all')}
              >
                <option value="required">All Required</option>
                <option value="unenriched">All Unenriched</option>
                <option value="all">All Transactions</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm">Limit:</span>
              <input
                type="number"
                className="input input-sm input-bordered w-20"
                placeholder="—"
                value={transactionLimit ?? ''}
                onChange={(e) => setTransactionLimit(e.target.value ? parseInt(e.target.value) : null)}
                min="1"
                max="10000"
              />
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={forceRefresh}
                onChange={(e) => setForceRefresh(e.target.checked)}
              />
              <span className="text-sm">Force Refresh</span>
            </label>
          </div>

          {/* Buttons Row */}
          <div className="flex gap-2">
            <button
              className="btn btn-sm btn-primary px-4"
              onClick={handleEnrichAllTransactions}
              disabled={enriching || !config.configured}
            >
              {enriching ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  Enriching...
                </>
              ) : (
                'Enrich Transactions'
              )}
            </button>

            {failedEnrichments.length > 0 && (
              <button
                className="btn btn-sm btn-warning"
                onClick={handleRetryFailed}
                disabled={enriching}
              >
                Retry {failedEnrichments.length}
              </button>
            )}
          </div>

          {/* Live Progress Display */}
          {progress && progress.type !== 'complete' && (
            <div className="alert alert-info mt-3">
              <div className="w-full">
                <div className="flex justify-between text-sm mb-2">
                  <span>{progress.processed}/{progress.total}</span>
                  <span className="font-mono">{progress.percentage}%</span>
                </div>
                <progress
                  className="progress progress-primary w-full mb-2"
                  value={progress.processed}
                  max={progress.total}
                ></progress>
                <div className="flex items-center gap-3 text-xs">
                  <span>Tokens: {progress.tokens_used?.toLocaleString() || 0}</span>
                  <span>Cost: ${progress.cost?.toFixed(4) || '0.0000'}</span>
                  <span className="text-success">OK: {progress.successful || 0}</span>
                  <span className="text-error">Err: {progress.failed || 0}</span>
                </div>
              </div>
            </div>
          )}

          {lastStats && (
            <div className="text-xs text-base-content/70 mt-3 flex items-center gap-3">
              <span>Last: OK {lastStats.successful_enrichments}</span>
              <span>Failed {lastStats.failed_enrichments}</span>
              <span>Tokens {lastStats.total_tokens_used.toLocaleString()}</span>
              <span>Cost ${lastStats.total_cost.toFixed(4)}</span>
            </div>
          )}
        </div>
      )}

      {/* Cache Statistics */}
      {cacheStats && (
        <div className="border border-base-300 rounded-lg p-4 mb-4">
          <h4 className="font-semibold mb-3">Cache</h4>
          <div className="flex items-center gap-4 text-sm">
            <span><span className="font-medium">Cached:</span> {cacheStats.total_cached}</span>
            <span><span className="font-medium">Size:</span> {(cacheStats.cache_size_bytes / 1024).toFixed(2)} KB</span>
            {cacheStats.pending_retries > 0 && (
              <span className="text-warning"><span className="font-medium">Pending:</span> {cacheStats.pending_retries}</span>
            )}
          </div>
          {cacheStats.providers && Object.keys(cacheStats.providers).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.entries(cacheStats.providers).map(([provider, count]) => (
                <span key={provider} className="badge badge-sm badge-outline">
                  {provider}: {count}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Failed Enrichments */}
      {failedEnrichments.length > 0 && (
        <div className="border border-base-300 rounded-lg p-4 mb-4">
          <div className="flex justify-between items-center mb-3">
            <h4 className="font-semibold">Failed ({failedEnrichments.length})</h4>
            <button
              className="btn btn-ghost btn-xs"
              onClick={() => setShowFailedDetails(!showFailedDetails)}
            >
              {showFailedDetails ? '▼' : '▶'}
            </button>
          </div>

          {showFailedDetails && (
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Error</th>
                    <th>Retries</th>
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
