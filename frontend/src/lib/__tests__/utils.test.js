/**
 * Utils Library Tests
 * Tests for utility functions in lib/utils.js
 */
import { describe, it, expect } from 'vitest'
import { cn, extractCN, formatDate, formatDateTime, extractData } from '../utils'

describe('cn (className merger)', () => {
  it('merges multiple class names', () => {
    const result = cn('text-sm', 'font-bold')
    expect(result).toContain('text-sm')
    expect(result).toContain('font-bold')
  })

  it('handles conditional classes', () => {
    const result = cn('base', true && 'active', false && 'hidden')
    expect(result).toContain('base')
    expect(result).toContain('active')
    expect(result).not.toContain('hidden')
  })

  it('merges Tailwind classes correctly', () => {
    const result = cn('px-2', 'px-4')
    expect(result).toBe('px-4') // tailwind-merge should keep last
  })

  it('handles empty input', () => {
    const result = cn()
    expect(result).toBe('')
  })
})

describe('extractCN', () => {
  it('extracts CN from DN string', () => {
    const result = extractCN('CN=example.com, O=My Org, C=US')
    expect(result).toBe('example.com')
  })

  it('extracts CN from DN without spaces', () => {
    const result = extractCN('CN=test.local,O=Test,C=FR')
    expect(result).toBe('test.local')
  })

  it('returns Unknown for null/undefined', () => {
    expect(extractCN(null)).toBe('Unknown')
    expect(extractCN(undefined)).toBe('Unknown')
    expect(extractCN('')).toBe('Unknown')
  })

  it('falls back to first component value', () => {
    const result = extractCN('O=Organization, C=US')
    expect(result).toBe('Organization')
  })

  it('truncates long string without =', () => {
    const longString = 'this is a very long string without equals sign'
    const result = extractCN(longString)
    expect(result.length).toBeLessThanOrEqual(30)
  })
})

describe('formatDate', () => {
  it('formats valid date string', () => {
    const result = formatDate('2026-01-29T10:00:00Z')
    expect(result).toMatch(/Jan/)
    expect(result).toMatch(/29/)
    expect(result).toMatch(/2026/)
  })

  it('formats Date object', () => {
    const result = formatDate(new Date('2026-06-15'))
    expect(result).toMatch(/Jun/)
    expect(result).toMatch(/15/)
  })

  it('returns N/A for null/undefined', () => {
    expect(formatDate(null)).toBe('N/A')
    expect(formatDate(undefined)).toBe('N/A')
  })

  it('returns custom fallback', () => {
    expect(formatDate(null, '-')).toBe('-')
    expect(formatDate('', 'Unknown')).toBe('Unknown')
  })

  it('returns fallback for invalid date', () => {
    expect(formatDate('not-a-date')).toBe('N/A')
    expect(formatDate('invalid')).toBe('N/A')
  })
})

describe('formatDateTime', () => {
  it('formats valid datetime', () => {
    const result = formatDateTime('2026-01-29T10:30:00Z')
    expect(result).not.toBe('N/A')
    expect(result.length).toBeGreaterThan(5)
  })

  it('returns N/A for null/undefined', () => {
    expect(formatDateTime(null)).toBe('N/A')
    expect(formatDateTime(undefined)).toBe('N/A')
  })

  it('returns fallback for invalid datetime', () => {
    expect(formatDateTime('invalid-date')).toBe('N/A')
  })

  it('returns custom fallback', () => {
    expect(formatDateTime(null, 'Never')).toBe('Never')
  })
})

describe('extractData', () => {
  it('extracts data from response object', () => {
    const response = { data: [1, 2, 3], message: 'ok' }
    expect(extractData(response)).toEqual([1, 2, 3])
  })

  it('returns response if no data field', () => {
    const response = { items: [1, 2, 3] }
    expect(extractData(response)).toEqual({ items: [1, 2, 3] })
  })

  it('returns null for null/undefined', () => {
    expect(extractData(null)).toBeNull()
    expect(extractData(undefined)).toBeNull()
  })

  it('handles nested data', () => {
    const response = { data: { users: [], count: 0 } }
    expect(extractData(response)).toEqual({ users: [], count: 0 })
  })

  it('handles data: null', () => {
    const response = { data: null }
    expect(extractData(response)).toBeNull()
  })
})
