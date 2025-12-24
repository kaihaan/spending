export type MonthKey = 'current' | 'month-1' | 'month-2' | 'month-3' | 'average';

interface MonthButton {
  key: MonthKey;
  label: string;
}

interface MonthSelectorProps {
  selectedMonth: MonthKey | null;
  onMonthSelect: (month: MonthKey) => void;
}

/**
 * Generate month buttons for the last 3 months, current month, and average
 * Handles year boundaries correctly (e.g., in January shows Oct, Nov, Dec of previous year)
 */
const getMonthButtons = (): MonthButton[] => {
  const now = new Date();
  const buttons: MonthButton[] = [];

  // Generate month-3 through current (oldest to newest)
  for (let i = 3; i >= 0; i--) {
    const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const label = date.toLocaleDateString('en-GB', { month: 'short' });
    const key: MonthKey = i === 0 ? 'current' : `month-${i}` as MonthKey;
    buttons.push({ key, label });
  }

  // Add average button
  buttons.push({ key: 'average', label: 'Avg' });

  return buttons;
};

export default function MonthSelector({ selectedMonth, onMonthSelect }: MonthSelectorProps) {
  const monthButtons = getMonthButtons();

  return (
    <div className="flex gap-1">
      {monthButtons.map(({ key, label }) => (
        <button
          key={key}
          className={`btn btn-sm ${selectedMonth === key ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => onMonthSelect(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
