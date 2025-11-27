import { useState, useEffect } from 'react';
import axios from 'axios';
import type { ExcelFile, ImportResponse } from '../types';

const API_URL = 'http://localhost:5000/api';

export default function FileList() {
  const [files, setFiles] = useState<ExcelFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);
  const [coverageWarning, setCoverageWarning] = useState<any>(null);
  const [autoEnrich, setAutoEnrich] = useState(false);
  const [llmEnrichmentStats, setLlmEnrichmentStats] = useState<any>(null);

  useEffect(() => {
    fetchFiles();
  }, []);

  const fetchFiles = async () => {
    try {
      setLoading(true);
      const response = await axios.get<ExcelFile[]>(`${API_URL}/files`);
      setFiles(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch files. Make sure backend is running.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async (filename: string) => {
    try {
      setImporting(filename);
      setImportSuccess(null);
      setError(null);
      setCoverageWarning(null);
      setLlmEnrichmentStats(null);

      const response = await axios.post<any>(`${API_URL}/import`, {
        filename: filename,
        auto_enrich: autoEnrich
      });

      // Build success message
      let successMessage = `Successfully imported ${response.data.imported} transactions from ${filename}`;

      // Add Amazon matching info if available
      if (response.data.amazon_matching) {
        const { matched, total_processed } = response.data.amazon_matching;
        if (total_processed > 0) {
          successMessage += `\n\nAmazon Matching: ${matched} of ${total_processed} Amazon transactions enriched`;
        }
      }

      // Add LLM enrichment info if available
      if (response.data.llm_enrichment) {
        const llmStats = response.data.llm_enrichment;
        setLlmEnrichmentStats(llmStats);
        successMessage += `\n\nLLM Enrichment: ${llmStats.successful} successful, ${llmStats.failed} failed (Cost: $${llmStats.total_cost.toFixed(4)})`;
      }

      setImportSuccess(successMessage);

      // Check for coverage warning
      if (response.data.coverage_warning) {
        setCoverageWarning(response.data.coverage_warning);
      }

      // Refresh file list to update imported status
      await fetchFiles();

      // Trigger refresh of transactions list (parent component will handle this)
      window.dispatchEvent(new Event('transactions-updated'));

    } catch (err: any) {
      if (err.response?.data?.message) {
        setError(err.response.data.message);
      } else if (err.response?.data?.error) {
        setError(err.response.data.error);
      } else {
        setError('Failed to import file');
      }
      console.error(err);
    } finally {
      setImporting(null);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error && files.length === 0) {
    return (
      <div className="alert alert-error">
        <span>{error}</span>
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="alert alert-info">
        <div>
          <h3 className="font-bold">No Excel files found</h3>
          <div className="text-sm mt-2">
            Place your Santander Excel bank statements in:<br />
            <code className="bg-base-300 px-2 py-1 rounded">~/FinanceData/</code>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Auto-enrich option */}
      <div className="card bg-base-100 border border-base-300">
        <div className="card-body py-4">
          <label className="label cursor-pointer justify-start gap-3">
            <input
              type="checkbox"
              className="checkbox checkbox-sm"
              checked={autoEnrich}
              onChange={(e) => setAutoEnrich(e.target.checked)}
            />
            <span className="label-text">Auto-enrich with LLM during import</span>
          </label>
          <p className="text-xs text-base-content/60 ml-8">
            Automatically categorize and enrich transactions using configured AI provider. May incur costs.
          </p>
        </div>
      </div>

      {importSuccess && (
        <div className="alert alert-success">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="whitespace-pre-line">{importSuccess}</span>
        </div>
      )}

      {coverageWarning && (
        <div className="alert alert-warning">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="flex-1">
            <div className="font-semibold mb-2">Missing Amazon Order Data</div>
            <div className="text-sm">{coverageWarning.message}</div>
            <div className="text-xs mt-2 opacity-70">
              Date range: {coverageWarning.date_from} to {coverageWarning.date_to}
            </div>
            <a
              href="/settings"
              className="btn btn-sm btn-warning mt-3"
            >
              Import Amazon Orders
            </a>
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-warning">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="table table-zebra">
          <thead>
            <tr>
              <th>File Name</th>
              <th>Size</th>
              <th>Modified</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {files.map((file) => (
              <tr key={file.name}>
                <td className="font-mono text-sm">{file.name}</td>
                <td>{file.size_mb} MB</td>
                <td>{file.modified_readable}</td>
                <td>
                  {file.imported ? (
                    <span className="badge badge-success">Imported</span>
                  ) : (
                    <span className="badge badge-warning">Not Imported</span>
                  )}
                </td>
                <td>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleImport(file.name)}
                    disabled={file.imported || importing !== null}
                  >
                    {importing === file.name ? (
                      <>
                        <span className="loading loading-spinner loading-sm"></span>
                        Importing...
                      </>
                    ) : file.imported ? (
                      'Already Imported'
                    ) : (
                      'Import'
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-sm text-base-content/60">
        <p>📁 Data folder: <code className="bg-base-300 px-2 py-1 rounded">~/FinanceData/</code></p>
        <p className="mt-1">💡 Add new Excel files to this folder and refresh to see them here.</p>
      </div>
    </div>
  );
}
