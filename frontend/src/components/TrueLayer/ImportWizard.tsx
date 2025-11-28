import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ImportProgressBar } from './ImportProgressBar';

interface BankAccount {
  id: number;
  account_id: string;
  display_name: string;
  account_type: string;
  currency: string;
  last_synced_at?: string;
}

interface BankConnection {
  id: number;
  provider_id: string;
  connection_status: string;
  accounts: BankAccount[];
}

interface ImportWizardProps {
  connection: BankConnection;
  onImportComplete?: (jobId: number) => void;
  onClose?: () => void;
}

const API_BASE = 'http://localhost:5000/api';

type WizardStep = 'daterange' | 'accounts' | 'config' | 'review' | 'progress';

export const ImportWizard: React.FC<ImportWizardProps> = ({
  connection,
  onImportComplete,
  onClose
}) => {
  // Step state
  const [currentStep, setCurrentStep] = useState<WizardStep>('daterange');

  // Date range
  const [fromDate, setFromDate] = useState<string>(() => {
    const date = new Date();
    date.setDate(date.getDate() - 90);
    return date.toISOString().split('T')[0];
  });
  const [toDate, setToDate] = useState<string>(new Date().toISOString().split('T')[0]);

  // Account selection
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(
    new Set(connection.accounts.map(a => a.account_id))
  );

  // Configuration
  const [autoEnrich, setAutoEnrich] = useState(true);
  const [batchSize, setBatchSize] = useState(50);

  // Job tracking
  const [jobId, setJobId] = useState<number | null>(null);
  const [jobStatus, setJobStatus] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Plan
  const [plan, setPlan] = useState<any>(null);

  const selectedAccountIds = Array.from(selectedAccounts);
  const allSelected = selectedAccountIds.length === connection.accounts.length;

  // Step 1: Date Range Selection
  const DateRangeStep = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Select Date Range</h2>
      <p className="text-gray-600">Choose when to import transactions from</p>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => {
              const d = new Date();
              d.setDate(d.getDate() - 7);
              setFromDate(d.toISOString().split('T')[0]);
            }}
            className="btn btn-outline text-sm"
          >
            Last 7 Days
          </button>
          <button
            onClick={() => {
              const d = new Date();
              d.setMonth(d.getMonth() - 1);
              setFromDate(d.toISOString().split('T')[0]);
            }}
            className="btn btn-outline text-sm"
          >
            Last 30 Days
          </button>
          <button
            onClick={() => {
              const d = new Date();
              d.setMonth(d.getMonth() - 3);
              setFromDate(d.toISOString().split('T')[0]);
            }}
            className="btn btn-outline text-sm"
          >
            Last 3 Months
          </button>
          <button
            onClick={() => {
              const d = new Date();
              d.setFullYear(d.getFullYear() - 1);
              setFromDate(d.toISOString().split('T')[0]);
            }}
            className="btn btn-outline text-sm"
          >
            Last Year
          </button>
        </div>

        <div className="divider">OR</div>

        <div className="space-y-4">
          <div>
            <label className="label">
              <span className="label-text font-medium">From Date</span>
            </label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="input input-bordered w-full"
            />
          </div>

          <div>
            <label className="label">
              <span className="label-text font-medium">To Date</span>
            </label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="input input-bordered w-full"
            />
          </div>

          <div className="alert alert-info">
            <span className="text-sm">
              {Math.ceil((new Date(toDate).getTime() - new Date(fromDate).getTime()) / (1000 * 60 * 60 * 24))} days selected
            </span>
          </div>
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onClose} className="btn btn-ghost">
          Cancel
        </button>
        <button onClick={() => setCurrentStep('accounts')} className="btn btn-primary">
          Next: Select Accounts
        </button>
      </div>
    </div>
  );

  // Step 2: Account Selection
  const AccountSelectionStep = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Select Accounts</h2>
      <p className="text-gray-600">Choose which accounts to import</p>

      <div className="space-y-3">
        <label className="label cursor-pointer gap-3">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={(e) => {
              if (e.target.checked) {
                setSelectedAccounts(new Set(connection.accounts.map(a => a.account_id)));
              } else {
                setSelectedAccounts(new Set());
              }
            }}
            className="checkbox"
          />
          <span className="label-text font-medium">Select All Accounts ({connection.accounts.length})</span>
        </label>

        <div className="divider" />

        {connection.accounts.map((account) => (
          <label
            key={account.id}
            className="label cursor-pointer border rounded-lg p-3 hover:bg-base-200"
          >
            <div className="flex-1">
              <div className="font-medium">{account.display_name}</div>
              <div className="text-sm text-gray-500">
                {account.account_type} • {account.currency}
                {account.last_synced_at && (
                  <span> • Last synced: {new Date(account.last_synced_at).toLocaleDateString()}</span>
                )}
              </div>
            </div>
            <input
              type="checkbox"
              checked={selectedAccounts.has(account.account_id)}
              onChange={(e) => {
                const newSet = new Set(selectedAccounts);
                if (e.target.checked) {
                  newSet.add(account.account_id);
                } else {
                  newSet.delete(account.account_id);
                }
                setSelectedAccounts(newSet);
              }}
              className="checkbox"
            />
          </label>
        ))}
      </div>

      <div className="alert alert-warning">
        <span className="text-sm">{selectedAccountIds.length} account(s) selected</span>
      </div>

      <div className="flex justify-between">
        <button onClick={() => setCurrentStep('daterange')} className="btn btn-ghost">
          Back
        </button>
        <button
          onClick={() => setCurrentStep('config')}
          disabled={selectedAccountIds.length === 0}
          className="btn btn-primary"
        >
          Next: Configure
        </button>
      </div>
    </div>
  );

  // Step 3: Configuration
  const ConfigurationStep = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Import Settings</h2>
      <p className="text-gray-600">Configure import options</p>

      <div className="space-y-4">
        <label className="label cursor-pointer gap-3">
          <input
            type="checkbox"
            checked={autoEnrich}
            onChange={(e) => setAutoEnrich(e.target.checked)}
            className="checkbox"
          />
          <span className="label-text">Auto-enrich transactions with AI categorization</span>
        </label>

        {autoEnrich && (
          <div className="alert alert-info">
            <span className="text-sm">
              Transactions will be automatically categorized after import (adds 3-5 seconds)
            </span>
          </div>
        )}

        <div>
          <label className="label">
            <span className="label-text font-medium">Batch Size (transactions per request)</span>
            <span className="label-text-alt">{batchSize}</span>
          </label>
          <input
            type="range"
            min="10"
            max="200"
            step="10"
            value={batchSize}
            onChange={(e) => setBatchSize(parseInt(e.target.value))}
            className="range"
          />
          <div className="flex justify-between text-xs text-gray-500 px-2">
            <span>10 (safer)</span>
            <span>200 (faster)</span>
          </div>
        </div>

        <div className="alert alert-info">
          <span className="text-sm">
            Smaller batches are safer but slower. Recommended: 50 transactions
          </span>
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={() => setCurrentStep('accounts')} className="btn btn-ghost">
          Back
        </button>
        <button onClick={handlePlan} disabled={isLoading} className="btn btn-primary">
          {isLoading ? 'Planning...' : 'Next: Review'}
        </button>
      </div>
    </div>
  );

  // Step 4: Review
  const ReviewStep = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Review Import</h2>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      )}

      {plan && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg">📅 Date Range</h3>
                <p className="text-sm">
                  {new Date(plan.date_range.from).toLocaleDateString()} →{' '}
                  {new Date(plan.date_range.to).toLocaleDateString()}
                </p>
              </div>
            </div>

            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg">💰 Accounts</h3>
                <p className="text-sm">{plan.estimated_accounts} account(s)</p>
              </div>
            </div>

            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg">📊 Transactions</h3>
                <p className="text-sm">~{plan.estimated_transactions} transactions</p>
              </div>
            </div>

            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title text-lg">⏱️ Duration</h3>
                <p className="text-sm">~{Math.ceil(plan.estimated_duration_seconds / 60)} minutes</p>
              </div>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <p>
              <strong>Auto-enrich:</strong> {autoEnrich ? 'Yes' : 'No'}
            </p>
            <p>
              <strong>Batch size:</strong> {batchSize} transactions/request
            </p>
            <p>
              <strong>Estimated cost:</strong> ${plan.estimated_cost.toFixed(4)}
            </p>
          </div>
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={() => setCurrentStep('config')} disabled={isLoading} className="btn btn-ghost">
          Back
        </button>
        <button onClick={handleStartImport} disabled={isLoading || !plan} className="btn btn-primary">
          {isLoading ? 'Starting...' : 'Start Import'}
        </button>
      </div>
    </div>
  );

  // Step 5: Progress
  const ProgressStep = () => (
    <ImportProgressBar
      jobId={jobId!}
      onComplete={() => {
        if (onImportComplete) {
          onImportComplete(jobId!);
        }
        onClose?.();
      }}
    />
  );

  const handlePlan = async () => {
    setIsLoading(true);
    setError(null);

    try {
      console.log('Planning import with:', {
        connection_id: connection.id,
        from_date: fromDate,
        to_date: toDate,
        account_ids: selectedAccountIds,
        auto_enrich: autoEnrich,
        batch_size: batchSize
      });

      const response = await axios.post(`${API_BASE}/truelayer/import/plan`, {
        connection_id: connection.id,
        from_date: fromDate,
        to_date: toDate,
        account_ids: selectedAccountIds,
        auto_enrich: autoEnrich,
        batch_size: batchSize
      });

      console.log('Plan response:', response.data);
      setPlan(response.data);
      setJobId(response.data.job_id);
      setCurrentStep('review');
    } catch (err: any) {
      const errorMsg = err.response?.data?.error || err.message || 'Failed to plan import';
      console.error('Plan error:', errorMsg, err);
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartImport = async () => {
    if (!jobId) return;

    setIsLoading(true);
    setError(null);

    try {
      await axios.post(`${API_BASE}/truelayer/import/start`, {
        job_id: jobId
      });

      setCurrentStep('progress');
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to start import');
      setIsLoading(false);
    }
  };

  return (
    <div className="modal modal-open">
      <div className="modal-box w-full max-w-2xl">
        {currentStep === 'daterange' && <DateRangeStep />}
        {currentStep === 'accounts' && <AccountSelectionStep />}
        {currentStep === 'config' && <ConfigurationStep />}
        {currentStep === 'review' && <ReviewStep />}
        {currentStep === 'progress' && jobId && <ProgressStep />}
      </div>
    </div>
  );
};
