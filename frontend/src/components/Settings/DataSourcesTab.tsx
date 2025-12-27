import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { GmailDateRangeSelector, getDefaultDateRange } from '../GmailDateRangeSelector';
import { GmailSyncProgressBar } from '../GmailSyncProgressBar';

const API_URL = 'http://localhost:5000/api';

// Types
interface SourceCoverageData {
  bank_transactions: {
    max_date: string | null;
    count: number;
  };
  amazon: {
    max_date: string | null;
    count: number;
  };
  apple: {
    max_date: string | null;
    count: number;
  };
  gmail: {
    max_date: string | null;
    count: number;
  };
  stale_sources: string[];
  has_stale_sources: boolean;
}

interface PreEnrichmentSummary {
  Apple: number;
  AMZN: number;
  'AMZN RTN': number;
  total: number;
}

interface AmazonStats {
  total_orders: number;
  total_matched: number;
  total_unmatched: number;
  min_order_date: string | null;
  max_order_date: string | null;
}

interface ReturnsStats {
  total_returns: number;
  matched_returns: number;
  unmatched_returns: number;
  min_return_date: string | null;
  max_return_date: string | null;
}

interface AppleStats {
  total_transactions: number;
  matched_transactions: number;
  unmatched_transactions: number;
  min_transaction_date: string | null;
  max_transaction_date: string | null;
}

interface AmazonBusinessStats {
  total_orders: number;
  total_matched: number;
  total_unmatched: number;
  min_order_date: string | null;
  max_order_date: string | null;
}

interface GmailStats {
  total_receipts: number;
  parsed_receipts: number;
  matched_receipts: number;
  pending_receipts: number;
  failed_receipts: number;
  min_receipt_date: string | null;
  max_receipt_date: string | null;
}

interface GmailConnection {
  id: number;
  email_address: string;
  connection_status: string;
  last_synced_at: string | null;
}

interface GmailReceipt {
  id: number;
  message_id: string;
  sender_email: string;
  subject: string;
  received_at: string;
  merchant_name: string | null;
  total_amount: number | null;
  receipt_date: string | null;
  parsing_status: string;
  matched_transaction_id: number | null;
}

interface AmazonBusinessConnection {
  connected: boolean;
  connection_id?: number;
  region?: string;
  status?: string;
}

interface AmazonOrder {
  id: number;
  order_id: string;
  order_date: string;
  product_names: string;
  total_owed: number;
  website: string;
}

interface AmazonReturn {
  id: number;
  order_id: string;
  refund_completion_date: string;
  amount_refunded: number;
  status: string | null;
  original_transaction_id: number | null;
  refund_transaction_id: number | null;
}

interface AppleTransaction {
  id: number;
  order_date: string;
  app_names: string;
  publishers: string | null;
  total_amount: number;
  item_count: number;
  matched_bank_transaction_id: number | null;
}

type VendorType = 'amazon' | 'returns' | 'apple' | 'amazon-business' | 'gmail';
type MatchingJobType = 'amazon' | 'returns' | 'apple';

interface MatchingJob {
  id: number;
  job_type: MatchingJobType;
  status: 'queued' | 'running' | 'completed' | 'failed';
  total_items: number;
  processed_items: number;
  matched_items: number;
  failed_items: number;
  progress_percentage: number;
  error_message?: string;
}

export default function DataSourcesTab() {
  // Summary and stats
  const [summary, setSummary] = useState<PreEnrichmentSummary | null>(null);
  const [amazonStats, setAmazonStats] = useState<AmazonStats | null>(null);
  const [returnsStats, setReturnsStats] = useState<ReturnsStats | null>(null);
  const [appleStats, setAppleStats] = useState<AppleStats | null>(null);
  const [loading, setLoading] = useState(true);

  // Source coverage for stale data warning
  const [sourceCoverage, setSourceCoverage] = useState<SourceCoverageData | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(true);

  // Import modal state
  const [importModalOpen, setImportModalOpen] = useState<VendorType | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [selectedFileName, setSelectedFileName] = useState<string>('');
  const [importing, setImporting] = useState(false);

  // Action states
  const [matching, setMatching] = useState<VendorType | null>(null);

  // Matching job state for async operations
  const [matchingJobs, setMatchingJobs] = useState<Record<MatchingJobType, MatchingJob | null>>({
    amazon: null,
    returns: null,
    apple: null,
  });

  // Apple browser import state
  const [appleBrowserStatus, setAppleBrowserStatus] = useState<'idle' | 'launching' | 'ready' | 'scrolling' | 'capturing'>('idle');
  const [appleBrowserError, setAppleBrowserError] = useState<string | null>(null);
  const [appleImportResult, setAppleImportResult] = useState<{
    imported: number;
    duplicates: number;
    matched: number;
  } | null>(null);

  // Amazon Business state
  const [amazonBusinessStats, setAmazonBusinessStats] = useState<AmazonBusinessStats | null>(null);
  const [amazonBusinessConnection, setAmazonBusinessConnection] = useState<AmazonBusinessConnection | null>(null);
  const [amazonBusinessImporting, setAmazonBusinessImporting] = useState(false);
  const [amazonBusinessDateFrom, setAmazonBusinessDateFrom] = useState('');
  const [amazonBusinessDateTo, setAmazonBusinessDateTo] = useState('');
  const [amazonBusinessImportResult, setAmazonBusinessImportResult] = useState<any>(null);

  // Gmail state
  const [gmailStats, setGmailStats] = useState<GmailStats | null>(null);
  const [gmailConnection, setGmailConnection] = useState<GmailConnection | null>(null);
  const [gmailSyncing, setGmailSyncing] = useState(false);
  const [gmailParsing, setGmailParsing] = useState(false);
  const [gmailSyncResult, setGmailSyncResult] = useState<any>(null);
  const [gmailJobId, setGmailJobId] = useState<number | null>(null);
  const [gmailFromDate, setGmailFromDate] = useState(() => getDefaultDateRange().fromDate);
  const [gmailToDate, setGmailToDate] = useState(() => getDefaultDateRange().toDate);

  // View expanded state
  const [expanded, setExpanded] = useState<VendorType | null>(null);
  const [expandedData, setExpandedData] = useState<any[]>([]);
  const [loadingExpanded, setLoadingExpanded] = useState(false);

  // Progress tracker expanded state
  const [progressExpanded, setProgressExpanded] = useState<MatchingJobType | null>(null);

  const fetchAllStats = useCallback(async () => {
    setLoading(true);
    setCoverageLoading(true);

    // Use Promise.allSettled to handle partial failures gracefully
    const results = await Promise.allSettled([
      axios.get<PreEnrichmentSummary>(`${API_URL}/pre-enrichment/summary`),
      axios.get<AmazonStats>(`${API_URL}/amazon/statistics`),
      axios.get<ReturnsStats>(`${API_URL}/amazon/returns/statistics`),
      axios.get<AppleStats>(`${API_URL}/apple/statistics`),
      axios.get<AmazonBusinessStats>(`${API_URL}/amazon-business/statistics`),
      axios.get<AmazonBusinessConnection>(`${API_URL}/amazon-business/connection`),
      axios.get(`${API_URL}/gmail/connection`),
      axios.get<SourceCoverageData>(`${API_URL}/matching/coverage`),
    ]);

    // Set state for each successful request
    if (results[0].status === 'fulfilled') setSummary(results[0].value.data);
    if (results[1].status === 'fulfilled') setAmazonStats(results[1].value.data);
    if (results[2].status === 'fulfilled') setReturnsStats(results[2].value.data);
    if (results[3].status === 'fulfilled') setAppleStats(results[3].value.data);
    if (results[4].status === 'fulfilled') setAmazonBusinessStats(results[4].value.data);
    if (results[5].status === 'fulfilled') setAmazonBusinessConnection(results[5].value.data);
    if (results[6].status === 'fulfilled') {
      const gmailData = results[6].value.data;
      if (gmailData.connected) {
        setGmailConnection(gmailData.connection);
        setGmailStats(gmailData.statistics);
      } else {
        setGmailConnection(null);
        setGmailStats(null);
      }
    }
    if (results[7].status === 'fulfilled') setSourceCoverage(results[7].value.data);

    // Log any failures for debugging
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const endpoints = ['pre-enrichment/summary', 'amazon/statistics', 'amazon/returns/statistics',
                          'apple/statistics', 'amazon-business/statistics', 'amazon-business/connection',
                          'gmail/connection', 'matching/coverage'];
        console.warn(`Failed to fetch ${endpoints[index]}:`, result.reason?.message || result.reason);
      }
    });

    setLoading(false);
    setCoverageLoading(false);
  }, []);

  useEffect(() => {
    fetchAllStats();
  }, [fetchAllStats]);

  // Check for saved Gmail sync job on mount and resume if still active
  useEffect(() => {
    const checkSavedGmailJob = async () => {
      const savedJobId = localStorage.getItem('preai_gmail_job_id');
      if (!savedJobId) return;

      try {
        // Check if job is still running
        const response = await axios.get(`${API_URL}/gmail/sync/${savedJobId}`);
        const job = response.data;

        if (job.status === 'queued' || job.status === 'running') {
          // Resume polling and open the import drawer to show progress
          setGmailJobId(parseInt(savedJobId));
          setGmailSyncing(true);
          setImportModalOpen('gmail');
        } else {
          // Job completed or failed while away, clear storage
          localStorage.removeItem('preai_gmail_job_id');
        }
      } catch (err) {
        // Job not found or error, clear storage
        localStorage.removeItem('preai_gmail_job_id');
      }
    };

    checkSavedGmailJob();
  }, []);

  // Import handlers
  const openImportModal = (vendor: VendorType) => {
    setImportModalOpen(vendor);
    setFileContent('');
    setSelectedFileName('');

    // Apple uses browser import, not file selection
    if (vendor === 'apple') {
      setAppleBrowserStatus('idle');
      setAppleBrowserError(null);
      setAppleImportResult(null);
      return;
    }

    // Amazon Business uses API import with date range
    if (vendor === 'amazon-business') {
      setAmazonBusinessImportResult(null);
      // Set default date range to last 30 days
      const today = new Date();
      const thirtyDaysAgo = new Date(today);
      thirtyDaysAgo.setDate(today.getDate() - 30);
      setAmazonBusinessDateFrom(thirtyDaysAgo.toISOString().split('T')[0]);
      setAmazonBusinessDateTo(today.toISOString().split('T')[0]);
      return;
    }
  };

  // Handle file selection from system file browser
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      setFileContent(event.target?.result as string);
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    if (!fileContent || !importModalOpen) return;

    try {
      setImporting(true);
      let endpoint = '';
      let payload: any = { csv_content: fileContent, filename: selectedFileName };

      if (importModalOpen === 'amazon') {
        endpoint = '/amazon/import';
      } else if (importModalOpen === 'returns') {
        endpoint = '/amazon/returns/import';
      } else {
        endpoint = '/apple/import';
      }

      const response = await axios.post(`${API_URL}${endpoint}`, payload);

      setImportModalOpen(null);
      setFileContent('');
      setSelectedFileName('');
      await fetchAllStats();
      window.dispatchEvent(new Event('transactions-updated'));

      const data = response.data;
      const importCount = data.orders_imported ?? data.returns_imported ?? data.transactions_imported ?? 0;
      const duplicates = data.orders_duplicated ?? data.returns_duplicated ?? data.transactions_duplicated ?? 0;
      const results = data.matching_results;

      alert(`Import Complete!\n\nImported: ${importCount}\nDuplicates: ${duplicates}\n\nMatching:\n- Processed: ${results.total_processed}\n- Matched: ${results.matched}\n- Unmatched: ${results.unmatched}`);
    } catch (err: any) {
      alert(`Import failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setImporting(false);
    }
  };

  // Helper to poll matching job status
  const pollMatchingJobStatus = useCallback(async (jobId: number, jobType: MatchingJobType) => {
    const poll = async () => {
      try {
        const response = await axios.get(`${API_URL}/matching/jobs/${jobId}`);
        const job: MatchingJob = response.data;

        setMatchingJobs(prev => ({ ...prev, [jobType]: job }));

        if (job.status === 'completed') {
          // Clear localStorage
          localStorage.removeItem(`preai_matching_job_${jobType}`);

          // Refresh stats
          await fetchAllStats();
          window.dispatchEvent(new Event('transactions-updated'));

          // Show completion message
          alert(`${jobType.charAt(0).toUpperCase() + jobType.slice(1)} Matching Complete!\n\nProcessed: ${job.total_items}\nMatched: ${job.matched_items}\nUnmatched: ${job.total_items - job.matched_items}`);

          // Clear job state after a delay to show completion
          setTimeout(() => {
            setMatchingJobs(prev => ({ ...prev, [jobType]: null }));
            setMatching(null);
          }, 1000);
        } else if (job.status === 'failed') {
          // Clear localStorage
          localStorage.removeItem(`preai_matching_job_${jobType}`);

          alert(`${jobType.charAt(0).toUpperCase() + jobType.slice(1)} Matching Failed: ${job.error_message || 'Unknown error'}`);
          setMatchingJobs(prev => ({ ...prev, [jobType]: null }));
          setMatching(null);
        } else {
          // Still running, poll again
          setTimeout(poll, 2000);
        }
      } catch (err) {
        console.error(`Failed to poll matching job ${jobId}:`, err);
        localStorage.removeItem(`preai_matching_job_${jobType}`);
        setMatchingJobs(prev => ({ ...prev, [jobType]: null }));
        setMatching(null);
      }
    };

    poll();
  }, [fetchAllStats]);

  // Check for active matching jobs on mount
  useEffect(() => {
    const checkActiveMatchingJobs = async () => {
      // Check localStorage for saved job IDs
      const jobTypes: MatchingJobType[] = ['amazon', 'returns', 'apple'];

      for (const jobType of jobTypes) {
        const savedJobId = localStorage.getItem(`preai_matching_job_${jobType}`);
        if (savedJobId) {
          try {
            const response = await axios.get(`${API_URL}/matching/jobs/${savedJobId}`);
            const job: MatchingJob = response.data;

            if (job.status === 'queued' || job.status === 'running') {
              setMatchingJobs(prev => ({ ...prev, [jobType]: job }));
              setMatching(jobType);
              pollMatchingJobStatus(parseInt(savedJobId), jobType);
            } else {
              // Job is complete or failed, clear localStorage
              localStorage.removeItem(`preai_matching_job_${jobType}`);
            }
          } catch (err) {
            // Job not found, clear localStorage
            localStorage.removeItem(`preai_matching_job_${jobType}`);
          }
        }
      }
    };

    checkActiveMatchingJobs();
  }, [pollMatchingJobStatus]);

  // Match handler
  const handleMatch = async (vendor: VendorType) => {
    // Check if this vendor uses async matching
    const isAsyncVendor = vendor === 'amazon' || vendor === 'returns' || vendor === 'apple';

    try {
      setMatching(vendor);
      const endpoint = vendor === 'amazon'
        ? '/amazon/match'
        : vendor === 'returns'
        ? '/amazon/returns/match'
        : vendor === 'amazon-business'
        ? '/amazon-business/match'
        : vendor === 'gmail'
        ? '/gmail/match'
        : '/apple/match';

      if (isAsyncVendor) {
        // Use async mode for Amazon, Returns, Apple
        const response = await axios.post(`${API_URL}${endpoint}?async=true`);
        const { job_id } = response.data;

        // Save job ID to localStorage for resume on navigation
        localStorage.setItem(`preai_matching_job_${vendor}`, job_id.toString());

        // Start polling for status
        setMatchingJobs(prev => ({
          ...prev,
          [vendor]: {
            id: job_id,
            job_type: vendor as MatchingJobType,
            status: 'queued',
            total_items: 0,
            processed_items: 0,
            matched_items: 0,
            failed_items: 0,
            progress_percentage: 0,
          },
        }));

        pollMatchingJobStatus(job_id, vendor as MatchingJobType);
      } else {
        // Sync mode for gmail and amazon-business
        const response = await axios.post(`${API_URL}${endpoint}`, {});
        const results = response.data.results || response.data;

        await fetchAllStats();
        window.dispatchEvent(new Event('transactions-updated'));

        alert(`Matching Complete!\n\nProcessed: ${results.total_processed}\nMatched: ${results.matched}\nUnmatched: ${results.unmatched}`);
        setMatching(null);
      }
    } catch (err: any) {
      alert(`Matching failed: ${err.response?.data?.error || err.message}`);
      setMatching(null);
    }
  };

  // View handler
  const handleView = async (vendor: VendorType) => {
    if (expanded === vendor) {
      setExpanded(null);
      setExpandedData([]);
      return;
    }

    try {
      setLoadingExpanded(true);
      setExpanded(vendor);

      const endpoint = vendor === 'amazon'
        ? '/amazon/orders'
        : vendor === 'returns'
        ? '/amazon/returns'
        : vendor === 'amazon-business'
        ? '/amazon-business/orders'
        : vendor === 'gmail'
        ? '/gmail/receipts'
        : '/apple';

      const response = await axios.get(`${API_URL}${endpoint}`);
      // Amazon Business returns array directly, others use objects
      const data = vendor === 'amazon-business'
        ? response.data
        : response.data.orders ?? response.data.returns ?? response.data.transactions ?? response.data.receipts ?? [];
      setExpandedData(data);
    } catch (err) {
      console.error('Error fetching data:', err);
      setExpandedData([]);
    } finally {
      setLoadingExpanded(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-GB');
  };

  const formatCurrency = (amount: number) => `£${Math.abs(amount).toFixed(2)}`;

  // Apple browser import handlers
  const handleAppleBrowserStart = async () => {
    try {
      setAppleBrowserStatus('launching');
      setAppleBrowserError(null);
      setAppleImportResult(null);

      await axios.post(`${API_URL}/apple/import/browser-start`);
      setAppleBrowserStatus('ready');
    } catch (err: any) {
      setAppleBrowserError(err.response?.data?.error || err.message);
      setAppleBrowserStatus('idle');
    }
  };

  const handleAppleBrowserCapture = async () => {
    try {
      // First show scrolling status, then it will switch to capturing
      setAppleBrowserStatus('scrolling');
      setAppleBrowserError(null);

      const response = await axios.post(`${API_URL}/apple/import/browser-capture`);
      const data = response.data;

      setAppleImportResult({
        imported: data.transactions_imported,
        duplicates: data.transactions_duplicated,
        matched: data.matching_results?.matched || 0
      });

      await fetchAllStats();
      window.dispatchEvent(new Event('transactions-updated'));
      setAppleBrowserStatus('idle');
    } catch (err: any) {
      setAppleBrowserError(err.response?.data?.error || err.message);
      setAppleBrowserStatus('idle');
    }
  };

  const handleAppleBrowserCancel = async () => {
    try {
      await axios.post(`${API_URL}/apple/import/browser-cancel`);
    } catch (err) {
      console.error('Error cancelling browser session:', err);
    }
    setAppleBrowserStatus('idle');
    setAppleBrowserError(null);
    setAppleImportResult(null);
    setImportModalOpen(null);
  };

  const closeAppleModal = () => {
    if (appleBrowserStatus === 'ready') {
      // Browser is open, need to cancel it
      handleAppleBrowserCancel();
    } else {
      setImportModalOpen(null);
      setAppleBrowserStatus('idle');
      setAppleBrowserError(null);
      setAppleImportResult(null);
    }
  };

  // Amazon Business handlers
  const handleAmazonBusinessConnect = async () => {
    try {
      const response = await axios.get(`${API_URL}/amazon-business/authorize`);
      if (response.data.success) {
        // Open authorization URL in new window
        window.open(response.data.authorization_url, '_blank', 'width=600,height=700');
      } else {
        alert(`Connection failed: ${response.data.error}`);
      }
    } catch (err: any) {
      alert(`Connection failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleAmazonBusinessDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect Amazon Business?')) return;

    try {
      await axios.post(`${API_URL}/amazon-business/disconnect`);
      await fetchAllStats();
      alert('Amazon Business disconnected');
    } catch (err: any) {
      alert(`Disconnect failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleAmazonBusinessImport = async () => {
    if (!amazonBusinessDateFrom || !amazonBusinessDateTo) {
      alert('Please select date range');
      return;
    }

    try {
      setAmazonBusinessImporting(true);
      const response = await axios.post(`${API_URL}/amazon-business/import`, {
        start_date: amazonBusinessDateFrom,
        end_date: amazonBusinessDateTo,
        run_matching: true
      });

      if (response.data.success) {
        setAmazonBusinessImportResult(response.data);
        await fetchAllStats();
        window.dispatchEvent(new Event('transactions-updated'));
      } else {
        alert(`Import failed: ${response.data.error}`);
      }
    } catch (err: any) {
      alert(`Import failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setAmazonBusinessImporting(false);
    }
  };

  const closeAmazonBusinessModal = () => {
    setImportModalOpen(null);
    setAmazonBusinessImportResult(null);
  };

  // Gmail handlers
  const handleGmailConnect = async () => {
    try {
      const response = await axios.get(`${API_URL}/gmail/authorize`);
      const { auth_url, state, code_verifier } = response.data;

      sessionStorage.setItem('gmail_state', state);
      sessionStorage.setItem('gmail_code_verifier', code_verifier);

      window.location.href = auth_url;
    } catch (err: any) {
      alert(`Gmail connection failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleGmailSync = async () => {
    if (!gmailConnection) return;

    try {
      setGmailSyncing(true);
      setGmailSyncResult(null);
      setGmailJobId(null);

      const response = await axios.post(`${API_URL}/gmail/sync`, {
        connection_id: gmailConnection.id,
        sync_type: 'full',
        from_date: gmailFromDate,
        to_date: gmailToDate,
      });

      // Store job ID for progress bar to poll
      if (response.data.job_id) {
        setGmailJobId(response.data.job_id);
        // Persist to localStorage for navigation recovery
        localStorage.setItem('preai_gmail_job_id', response.data.job_id.toString());
      } else {
        // Sync was synchronous (rare case)
        setGmailSyncResult(response.data);
        setGmailSyncing(false);
        await fetchAllStats();
        window.dispatchEvent(new Event('transactions-updated'));
      }
    } catch (err: any) {
      alert(`Sync failed: ${err.response?.data?.error || err.message}`);
      setGmailSyncing(false);
    }
  };

  const handleGmailSyncComplete = async (result: any) => {
    setGmailJobId(null);
    setGmailSyncing(false);
    // Clear localStorage on completion
    localStorage.removeItem('preai_gmail_job_id');
    setGmailSyncResult({
      parsed: result.parsed_receipts,
      duplicates: result.total_messages - result.parsed_receipts - result.failed_messages,
      failed: result.failed_messages,
    });
    await fetchAllStats();
    window.dispatchEvent(new Event('transactions-updated'));
  };

  const handleGmailSyncError = (error: string) => {
    setGmailJobId(null);
    setGmailSyncing(false);
    // Clear localStorage on error
    localStorage.removeItem('preai_gmail_job_id');
    alert(`Sync failed: ${error}`);
  };

  const handleGmailParse = async () => {
    if (!gmailConnection) return;

    try {
      setGmailParsing(true);
      const response = await axios.post(`${API_URL}/gmail/parse`, {
        connection_id: gmailConnection.id
      });

      alert(`Parsed ${response.data.parsed} receipts successfully`);
      await fetchAllStats();
    } catch (err: any) {
      alert(`Parsing failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setGmailParsing(false);
    }
  };

  const handleGmailDisconnect = async () => {
    if (!gmailConnection) return;
    if (!confirm('Are you sure you want to disconnect Gmail? All synced receipts will be deleted.')) return;

    try {
      await axios.post(`${API_URL}/gmail/disconnect`, {
        connection_id: gmailConnection.id
      });
      setGmailConnection(null);
      setGmailStats(null);
      setGmailSyncResult(null);
      await fetchAllStats();
      window.dispatchEvent(new Event('transactions-updated'));
      alert('Gmail disconnected successfully');
    } catch (err: any) {
      alert(`Disconnect failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const closeGmailModal = () => {
    setImportModalOpen(null);
    setGmailSyncResult(null);
  };

  // Get counts for each vendor
  const getIdentified = (vendor: VendorType): number => {
    if (!summary) return 0;
    if (vendor === 'amazon') return summary.AMZN;
    if (vendor === 'returns') return summary['AMZN RTN'];
    if (vendor === 'amazon-business') return amazonBusinessStats?.total_unmatched ?? 0;
    if (vendor === 'gmail') return gmailStats?.parsed_receipts ?? 0;
    return summary.Apple;
  };

  const getMatched = (vendor: VendorType): number => {
    if (vendor === 'amazon') return amazonStats?.total_matched ?? 0;
    if (vendor === 'returns') return returnsStats?.matched_returns ?? 0;
    if (vendor === 'amazon-business') return amazonBusinessStats?.total_matched ?? 0;
    if (vendor === 'gmail') return gmailStats?.matched_receipts ?? 0;
    return appleStats?.matched_transactions ?? 0;
  };

  const hasData = (vendor: VendorType): boolean => {
    if (vendor === 'amazon') return (amazonStats?.total_orders ?? 0) > 0;
    if (vendor === 'returns') return (returnsStats?.total_returns ?? 0) > 0;
    if (vendor === 'amazon-business') return (amazonBusinessStats?.total_orders ?? 0) > 0;
    if (vendor === 'gmail') return (gmailStats?.total_receipts ?? 0) > 0;
    return (appleStats?.total_transactions ?? 0) > 0;
  };

  const getDateRange = (vendor: VendorType): string => {
    if (vendor === 'amazon' && amazonStats?.min_order_date && amazonStats?.max_order_date) {
      return `${formatDate(amazonStats.min_order_date)} – ${formatDate(amazonStats.max_order_date)}`;
    }
    if (vendor === 'returns' && returnsStats?.min_return_date && returnsStats?.max_return_date) {
      return `${formatDate(returnsStats.min_return_date)} – ${formatDate(returnsStats.max_return_date)}`;
    }
    if (vendor === 'apple' && appleStats?.min_transaction_date && appleStats?.max_transaction_date) {
      return `${formatDate(appleStats.min_transaction_date)} – ${formatDate(appleStats.max_transaction_date)}`;
    }
    if (vendor === 'amazon-business' && amazonBusinessStats?.min_order_date && amazonBusinessStats?.max_order_date) {
      return `${formatDate(amazonBusinessStats.min_order_date)} – ${formatDate(amazonBusinessStats.max_order_date)}`;
    }
    if (vendor === 'gmail' && gmailStats?.min_receipt_date && gmailStats?.max_receipt_date) {
      return `${formatDate(gmailStats.min_receipt_date)} – ${formatDate(gmailStats.max_receipt_date)}`;
    }
    return '—';
  };

  const vendors: { key: VendorType; label: string }[] = [
    { key: 'amazon', label: 'Amazon Purchases' },
    { key: 'returns', label: 'Amazon Returns' },
    { key: 'apple', label: 'Apple App Store' },
    { key: 'amazon-business', label: 'Amazon Business' },
    { key: 'gmail', label: 'Gmail Receipts' }
  ];

  if (loading) {
    return (
      <div className="flex justify-center items-center p-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Format date for display
  const formatCoverageDate = (dateStr: string | null): string => {
    if (!dateStr) return 'No data';
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  };

  return (
    <div className="space-y-6">
      {/* Stale Sources Warning Banner */}
      {!coverageLoading && sourceCoverage?.has_stale_sources && (
        <div className="alert alert-warning shadow-lg">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current flex-shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="font-bold">Some data sources may be outdated</h3>
            <div className="text-sm mt-1 space-y-1">
              <p className="text-base-content/80">
                Bank transactions: through {formatCoverageDate(sourceCoverage.bank_transactions.max_date)}
              </p>
              {sourceCoverage.stale_sources.map((source) => (
                <p key={source} className="text-base-content/70">
                  • {source.charAt(0).toUpperCase() + source.slice(1)}: last data{' '}
                  {formatCoverageDate(
                    source === 'amazon' ? sourceCoverage.amazon.max_date :
                    source === 'apple' ? sourceCoverage.apple.max_date :
                    source === 'gmail' ? sourceCoverage.gmail.max_date :
                    null
                  )}
                </p>
              ))}
            </div>
          </div>
          <div className="flex-none">
            <button className="btn btn-sm btn-ghost" onClick={() => setSourceCoverage(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Vendor Data Table */}
      <div className="overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th>Vendor Data</th>
              <th>Date Range</th>
              <th className="text-center">Identified</th>
              <th className="text-center">Matched</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {vendors.map(({ key, label }) => (
              <React.Fragment key={key}>
                <tr className="hover">
                  <td className="font-medium">
                    <div className="flex items-center gap-2">
                      {label}
                      {/* Show "Working" badge for async matching jobs */}
                      {matchingJobs[key as MatchingJobType] && (
                        <button
                          className="badge badge-warning badge-sm gap-1 cursor-pointer hover:badge-accent transition-colors"
                          onClick={() => setProgressExpanded(
                            progressExpanded === key ? null : key as MatchingJobType
                          )}
                          title="Click to expand progress"
                        >
                          <span className="loading loading-spinner loading-xs"></span>
                          Working
                        </button>
                      )}
                      {/* Show "Working" badge for Gmail sync */}
                      {key === 'gmail' && gmailSyncing && (
                        <span className="badge badge-warning badge-sm">
                          Syncing
                          <span className="inline-flex ml-0.5">
                            <span className="animate-dot-pulse" style={{ animationDelay: '0s' }}>•</span>
                            <span className="animate-dot-pulse" style={{ animationDelay: '0.2s' }}>•</span>
                            <span className="animate-dot-pulse" style={{ animationDelay: '0.4s' }}>•</span>
                          </span>
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="text-sm text-base-content/70">{getDateRange(key)}</td>
                  <td className="text-center">
                    <span className={getIdentified(key) > 0 ? 'text-warning font-semibold' : 'text-base-content/50'}>
                      {getIdentified(key)}
                    </span>
                  </td>
                  <td className="text-center">
                    <span className={getMatched(key) > 0 ? 'text-success font-semibold' : 'text-base-content/50'}>
                      {getMatched(key)}
                    </span>
                  </td>
                  <td className="text-right">
                    <div className="flex gap-2 justify-end">
                      <button
                        className="btn btn-xs btn-primary"
                        onClick={() => openImportModal(key)}
                      >
                        Import
                      </button>
                      <button
                        className="btn btn-xs btn-outline"
                        onClick={() => handleView(key)}
                        disabled={!hasData(key) || loadingExpanded}
                      >
                        {expanded === key ? 'Hide' : 'View'}
                      </button>
                      <button
                        className="btn btn-xs btn-outline"
                        onClick={() => handleMatch(key)}
                        disabled={matching !== null || !hasData(key)}
                      >
                        Match
                      </button>
                    </div>
                  </td>
                </tr>
                {/* Progress tracker row - expands when "Working" badge clicked */}
                {progressExpanded === key && matchingJobs[key as MatchingJobType] && (
                  <tr key={`${key}-progress`}>
                    <td colSpan={5} className="bg-base-200 border-l-4 border-warning p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className="flex flex-col">
                            <span className="text-sm font-medium">
                              {key.charAt(0).toUpperCase() + key.slice(1)} Matching
                            </span>
                            <span className="text-xs text-base-content/70">
                              Status: {matchingJobs[key as MatchingJobType]?.status || 'unknown'}
                            </span>
                          </div>
                          <div className="divider divider-horizontal"></div>
                          <div className="stats stats-horizontal bg-base-100 shadow-sm">
                            <div className="stat py-2 px-4">
                              <div className="stat-title text-xs">Total</div>
                              <div className="stat-value text-lg">
                                {matchingJobs[key as MatchingJobType]?.total_items || '—'}
                              </div>
                            </div>
                            <div className="stat py-2 px-4">
                              <div className="stat-title text-xs">Matched</div>
                              <div className="stat-value text-lg text-success">
                                {matchingJobs[key as MatchingJobType]?.matched_items || 0}
                              </div>
                            </div>
                            <div className="stat py-2 px-4">
                              <div className="stat-title text-xs">Unmatched</div>
                              <div className="stat-value text-lg text-warning">
                                {(matchingJobs[key as MatchingJobType]?.total_items || 0) -
                                 (matchingJobs[key as MatchingJobType]?.matched_items || 0)}
                              </div>
                            </div>
                          </div>
                        </div>
                        <button
                          className="btn btn-xs btn-ghost"
                          onClick={() => setProgressExpanded(null)}
                        >
                          ✕
                        </button>
                      </div>
                      {matchingJobs[key as MatchingJobType]?.total_items ? (
                        <progress
                          className="progress progress-warning w-full mt-3"
                          value={matchingJobs[key as MatchingJobType]?.processed_items || 0}
                          max={matchingJobs[key as MatchingJobType]?.total_items || 100}
                        ></progress>
                      ) : (
                        <progress className="progress progress-warning w-full mt-3"></progress>
                      )}
                    </td>
                  </tr>
                )}
                {/* Import drawer row */}
                {importModalOpen === key && (
                  <tr key={`${key}-import`}>
                    <td colSpan={5} className="bg-base-100 border-l-4 border-primary p-4">
                      {/* Amazon/Returns file import */}
                      {(key === 'amazon' || key === 'returns') && (
                        <div className="flex items-center gap-4">
                          <div className="flex-1">
                            <input
                              type="file"
                              accept=".csv"
                              className="file-input file-input-bordered file-input-sm w-full max-w-md"
                              onChange={handleFileSelect}
                            />
                            {selectedFileName && (
                              <span className="ml-2 text-sm text-success">{selectedFileName}</span>
                            )}
                          </div>
                          <div className="flex gap-2">
                            <button
                              className="btn btn-sm btn-ghost"
                              onClick={() => {
                                setImportModalOpen(null);
                                setFileContent('');
                                setSelectedFileName('');
                              }}
                              disabled={importing}
                            >
                              Cancel
                            </button>
                            <button
                              className="btn btn-sm btn-primary"
                              onClick={handleImport}
                              disabled={!fileContent || importing}
                            >
                              {importing ? (
                                <>
                                  <span className="loading loading-spinner loading-xs"></span>
                                  Importing...
                                </>
                              ) : (
                                'Import'
                              )}
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Apple browser import */}
                      {key === 'apple' && (
                        <div className="space-y-3">
                          {appleBrowserStatus === 'idle' && !appleImportResult && (
                            <div className="flex items-center gap-4">
                              <p className="text-sm flex-1">
                                Launch Apple's purchase history page, log in, then capture transactions.
                              </p>
                              <button className="btn btn-sm btn-primary" onClick={handleAppleBrowserStart}>
                                Open Browser
                              </button>
                              <button className="btn btn-sm btn-ghost" onClick={closeAppleModal}>
                                Cancel
                              </button>
                            </div>
                          )}

                          {appleBrowserStatus === 'launching' && (
                            <div className="flex items-center gap-2">
                              <span className="loading loading-spinner loading-sm"></span>
                              <span>Launching browser...</span>
                            </div>
                          )}

                          {appleBrowserStatus === 'ready' && (
                            <div className="flex items-center gap-4">
                              <div className="flex-1">
                                <span className="badge badge-info badge-sm mr-2">Browser Open</span>
                                <span className="text-sm">Log in and navigate to purchase history, then click Capture.</span>
                              </div>
                              <button className="btn btn-sm btn-success" onClick={handleAppleBrowserCapture}>
                                Capture Transactions
                              </button>
                              <button className="btn btn-sm btn-ghost" onClick={closeAppleModal}>
                                Cancel
                              </button>
                            </div>
                          )}

                          {(appleBrowserStatus === 'scrolling' || appleBrowserStatus === 'capturing') && (
                            <div className="flex items-center gap-2">
                              <span className="loading loading-spinner loading-sm"></span>
                              <span>{appleBrowserStatus === 'scrolling' ? 'Scrolling to load all transactions...' : 'Capturing transactions...'}</span>
                            </div>
                          )}

                          {appleImportResult && (
                            <div className="flex items-center gap-4">
                              <div className="flex-1">
                                <span className="badge badge-success badge-sm mr-2">Complete</span>
                                <span className="text-sm">
                                  Imported: {appleImportResult.imported} | Duplicates: {appleImportResult.duplicates} | Matched: {appleImportResult.matched}
                                </span>
                              </div>
                              <button className="btn btn-sm btn-ghost" onClick={closeAppleModal}>
                                Close
                              </button>
                            </div>
                          )}

                          {appleBrowserError && (
                            <div className="text-error text-sm">{appleBrowserError}</div>
                          )}
                        </div>
                      )}

                      {/* Amazon Business import */}
                      {key === 'amazon-business' && (
                        <div className="space-y-3">
                          {!amazonBusinessConnection?.connected ? (
                            <div className="flex items-center gap-4">
                              <p className="text-sm flex-1">Connect your Amazon Business account to import orders via API.</p>
                              <button className="btn btn-sm btn-primary" onClick={handleAmazonBusinessConnect}>
                                Connect Amazon Business
                              </button>
                              <button className="btn btn-sm btn-ghost" onClick={closeAmazonBusinessModal}>
                                Cancel
                              </button>
                            </div>
                          ) : amazonBusinessImportResult ? (
                            <div className="flex items-center gap-4">
                              <div className="flex-1">
                                <span className="badge badge-success badge-sm mr-2">Complete</span>
                                <span className="text-sm">
                                  Imported: {amazonBusinessImportResult.import?.orders_imported || 0} |
                                  Duplicates: {amazonBusinessImportResult.import?.orders_duplicates || 0} |
                                  Matched: {amazonBusinessImportResult.matching?.matched || 0}
                                </span>
                              </div>
                              <button className="btn btn-sm btn-ghost" onClick={closeAmazonBusinessModal}>
                                Close
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-4">
                              <span className="badge badge-success badge-sm">Connected ({amazonBusinessConnection.region})</span>
                              <input
                                type="date"
                                className="input input-bordered input-sm"
                                value={amazonBusinessDateFrom}
                                onChange={(e) => setAmazonBusinessDateFrom(e.target.value)}
                              />
                              <span>to</span>
                              <input
                                type="date"
                                className="input input-bordered input-sm"
                                value={amazonBusinessDateTo}
                                onChange={(e) => setAmazonBusinessDateTo(e.target.value)}
                              />
                              <button
                                className="btn btn-sm btn-primary"
                                onClick={handleAmazonBusinessImport}
                                disabled={amazonBusinessImporting || !amazonBusinessDateFrom || !amazonBusinessDateTo}
                              >
                                {amazonBusinessImporting ? (
                                  <>
                                    <span className="loading loading-spinner loading-xs"></span>
                                    Importing...
                                  </>
                                ) : (
                                  'Import'
                                )}
                              </button>
                              <button className="btn btn-sm btn-ghost" onClick={closeAmazonBusinessModal}>
                                Cancel
                              </button>
                              <button
                                className="btn btn-sm btn-outline btn-error"
                                onClick={handleAmazonBusinessDisconnect}
                              >
                                Disconnect
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Gmail receipts import */}
                      {key === 'gmail' && (
                        <div className="space-y-3">
                          {!gmailConnection ? (
                            <div className="flex items-center gap-4">
                              <p className="text-sm flex-1">Connect your Gmail account to sync receipt emails for transaction matching.</p>
                              <button className="btn btn-sm btn-primary" onClick={handleGmailConnect}>
                                Connect Gmail
                              </button>
                              <button className="btn btn-sm btn-ghost" onClick={closeGmailModal}>
                                Cancel
                              </button>
                            </div>
                          ) : gmailJobId ? (
                            // Show progress bar when sync is running
                            <GmailSyncProgressBar
                              jobId={gmailJobId}
                              onComplete={handleGmailSyncComplete}
                              onError={handleGmailSyncError}
                            />
                          ) : gmailSyncResult ? (
                            <div className="flex items-center gap-4">
                              <div className="flex-1">
                                <span className="badge badge-success badge-sm mr-2">Complete</span>
                                <span className="text-sm">
                                  Stored: {gmailSyncResult.parsed || 0} |
                                  Duplicates: {gmailSyncResult.duplicates || 0} |
                                  Failed: {gmailSyncResult.failed || 0}
                                </span>
                              </div>
                              <button className="btn btn-sm btn-ghost" onClick={closeGmailModal}>
                                Close
                              </button>
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {/* Connection status and actions */}
                              <div className="flex items-center gap-4">
                                <span className="badge badge-success badge-sm">Connected ({gmailConnection.email_address})</span>
                                <button
                                  className="btn btn-sm btn-primary"
                                  onClick={handleGmailSync}
                                  disabled={gmailSyncing}
                                >
                                  {gmailSyncing ? (
                                    <>
                                      Starting
                                      <span className="inline-flex ml-0.5">
                                        <span className="animate-dot-pulse" style={{ animationDelay: '0s' }}>•</span>
                                        <span className="animate-dot-pulse" style={{ animationDelay: '0.2s' }}>•</span>
                                        <span className="animate-dot-pulse" style={{ animationDelay: '0.4s' }}>•</span>
                                      </span>
                                    </>
                                  ) : (
                                    'Sync Receipts'
                                  )}
                                </button>
                                <button
                                  className="btn btn-sm btn-outline"
                                  onClick={handleGmailParse}
                                  disabled={gmailParsing || !hasData('gmail')}
                                >
                                  {gmailParsing ? (
                                    <>
                                      <span className="loading loading-spinner loading-xs"></span>
                                      Parsing...
                                    </>
                                  ) : (
                                    'Parse'
                                  )}
                                </button>
                                <button className="btn btn-sm btn-ghost" onClick={closeGmailModal}>
                                  Cancel
                                </button>
                                <button
                                  className="btn btn-sm btn-outline btn-error"
                                  onClick={handleGmailDisconnect}
                                >
                                  Disconnect
                                </button>
                              </div>
                              {/* Date range selector */}
                              <GmailDateRangeSelector
                                fromDate={gmailFromDate}
                                toDate={gmailToDate}
                                onFromDateChange={setGmailFromDate}
                                onToDateChange={setGmailToDate}
                                disabled={gmailSyncing}
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                {/* Expanded view row */}
                {expanded === key && (
                  <tr key={`${key}-expanded`}>
                    <td colSpan={5} className="bg-base-200 p-4">
                      {loadingExpanded ? (
                        <div className="flex justify-center py-4">
                          <span className="loading loading-spinner loading-sm"></span>
                        </div>
                      ) : expandedData.length === 0 ? (
                        <div className="text-center text-base-content/50 py-4">No data</div>
                      ) : (
                        <div className="overflow-x-auto max-h-64 overflow-y-auto">
                          {key === 'amazon' && (
                            <table className="table table-xs">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Order ID</th>
                                  <th>Products</th>
                                  <th>Amount</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(expandedData as AmazonOrder[]).slice(0, 20).map((order) => (
                                  <tr key={order.id}>
                                    <td>{formatDate(order.order_date)}</td>
                                    <td className="font-mono text-xs">{order.order_id}</td>
                                    <td className="max-w-xs truncate">{order.product_names}</td>
                                    <td>{formatCurrency(order.total_owed)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {key === 'returns' && (
                            <table className="table table-xs">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Order ID</th>
                                  <th>Amount</th>
                                  <th>Matched</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(expandedData as AmazonReturn[]).slice(0, 20).map((ret) => (
                                  <tr key={ret.id}>
                                    <td>{formatDate(ret.refund_completion_date)}</td>
                                    <td className="font-mono text-xs">{ret.order_id}</td>
                                    <td className="text-success">{formatCurrency(ret.amount_refunded)}</td>
                                    <td>
                                      {ret.original_transaction_id ? (
                                        <span className="badge badge-success badge-xs">Yes</span>
                                      ) : (
                                        <span className="badge badge-warning badge-xs">No</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {key === 'apple' && (
                            <table className="table table-xs">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>App</th>
                                  <th>Amount</th>
                                  <th>Matched</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(expandedData as AppleTransaction[]).slice(0, 20).map((txn) => (
                                  <tr key={txn.id}>
                                    <td>{formatDate(txn.order_date)}</td>
                                    <td className="max-w-xs truncate">{txn.app_names}</td>
                                    <td>{formatCurrency(txn.total_amount)}</td>
                                    <td>
                                      {txn.matched_bank_transaction_id ? (
                                        <span className="badge badge-success badge-xs">Yes</span>
                                      ) : (
                                        <span className="badge badge-warning badge-xs">No</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {key === 'amazon-business' && (
                            <table className="table table-xs">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Order ID</th>
                                  <th>Products</th>
                                  <th>Amount</th>
                                </tr>
                              </thead>
                              <tbody>
                                {expandedData.slice(0, 20).map((order: any) => (
                                  <tr key={order.id}>
                                    <td>{formatDate(order.order_date)}</td>
                                    <td className="font-mono text-xs">{order.order_id}</td>
                                    <td className="max-w-xs truncate">{order.product_summary || '—'}</td>
                                    <td>{formatCurrency(order.net_total || 0)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {key === 'gmail' && (
                            <table className="table table-xs">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Merchant</th>
                                  <th>Subject</th>
                                  <th>Amount</th>
                                  <th>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(expandedData as GmailReceipt[]).slice(0, 20).map((receipt) => (
                                  <tr key={receipt.id}>
                                    <td>{formatDate(receipt.receipt_date || receipt.received_at)}</td>
                                    <td className="max-w-32 truncate">{receipt.merchant_name || receipt.sender_email}</td>
                                    <td className="max-w-xs truncate">{receipt.subject}</td>
                                    <td>{receipt.total_amount ? formatCurrency(receipt.total_amount) : '—'}</td>
                                    <td>
                                      <div className="flex gap-1">
                                        {receipt.parsing_status === 'parsed' && (
                                          <span className="badge badge-success badge-xs">Parsed</span>
                                        )}
                                        {receipt.parsing_status === 'pending' && (
                                          <span className="badge badge-warning badge-xs">Pending</span>
                                        )}
                                        {(receipt.parsing_status === 'failed' || receipt.parsing_status === 'unparseable') && (
                                          <span className="badge badge-error badge-xs">Failed</span>
                                        )}
                                        {receipt.matched_transaction_id && (
                                          <span className="badge badge-primary badge-xs">Matched</span>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {expandedData.length > 20 && (
                            <div className="text-center text-xs text-base-content/50 mt-2">
                              Showing first 20 of {expandedData.length}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
