// Category color mappings for consistent UI
export const CATEGORY_COLORS: Record<string, string> = {
  Groceries: 'badge-success',
  Transport: 'badge-info',
  Dining: 'badge-warning',
  Entertainment: 'badge-secondary',
  Utilities: 'badge-accent',
  Shopping: 'badge-primary',
  Health: 'badge-error',
  Income: 'badge-success',
  Other: 'badge-ghost',
};

export function getCategoryColor(category: string): string {
  return CATEGORY_COLORS[category] || 'badge-ghost';
}

export const ALL_CATEGORIES = [
  'Groceries',
  'Transport',
  'Dining',
  'Entertainment',
  'Utilities',
  'Shopping',
  'Health',
  'Income',
  'Other',
];
