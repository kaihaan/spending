/**
 * Filter Utilities Tests
 *
 * Tests for transaction filtering logic - category, date, search,
 * direction (inbound/outbound), and Huququllah classification filters.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Transaction } from '../types'
import {
  applyFilters,
  getFilteredTransactions,
  getUniqueCategories,
  getSubcategoriesForCategory,
  loadFilters,
  saveFilters,
  DEFAULT_FILTERS,
  type TransactionFilters,
} from './filterUtils'

// Helper to create a test transaction with defaults
function createTransaction(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 1,
    date: '2024-06-15',
    description: 'Test Transaction',
    amount: -50.0,
    category: 'Shopping',
    merchant: 'Test Store',
    huququllah_classification: null,
    transaction_type: 'DEBIT',
    created_at: '2024-06-15T10:00:00Z',
    provider: null,
    ...overrides,
  }
}

// Default filters for testing (show all)
const noFilters: TransactionFilters = {
  ...DEFAULT_FILTERS,
}

describe('applyFilters', () => {
  describe('category filtering', () => {
    it('returns true when category is "All"', () => {
      const txn = createTransaction({ category: 'Groceries' })
      const filters = { ...noFilters, selectedCategory: 'All' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns true when transaction matches selected category', () => {
      const txn = createTransaction({ category: 'Groceries' })
      const filters = { ...noFilters, selectedCategory: 'Groceries' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns false when transaction does not match selected category', () => {
      const txn = createTransaction({ category: 'Shopping' })
      const filters = { ...noFilters, selectedCategory: 'Groceries' }

      expect(applyFilters(txn, filters)).toBe(false)
    })
  })

  describe('subcategory filtering', () => {
    it('ignores subcategory filter when empty', () => {
      const txn = createTransaction({ category: 'Groceries', subcategory: 'Supermarket' })
      const filters = { ...noFilters, selectedCategory: 'Groceries', selectedSubcategory: '' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns true when subcategory matches', () => {
      const txn = createTransaction({ category: 'Groceries', subcategory: 'Supermarket' })
      const filters = {
        ...noFilters,
        selectedCategory: 'Groceries',
        selectedSubcategory: 'Supermarket',
      }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns false when subcategory does not match', () => {
      const txn = createTransaction({ category: 'Groceries', subcategory: 'Supermarket' })
      const filters = {
        ...noFilters,
        selectedCategory: 'Groceries',
        selectedSubcategory: 'Convenience Store',
      }

      expect(applyFilters(txn, filters)).toBe(false)
    })
  })

  describe('date filtering', () => {
    it('returns true when no date filters are set', () => {
      const txn = createTransaction({ date: '2024-06-15' })
      const filters = { ...noFilters }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns true when date is within range', () => {
      const txn = createTransaction({ date: '2024-06-15' })
      const filters = { ...noFilters, dateFrom: '2024-06-01', dateTo: '2024-06-30' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns false when date is before dateFrom', () => {
      const txn = createTransaction({ date: '2024-05-15' })
      const filters = { ...noFilters, dateFrom: '2024-06-01' }

      expect(applyFilters(txn, filters)).toBe(false)
    })

    it('returns false when date is after dateTo', () => {
      const txn = createTransaction({ date: '2024-07-15' })
      const filters = { ...noFilters, dateTo: '2024-06-30' }

      expect(applyFilters(txn, filters)).toBe(false)
    })

    it('includes transactions on boundary dates', () => {
      const txn = createTransaction({ date: '2024-06-01' })
      const filters = { ...noFilters, dateFrom: '2024-06-01', dateTo: '2024-06-30' }

      expect(applyFilters(txn, filters)).toBe(true)
    })
  })

  describe('keyword search', () => {
    it('matches description (case insensitive)', () => {
      const txn = createTransaction({ description: 'AMAZON MARKETPLACE' })
      const filters = { ...noFilters, searchKeyword: 'amazon' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('matches merchant name', () => {
      const txn = createTransaction({ merchant: 'Tesco Express' })
      const filters = { ...noFilters, searchKeyword: 'tesco' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('matches amount', () => {
      const txn = createTransaction({ amount: -123.45 })
      const filters = { ...noFilters, searchKeyword: '123.45' }

      expect(applyFilters(txn, filters)).toBe(true)
    })

    it('returns false when keyword not found', () => {
      const txn = createTransaction({
        description: 'TESCO STORES',
        merchant: 'Tesco',
        amount: -50.0,
      })
      const filters = { ...noFilters, searchKeyword: 'amazon' }

      expect(applyFilters(txn, filters)).toBe(false)
    })
  })

  describe('direction filtering (inbound/outbound)', () => {
    it('shows all when both inbound and outbound are true', () => {
      const debit = createTransaction({ transaction_type: 'DEBIT' })
      const credit = createTransaction({ transaction_type: 'CREDIT' })
      const filters = { ...noFilters, showInbound: true, showOutbound: true }

      expect(applyFilters(debit, filters)).toBe(true)
      expect(applyFilters(credit, filters)).toBe(true)
    })

    it('shows all when both inbound and outbound are false', () => {
      const debit = createTransaction({ transaction_type: 'DEBIT' })
      const credit = createTransaction({ transaction_type: 'CREDIT' })
      const filters = { ...noFilters, showInbound: false, showOutbound: false }

      expect(applyFilters(debit, filters)).toBe(true)
      expect(applyFilters(credit, filters)).toBe(true)
    })

    it('shows only CREDIT when inbound=true and outbound=false', () => {
      const debit = createTransaction({ transaction_type: 'DEBIT' })
      const credit = createTransaction({ transaction_type: 'CREDIT' })
      const filters = { ...noFilters, showInbound: true, showOutbound: false }

      expect(applyFilters(debit, filters)).toBe(false)
      expect(applyFilters(credit, filters)).toBe(true)
    })

    it('shows only DEBIT when inbound=false and outbound=true', () => {
      const debit = createTransaction({ transaction_type: 'DEBIT' })
      const credit = createTransaction({ transaction_type: 'CREDIT' })
      const filters = { ...noFilters, showInbound: false, showOutbound: true }

      expect(applyFilters(debit, filters)).toBe(true)
      expect(applyFilters(credit, filters)).toBe(false)
    })
  })

  describe('Huququllah classification filtering', () => {
    it('shows all when both essential and discretionary are false', () => {
      const essential = createTransaction({ huququllah_classification: 'essential' })
      const discretionary = createTransaction({ huququllah_classification: 'discretionary' })
      const unclassified = createTransaction({ huququllah_classification: null })
      const filters = { ...noFilters, showEssential: false, showDiscretionary: false }

      expect(applyFilters(essential, filters)).toBe(true)
      expect(applyFilters(discretionary, filters)).toBe(true)
      expect(applyFilters(unclassified, filters)).toBe(true)
    })

    it('shows only essential when essential=true and discretionary=false', () => {
      const essential = createTransaction({ huququllah_classification: 'essential' })
      const discretionary = createTransaction({ huququllah_classification: 'discretionary' })
      const filters = { ...noFilters, showEssential: true, showDiscretionary: false }

      expect(applyFilters(essential, filters)).toBe(true)
      expect(applyFilters(discretionary, filters)).toBe(false)
    })

    it('shows only discretionary when essential=false and discretionary=true', () => {
      const essential = createTransaction({ huququllah_classification: 'essential' })
      const discretionary = createTransaction({ huququllah_classification: 'discretionary' })
      const filters = { ...noFilters, showEssential: false, showDiscretionary: true }

      expect(applyFilters(essential, filters)).toBe(false)
      expect(applyFilters(discretionary, filters)).toBe(true)
    })
  })
})

describe('getFilteredTransactions', () => {
  it('returns all transactions when no filters applied', () => {
    const transactions = [
      createTransaction({ id: 1, category: 'Shopping' }),
      createTransaction({ id: 2, category: 'Groceries' }),
      createTransaction({ id: 3, category: 'Transport' }),
    ]

    const result = getFilteredTransactions(transactions, noFilters)

    expect(result).toHaveLength(3)
  })

  it('filters transactions correctly', () => {
    const transactions = [
      createTransaction({ id: 1, category: 'Shopping' }),
      createTransaction({ id: 2, category: 'Groceries' }),
      createTransaction({ id: 3, category: 'Shopping' }),
    ]
    const filters = { ...noFilters, selectedCategory: 'Shopping' }

    const result = getFilteredTransactions(transactions, filters)

    expect(result).toHaveLength(2)
    expect(result.every((t) => t.category === 'Shopping')).toBe(true)
  })

  it('returns empty array when no transactions match', () => {
    const transactions = [
      createTransaction({ id: 1, category: 'Shopping' }),
      createTransaction({ id: 2, category: 'Groceries' }),
    ]
    const filters = { ...noFilters, selectedCategory: 'Transport' }

    const result = getFilteredTransactions(transactions, filters)

    expect(result).toHaveLength(0)
  })
})

describe('getUniqueCategories', () => {
  it('returns sorted unique categories', () => {
    const transactions = [
      createTransaction({ category: 'Transport' }),
      createTransaction({ category: 'Groceries' }),
      createTransaction({ category: 'Transport' }), // duplicate
      createTransaction({ category: 'Bills' }),
    ]

    const result = getUniqueCategories(transactions)

    expect(result).toEqual(['Bills', 'Groceries', 'Transport'])
  })

  it('returns empty array for empty transactions', () => {
    const result = getUniqueCategories([])

    expect(result).toEqual([])
  })

  it('excludes transactions without category', () => {
    const transactions = [
      createTransaction({ category: 'Shopping' }),
      createTransaction({ category: '' }),
    ]

    const result = getUniqueCategories(transactions)

    expect(result).toEqual(['Shopping'])
  })
})

describe('getSubcategoriesForCategory', () => {
  it('returns subcategories for specified category only', () => {
    const transactions = [
      createTransaction({ category: 'Groceries', subcategory: 'Supermarket' }),
      createTransaction({ category: 'Groceries', subcategory: 'Convenience Store' }),
      createTransaction({ category: 'Shopping', subcategory: 'Clothing' }),
    ]

    const result = getSubcategoriesForCategory(transactions, 'Groceries')

    expect(result).toEqual(['Convenience Store', 'Supermarket'])
  })

  it('returns empty array when no subcategories exist', () => {
    const transactions = [createTransaction({ category: 'Groceries', subcategory: undefined })]

    const result = getSubcategoriesForCategory(transactions, 'Groceries')

    expect(result).toEqual([])
  })
})

describe('localStorage operations', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  describe('loadFilters', () => {
    it('returns saved filters from localStorage', () => {
      const savedFilters: TransactionFilters = {
        ...DEFAULT_FILTERS,
        selectedCategory: 'Groceries',
      }
      vi.mocked(localStorage.getItem).mockReturnValue(JSON.stringify(savedFilters))

      const result = loadFilters()

      expect(result).toEqual(savedFilters)
    })

    it('returns defaults when nothing saved', () => {
      vi.mocked(localStorage.getItem).mockReturnValue(null)

      const result = loadFilters()

      expect(result).toEqual(DEFAULT_FILTERS)
    })

    it('returns defaults on parse error', () => {
      vi.mocked(localStorage.getItem).mockReturnValue('invalid json')

      const result = loadFilters()

      expect(result).toEqual(DEFAULT_FILTERS)
    })
  })

  describe('saveFilters', () => {
    it('saves filters to localStorage', () => {
      const filters: TransactionFilters = {
        ...DEFAULT_FILTERS,
        selectedCategory: 'Shopping',
      }

      saveFilters(filters)

      expect(localStorage.setItem).toHaveBeenCalledWith(
        'transactionFilters',
        JSON.stringify(filters)
      )
    })
  })
})
