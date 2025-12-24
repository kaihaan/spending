import React from 'react';

interface GmailDateRangeSelectorProps {
  fromDate: string;
  toDate: string;
  onFromDateChange: (date: string) => void;
  onToDateChange: (date: string) => void;
  disabled?: boolean;
}

/**
 * Date range selector for Gmail receipt sync.
 * Defaults to last 12 months.
 */
export const GmailDateRangeSelector: React.FC<GmailDateRangeSelectorProps> = ({
  fromDate,
  toDate,
  onFromDateChange,
  onToDateChange,
  disabled = false,
}) => {
  // Quick presets
  const setPreset = (months: number) => {
    const today = new Date();
    const from = new Date();
    from.setMonth(from.getMonth() - months);

    onToDateChange(today.toISOString().split('T')[0]);
    onFromDateChange(from.toISOString().split('T')[0]);
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-base-content/70">From</label>
        <input
          type="date"
          value={fromDate}
          onChange={(e) => onFromDateChange(e.target.value)}
          disabled={disabled}
          className="input input-sm input-bordered w-36"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-base-content/70">To</label>
        <input
          type="date"
          value={toDate}
          onChange={(e) => onToDateChange(e.target.value)}
          disabled={disabled}
          className="input input-sm input-bordered w-36"
        />
      </div>

      <div className="flex gap-1">
        <button
          type="button"
          className="btn btn-xs btn-ghost"
          onClick={() => setPreset(3)}
          disabled={disabled}
        >
          3mo
        </button>
        <button
          type="button"
          className="btn btn-xs btn-ghost"
          onClick={() => setPreset(6)}
          disabled={disabled}
        >
          6mo
        </button>
        <button
          type="button"
          className="btn btn-xs btn-ghost"
          onClick={() => setPreset(12)}
          disabled={disabled}
        >
          1yr
        </button>
        <button
          type="button"
          className="btn btn-xs btn-ghost"
          onClick={() => setPreset(24)}
          disabled={disabled}
        >
          2yr
        </button>
      </div>
    </div>
  );
};

/**
 * Returns default date range (last 12 months).
 */
export const getDefaultDateRange = (): { fromDate: string; toDate: string } => {
  const today = new Date();
  const from = new Date();
  from.setMonth(from.getMonth() - 12);

  return {
    fromDate: from.toISOString().split('T')[0],
    toDate: today.toISOString().split('T')[0],
  };
};
