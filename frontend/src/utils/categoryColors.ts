// Base category color mappings for common categories
const BASE_CATEGORY_COLORS: Record<string, string> = {
  Groceries: 'badge-success',
  Transport: 'badge-info',
  Transportation: 'badge-info',
  Dining: 'badge-warning',
  Entertainment: 'badge-secondary',
  Utilities: 'badge-accent',
  Shopping: 'badge-primary',
  Health: 'badge-error',
  Income: 'badge-success',
  Electronics: 'badge-primary',
  Travel: 'badge-secondary',
  Other: 'badge-warning',
};

// Color palette for dynamically assigned categories
const COLOR_PALETTE = [
  'badge-primary',
  'badge-secondary',
  'badge-accent',
  'badge-info',
  'badge-success',
  'badge-warning',
  'badge-error',
];

// In-memory cache of category colors
let categoryColorCache: Record<string, string> = { ...BASE_CATEGORY_COLORS };
let isColorMapLoaded = false;

/**
 * Load category-color mappings from localStorage
 */
function loadCategoryColorMap(): void {
  if (isColorMapLoaded) return;

  try {
    const saved = localStorage.getItem('categoryColorMap');
    if (saved) {
      const savedMap = JSON.parse(saved);
      categoryColorCache = { ...BASE_CATEGORY_COLORS, ...savedMap };
    }
  } catch (e) {
    console.error('Failed to load category color map from localStorage:', e);
  }
  isColorMapLoaded = true;
}

/**
 * Save category-color mappings to localStorage
 */
function saveCategoryColorMap(): void {
  try {
    // Only save the non-base colors to avoid storing redundant data
    const customColors: Record<string, string> = {};
    Object.entries(categoryColorCache).forEach(([category, color]) => {
      if (BASE_CATEGORY_COLORS[category] !== color) {
        customColors[category] = color;
      }
    });
    localStorage.setItem('categoryColorMap', JSON.stringify(customColors));
  } catch (e) {
    console.error('Failed to save category color map to localStorage:', e);
  }
}

/**
 * Get or assign a persistent color for a category
 */
export function getCategoryColor(category: string): string {
  loadCategoryColorMap();

  // If already in cache, return it
  if (categoryColorCache[category]) {
    return categoryColorCache[category];
  }

  // Assign a new color from the palette
  const usedColors = new Set(Object.values(categoryColorCache));
  let colorToAssign = 'badge-ghost'; // fallback

  // Find the first color in palette that's not heavily used
  for (const color of COLOR_PALETTE) {
    if (!usedColors.has(color)) {
      colorToAssign = color;
      break;
    }
  }

  // If all palette colors are used, cycle through them
  if (colorToAssign === 'badge-ghost') {
    const categoriesCount = Object.keys(categoryColorCache).length;
    colorToAssign = COLOR_PALETTE[categoriesCount % COLOR_PALETTE.length];
  }

  // Cache and persist the assignment
  categoryColorCache[category] = colorToAssign;
  saveCategoryColorMap();

  return colorToAssign;
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
