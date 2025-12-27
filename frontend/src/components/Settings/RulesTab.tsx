import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type {
  CategoryRule,
  MerchantNormalization,
  RulesStatistics,
  RuleTestResult,
  TestAllRulesResult,
  Category,
} from '../../types';

const API_URL = 'http://localhost:5000/api';

type RuleType = 'all' | 'category' | 'merchant';
type EditingMode = 'none' | 'category' | 'merchant';

interface EditingState {
  mode: EditingMode;
  id: number | null; // null for new rule
  rule_name: string;
  pattern: string;
  pattern_type: 'contains' | 'starts_with' | 'exact' | 'regex';
  transaction_type: 'CREDIT' | 'DEBIT' | null;
  category: string;
  subcategory: string;
  normalized_name: string;
  merchant_type: string;
  priority: number;
  is_active: boolean;
}

const initialEditingState: EditingState = {
  mode: 'none',
  id: null,
  rule_name: '',
  pattern: '',
  pattern_type: 'contains',
  transaction_type: null,
  category: '',
  subcategory: '',
  normalized_name: '',
  merchant_type: '',
  priority: 50,
  is_active: true,
};

export default function RulesTab() {
  // Data state
  const [categoryRules, setCategoryRules] = useState<CategoryRule[]>([]);
  const [merchantRules, setMerchantRules] = useState<MerchantNormalization[]>([]);
  const [statistics, setStatistics] = useState<RulesStatistics | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);

  // Filter state
  const [ruleTypeFilter, setRuleTypeFilter] = useState<RuleType>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [sourceFilter, setSourceFilter] = useState<string>('');
  const [patternSearch, setPatternSearch] = useState<string>('');

  // Editing state
  const [editing, setEditing] = useState<EditingState>(initialEditingState);
  const [testResult, setTestResult] = useState<RuleTestResult | null>(null);
  const [testAllResult, setTestAllResult] = useState<TestAllRulesResult | null>(null);
  const [showTestAllReport, setShowTestAllReport] = useState(false);

  // Loading/status state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testingAll, setTestingAll] = useState(false);
  const [applyingAll, setApplyingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch data on mount
  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      await Promise.all([
        fetchCategoryRules(),
        fetchMerchantRules(),
        fetchStatistics(),
        fetchCategories(),
      ]);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategoryRules = async () => {
    try {
      const response = await axios.get<CategoryRule[]>(`${API_URL}/rules/category`);
      setCategoryRules(response.data);
    } catch (err: any) {
      console.error('Error fetching category rules:', err);
    }
  };

  const fetchMerchantRules = async () => {
    try {
      const response = await axios.get<MerchantNormalization[]>(`${API_URL}/rules/merchant`);
      setMerchantRules(response.data);
    } catch (err: any) {
      console.error('Error fetching merchant rules:', err);
    }
  };

  const fetchStatistics = async () => {
    try {
      const response = await axios.get<RulesStatistics>(`${API_URL}/rules/statistics`);
      setStatistics(response.data);
    } catch (err: any) {
      console.error('Error fetching statistics:', err);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await axios.get<{ categories: { name: string }[] }>(
        `${API_URL}/categories/summary`
      );
      const cats = response.data.categories.map((c, idx) => ({
        id: idx,
        name: c.name,
        rule_pattern: null,
        ai_suggested: false,
      }));
      setCategories(cats);
    } catch (err: any) {
      console.error('Error fetching categories:', err);
    }
  };

  // Filter rules
  const getFilteredRules = useCallback(() => {
    let rules: { type: 'category' | 'merchant'; rule: CategoryRule | MerchantNormalization }[] = [];

    if (ruleTypeFilter === 'all' || ruleTypeFilter === 'category') {
      rules = rules.concat(categoryRules.map(r => ({ type: 'category' as const, rule: r })));
    }
    if (ruleTypeFilter === 'all' || ruleTypeFilter === 'merchant') {
      rules = rules.concat(merchantRules.map(r => ({ type: 'merchant' as const, rule: r })));
    }

    // Apply category filter
    if (categoryFilter) {
      rules = rules.filter(({ type, rule }) => {
        if (type === 'category') {
          return (rule as CategoryRule).category === categoryFilter;
        } else {
          return (rule as MerchantNormalization).default_category === categoryFilter;
        }
      });
    }

    // Apply source filter
    if (sourceFilter) {
      rules = rules.filter(({ rule }) => rule.source === sourceFilter);
    }

    // Apply pattern search
    if (patternSearch) {
      const search = patternSearch.toLowerCase();
      rules = rules.filter(({ type, rule }) => {
        if (type === 'category') {
          const catRule = rule as CategoryRule;
          return (
            catRule.description_pattern.toLowerCase().includes(search) ||
            catRule.rule_name.toLowerCase().includes(search)
          );
        } else {
          const merRule = rule as MerchantNormalization;
          return (
            merRule.pattern.toLowerCase().includes(search) ||
            merRule.normalized_name.toLowerCase().includes(search)
          );
        }
      });
    }

    // Sort by priority (highest first)
    rules.sort((a, b) => b.rule.priority - a.rule.priority);

    return rules;
  }, [categoryRules, merchantRules, ruleTypeFilter, categoryFilter, sourceFilter, patternSearch]);

  // Start editing a rule
  const startEditing = (type: 'category' | 'merchant', rule: CategoryRule | MerchantNormalization) => {
    if (type === 'category') {
      const catRule = rule as CategoryRule;
      setEditing({
        mode: 'category',
        id: catRule.id,
        rule_name: catRule.rule_name,
        pattern: catRule.description_pattern,
        pattern_type: catRule.pattern_type,
        transaction_type: catRule.transaction_type,
        category: catRule.category,
        subcategory: catRule.subcategory || '',
        normalized_name: '',
        merchant_type: '',
        priority: catRule.priority,
        is_active: catRule.is_active,
      });
    } else {
      const merRule = rule as MerchantNormalization;
      setEditing({
        mode: 'merchant',
        id: merRule.id,
        rule_name: '',
        pattern: merRule.pattern,
        pattern_type: merRule.pattern_type,
        transaction_type: null,
        category: merRule.default_category || '',
        subcategory: '',
        normalized_name: merRule.normalized_name,
        merchant_type: merRule.merchant_type || '',
        priority: merRule.priority,
        is_active: true,
      });
    }
    setTestResult(null);
  };

  // Start creating a new rule
  const startCreating = (type: 'category' | 'merchant') => {
    setEditing({
      ...initialEditingState,
      mode: type,
    });
    setTestResult(null);
  };

  // Cancel editing
  const cancelEditing = () => {
    setEditing(initialEditingState);
    setTestResult(null);
  };

  // Test pattern
  const testPattern = async () => {
    if (!editing.pattern) return;

    setTesting(true);
    try {
      const response = await axios.post<RuleTestResult>(`${API_URL}/rules/category/test-pattern`, {
        pattern: editing.pattern,
        pattern_type: editing.pattern_type,
        limit: 10,
      });
      setTestResult(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to test pattern');
    } finally {
      setTesting(false);
    }
  };

  // Save rule
  const saveRule = async () => {
    if (!editing.pattern) return;

    setSaving(true);
    setError(null);

    try {
      if (editing.mode === 'category') {
        const payload = {
          rule_name: editing.rule_name || editing.pattern,
          description_pattern: editing.pattern,
          pattern_type: editing.pattern_type,
          transaction_type: editing.transaction_type,
          category: editing.category,
          subcategory: editing.subcategory || null,
          priority: editing.priority,
          is_active: editing.is_active,
        };

        if (editing.id) {
          await axios.put(`${API_URL}/rules/category/${editing.id}`, payload);
          setSuccessMessage('Category rule updated');
        } else {
          await axios.post(`${API_URL}/rules/category`, payload);
          setSuccessMessage('Category rule created');
        }
      } else {
        const payload = {
          pattern: editing.pattern,
          pattern_type: editing.pattern_type,
          normalized_name: editing.normalized_name || editing.pattern,
          merchant_type: editing.merchant_type || null,
          default_category: editing.category || null,
          priority: editing.priority,
        };

        if (editing.id) {
          await axios.put(`${API_URL}/rules/merchant/${editing.id}`, payload);
          setSuccessMessage('Merchant rule updated');
        } else {
          await axios.post(`${API_URL}/rules/merchant`, payload);
          setSuccessMessage('Merchant rule created');
        }
      }

      setTimeout(() => setSuccessMessage(null), 3000);
      cancelEditing();
      await fetchAllData();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to save rule');
    } finally {
      setSaving(false);
    }
  };

  // Delete rule
  const deleteRule = async (type: 'category' | 'merchant', id: number) => {
    if (!confirm('Are you sure you want to delete this rule?')) return;

    try {
      if (type === 'category') {
        await axios.delete(`${API_URL}/rules/category/${id}`);
      } else {
        await axios.delete(`${API_URL}/rules/merchant/${id}`);
      }
      setSuccessMessage('Rule deleted');
      setTimeout(() => setSuccessMessage(null), 3000);
      await fetchAllData();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to delete rule');
    }
  };

  // Test all rules
  const testAllRules = async () => {
    setTestingAll(true);
    setError(null);
    try {
      const response = await axios.post<TestAllRulesResult>(`${API_URL}/rules/test-all`);
      setTestAllResult(response.data);
      setShowTestAllReport(true);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to test all rules');
    } finally {
      setTestingAll(false);
    }
  };

  // Apply all rules
  const applyAllRules = async () => {
    if (!confirm('This will re-enrich all transactions using current rules. Continue?')) return;

    setApplyingAll(true);
    setError(null);
    try {
      const response = await axios.post(`${API_URL}/rules/apply-all`);
      setSuccessMessage(`Updated ${response.data.updated_count} transactions`);
      setTimeout(() => setSuccessMessage(null), 5000);
      window.dispatchEvent(new CustomEvent('transactionsUpdated'));
      await fetchStatistics();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to apply rules');
    } finally {
      setApplyingAll(false);
    }
  };

  // Get pattern type display
  const getPatternTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      contains: 'contains',
      starts_with: 'starts',
      exact: 'exact',
      regex: 'regex',
    };
    return labels[type] || type;
  };

  const filteredRules = getFilteredRules();

  return (
    <div className="space-y-6">
      {/* Header with Statistics */}
      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body">
          <h2 className="card-title text-lg">Enrichment Rules</h2>
          <p className="text-base-content/70 text-sm">
            Configure patterns to automatically categorize transactions. Rules with higher priority
            are checked first.
          </p>

          {statistics && (
            <div className="flex items-center gap-4 mt-4 flex-wrap">
              <div className="stats shadow-sm">
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Total Rules</div>
                  <div className="stat-value text-lg">
                    {statistics.category_rules_count + statistics.merchant_rules_count}
                  </div>
                </div>
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Coverage</div>
                  <div className="stat-value text-lg text-success">
                    {statistics.coverage_percentage}%
                  </div>
                </div>
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Total Matches</div>
                  <div className="stat-value text-lg">{statistics.total_usage.toLocaleString()}</div>
                </div>
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Unused</div>
                  <div className="stat-value text-lg text-warning">
                    {statistics.unused_rules_count}
                  </div>
                </div>
              </div>

              <div className="flex gap-2 ml-auto">
                <button
                  className="btn btn-outline btn-sm"
                  onClick={testAllRules}
                  disabled={testingAll}
                >
                  {testingAll ? (
                    <>
                      <span className="loading loading-spinner loading-xs"></span>
                      Testing...
                    </>
                  ) : (
                    'Test All Rules'
                  )}
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={applyAllRules}
                  disabled={applyingAll}
                >
                  {applyingAll ? (
                    <>
                      <span className="loading loading-spinner loading-xs"></span>
                      Applying...
                    </>
                  ) : (
                    'Apply All Rules'
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error/Success alerts */}
      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
          <button className="btn btn-ghost btn-xs" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="alert alert-success">
          <span>{successMessage}</span>
        </div>
      )}

      {/* Filters and Rules List */}
      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body p-0">
          <div className="flex flex-col lg:flex-row">
            {/* Filters sidebar */}
            <div className="lg:w-64 p-4 border-b lg:border-b-0 lg:border-r border-base-300 space-y-4">
              <h3 className="font-semibold text-sm">Filters</h3>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Rule Type</span>
                </label>
                <select
                  className="select select-bordered select-sm w-full"
                  value={ruleTypeFilter}
                  onChange={(e) => setRuleTypeFilter(e.target.value as RuleType)}
                >
                  <option value="all">All Rules</option>
                  <option value="category">Category Rules</option>
                  <option value="merchant">Merchant Rules</option>
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Category</span>
                </label>
                <select
                  className="select select-bordered select-sm w-full"
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                >
                  <option value="">All Categories</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.name}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Source</span>
                </label>
                <select
                  className="select select-bordered select-sm w-full"
                  value={sourceFilter}
                  onChange={(e) => setSourceFilter(e.target.value)}
                >
                  <option value="">All Sources</option>
                  <option value="manual">Manual</option>
                  <option value="learned">Learned</option>
                  <option value="llm">LLM</option>
                  <option value="direct_debit">Direct Debit</option>
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Search Pattern</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered input-sm w-full"
                  placeholder="Search..."
                  value={patternSearch}
                  onChange={(e) => setPatternSearch(e.target.value)}
                />
              </div>

              <div className="divider my-2"></div>

              <div className="space-y-2">
                <button
                  className="btn btn-outline btn-sm w-full"
                  onClick={() => startCreating('category')}
                >
                  + New Category Rule
                </button>
                <button
                  className="btn btn-outline btn-sm w-full"
                  onClick={() => startCreating('merchant')}
                >
                  + New Merchant Rule
                </button>
              </div>
            </div>

            {/* Rules list */}
            <div className="flex-1 p-4">
              {loading ? (
                <div className="flex items-center justify-center p-8">
                  <span className="loading loading-spinner loading-lg"></span>
                </div>
              ) : filteredRules.length === 0 ? (
                <div className="text-center p-8 text-base-content/60">
                  <p>No rules found matching your filters.</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {filteredRules.map(({ type, rule }) => {
                    const isCategory = type === 'category';
                    const catRule = rule as CategoryRule;
                    const merRule = rule as MerchantNormalization;

                    return (
                      <div
                        key={`${type}-${rule.id}`}
                        className={`card bg-base-200 shadow-sm ${
                          !isCategory || catRule.is_active ? '' : 'opacity-50'
                        }`}
                      >
                        <div className="card-body p-3">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span
                                  className={`badge badge-sm ${
                                    isCategory ? 'badge-primary' : 'badge-secondary'
                                  }`}
                                >
                                  {isCategory ? 'Category' : 'Merchant'}
                                </span>
                                <span className="font-semibold text-sm truncate">
                                  {isCategory ? catRule.rule_name : merRule.normalized_name}
                                </span>
                                {!isCategory || !catRule.is_active ? null : null}
                              </div>

                              <div className="mt-1 text-xs text-base-content/70 font-mono">
                                <span className="badge badge-ghost badge-xs mr-1">
                                  {getPatternTypeLabel(rule.pattern_type)}
                                </span>
                                {isCategory ? catRule.description_pattern : merRule.pattern}
                              </div>

                              <div className="mt-1 flex items-center gap-3 text-xs text-base-content/60">
                                <span>
                                  {isCategory ? (
                                    <>
                                      {catRule.category}
                                      {catRule.subcategory && ` / ${catRule.subcategory}`}
                                    </>
                                  ) : (
                                    <>
                                      {merRule.default_category || 'No category'}
                                      {merRule.merchant_type && ` (${merRule.merchant_type})`}
                                    </>
                                  )}
                                </span>
                                <span className="text-base-content/40">|</span>
                                <span>pri: {rule.priority}</span>
                                <span className="text-base-content/40">|</span>
                                <span>used: {rule.usage_count}</span>
                              </div>
                            </div>

                            <div className="flex gap-1">
                              <button
                                className="btn btn-ghost btn-xs"
                                onClick={() => startEditing(type, rule)}
                              >
                                Edit
                              </button>
                              <button
                                className="btn btn-ghost btn-xs text-error"
                                onClick={() => deleteRule(type, rule.id)}
                              >
                                x
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Rule Editor Panel */}
      {editing.mode !== 'none' && (
        <div className="card bg-base-100 border border-base-300 shadow-sm">
          <div className="card-body">
            <h3 className="card-title text-base">
              {editing.id ? 'Edit' : 'New'}{' '}
              {editing.mode === 'category' ? 'Category Rule' : 'Merchant Rule'}
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              {/* Rule Name (category only) */}
              {editing.mode === 'category' && (
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-sm">Rule Name</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm"
                    value={editing.rule_name}
                    onChange={(e) => setEditing((s) => ({ ...s, rule_name: e.target.value }))}
                    placeholder="e.g., Grocery Stores"
                  />
                </div>
              )}

              {/* Pattern */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text text-sm">Pattern</span>
                  <span
                    className="label-text-alt text-xs cursor-help"
                    title="Use starts:, contains:, exact:, or regex: prefix"
                  >
                    ?
                  </span>
                </label>
                <input
                  type="text"
                  className="input input-bordered input-sm"
                  value={editing.pattern}
                  onChange={(e) => setEditing((s) => ({ ...s, pattern: e.target.value }))}
                  placeholder="e.g., TESCO or starts:AMAZON"
                />
              </div>

              {/* Pattern Type */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text text-sm">Match Type</span>
                </label>
                <select
                  className="select select-bordered select-sm"
                  value={editing.pattern_type}
                  onChange={(e) =>
                    setEditing((s) => ({
                      ...s,
                      pattern_type: e.target.value as EditingState['pattern_type'],
                    }))
                  }
                >
                  <option value="contains">Contains</option>
                  <option value="starts_with">Starts With</option>
                  <option value="exact">Exact Match</option>
                  <option value="regex">Regex</option>
                </select>
              </div>

              {/* Category */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text text-sm">Category</span>
                </label>
                <select
                  className="select select-bordered select-sm"
                  value={editing.category}
                  onChange={(e) => setEditing((s) => ({ ...s, category: e.target.value }))}
                >
                  <option value="">Select category...</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.name}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Subcategory (category rules) */}
              {editing.mode === 'category' && (
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-sm">Subcategory</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm"
                    value={editing.subcategory}
                    onChange={(e) => setEditing((s) => ({ ...s, subcategory: e.target.value }))}
                    placeholder="Optional"
                  />
                </div>
              )}

              {/* Normalized Name (merchant rules) */}
              {editing.mode === 'merchant' && (
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-sm">Merchant Name</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm"
                    value={editing.normalized_name}
                    onChange={(e) => setEditing((s) => ({ ...s, normalized_name: e.target.value }))}
                    placeholder="Clean merchant name"
                  />
                </div>
              )}

              {/* Merchant Type (merchant rules) */}
              {editing.mode === 'merchant' && (
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-sm">Merchant Type</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-sm"
                    value={editing.merchant_type}
                    onChange={(e) => setEditing((s) => ({ ...s, merchant_type: e.target.value }))}
                    placeholder="e.g., supermarket, coffee_shop"
                  />
                </div>
              )}

              {/* Transaction Type (category rules) */}
              {editing.mode === 'category' && (
                <div className="form-control">
                  <label className="label">
                    <span className="label-text text-sm">Transaction Type</span>
                  </label>
                  <select
                    className="select select-bordered select-sm"
                    value={editing.transaction_type || ''}
                    onChange={(e) =>
                      setEditing((s) => ({
                        ...s,
                        transaction_type: (e.target.value || null) as EditingState['transaction_type'],
                      }))
                    }
                  >
                    <option value="">All</option>
                    <option value="CREDIT">Credit only</option>
                    <option value="DEBIT">Debit only</option>
                  </select>
                </div>
              )}

              {/* Priority */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text text-sm">Priority (0-100)</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered input-sm"
                  min={0}
                  max={100}
                  value={editing.priority}
                  onChange={(e) =>
                    setEditing((s) => ({ ...s, priority: parseInt(e.target.value) || 0 }))
                  }
                />
              </div>
            </div>

            {/* Test Preview */}
            {testResult && (
              <div className="mt-4 p-3 bg-base-200 rounded-lg">
                <div className="font-semibold text-sm mb-2">
                  Test Preview: {testResult.match_count} transactions would match
                </div>
                {testResult.sample_transactions.length > 0 ? (
                  <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
                    {testResult.sample_transactions.map((txn) => (
                      <li key={txn.id} className="font-mono truncate">
                        {txn.description} - {txn.amount < 0 ? '-' : ''}£
                        {Math.abs(txn.amount).toFixed(2)} - {txn.date}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-base-content/60">No transactions match this pattern.</p>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 mt-4">
              <button
                className="btn btn-outline btn-sm"
                onClick={testPattern}
                disabled={testing || !editing.pattern}
              >
                {testing ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Testing...
                  </>
                ) : (
                  'Test Pattern'
                )}
              </button>
              <button
                className="btn btn-success btn-sm"
                onClick={saveRule}
                disabled={saving || !editing.pattern || !editing.category}
              >
                {saving ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Saving...
                  </>
                ) : (
                  'Save Rule'
                )}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={cancelEditing}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Test All Rules Report */}
      {showTestAllReport && testAllResult && (
        <div className="card bg-base-100 border border-base-300 shadow-sm">
          <div className="card-body">
            <div className="flex items-center justify-between">
              <h3 className="card-title text-base">Rule Coverage Report</h3>
              <button
                className="btn btn-ghost btn-xs"
                onClick={() => setShowTestAllReport(false)}
              >
                Close
              </button>
            </div>

            <div className="mt-4">
              <div className="text-lg font-semibold">
                Overall Coverage: {testAllResult.coverage_percentage}%
                <span className="text-sm font-normal text-base-content/60 ml-2">
                  ({testAllResult.covered_transactions.toLocaleString()} of{' '}
                  {testAllResult.total_transactions.toLocaleString()} transactions)
                </span>
              </div>

              {/* Category breakdown */}
              <div className="mt-4">
                <div className="text-sm font-semibold mb-2">Coverage by Category:</div>
                <div className="space-y-1">
                  {Object.entries(testAllResult.category_coverage)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 10)
                    .map(([cat, count]) => (
                      <div key={cat} className="flex items-center gap-2">
                        <span className="text-xs w-32 truncate">{cat}</span>
                        <progress
                          className="progress progress-success w-40"
                          value={count}
                          max={testAllResult.total_transactions}
                        ></progress>
                        <span className="text-xs text-base-content/60">{count} txns</span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Unused rules */}
              {(testAllResult.unused_category_rules.length > 0 ||
                testAllResult.unused_merchant_rules.length > 0) && (
                <div className="mt-4">
                  <div className="text-sm font-semibold mb-2 text-warning">Unused Rules:</div>
                  <ul className="text-xs space-y-1">
                    {testAllResult.unused_category_rules.map((r) => (
                      <li key={`cat-${r.id}`}>
                        <span className="badge badge-primary badge-xs mr-1">cat</span>
                        {r.name} - {r.pattern}
                      </li>
                    ))}
                    {testAllResult.unused_merchant_rules.map((r) => (
                      <li key={`mer-${r.id}`}>
                        <span className="badge badge-secondary badge-xs mr-1">mer</span>
                        {r.name} - {r.pattern}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Conflicts */}
              {testAllResult.potential_conflicts_count > 0 && (
                <div className="mt-4">
                  <div className="text-sm font-semibold mb-2">
                    Potential Conflicts: {testAllResult.potential_conflicts_count} transactions
                    match multiple rules
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
