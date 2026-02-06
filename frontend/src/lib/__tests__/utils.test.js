import { describe, it, expect, vi, beforeEach } from 'vitest'
import { 
  cn, 
  safeJsonParse, 
  extractCN, 
  extractData, 
  formatDate,
  exportToCSV,
  exportToJSON
} from '../utils'

describe('utils', () => {
  describe('cn', () => {
    it('merges class names', () => {
      expect(cn('foo', 'bar')).toBe('foo bar')
    })

    it('handles conditional classes', () => {
      expect(cn('foo', false && 'bar', 'baz')).toBe('foo baz')
    })

    it('merges tailwind classes correctly', () => {
      expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4')
    })

    it('handles undefined and null', () => {
      expect(cn('foo', undefined, null, 'bar')).toBe('foo bar')
    })
  })

  describe('safeJsonParse', () => {
    it('parses valid JSON', () => {
      expect(safeJsonParse('{"a":1}')).toEqual({ a: 1 })
    })

    it('returns fallback for invalid JSON', () => {
      expect(safeJsonParse('invalid')).toEqual([])
    })

    it('returns fallback for null', () => {
      expect(safeJsonParse(null)).toEqual([])
    })

    it('returns fallback for empty string', () => {
      expect(safeJsonParse('')).toEqual([])
    })

    it('uses custom fallback', () => {
      expect(safeJsonParse('invalid', {})).toEqual({})
    })

    it('parses arrays', () => {
      expect(safeJsonParse('[1,2,3]')).toEqual([1, 2, 3])
    })
  })

  describe('extractCN', () => {
    it('extracts CN from subject', () => {
      expect(extractCN('CN=example.com,O=Org')).toBe('example.com')
    })

    it('handles CN only', () => {
      expect(extractCN('CN=test')).toBe('test')
    })

    it('returns full string if no CN', () => {
      expect(extractCN('O=Org,C=US')).toBe('O=Org,C=US')
    })

    it('handles empty string', () => {
      expect(extractCN('')).toBe('')
    })

    it('handles null', () => {
      expect(extractCN(null)).toBe('')
    })

    it('handles undefined', () => {
      expect(extractCN(undefined)).toBe('')
    })
  })

  describe('extractData', () => {
    it('extracts .data field by default', () => {
      expect(extractData({ data: [1, 2, 3] })).toEqual([1, 2, 3])
    })

    it('extracts specific key when provided', () => {
      expect(extractData({ items: [1, 2], count: 2 }, 'items')).toEqual([1, 2])
    })

    it('returns fallback for null', () => {
      expect(extractData(null, undefined, [])).toEqual([])
    })

    it('returns object itself if no .data field', () => {
      expect(extractData({ foo: 'bar' })).toEqual({ foo: 'bar' })
    })

    it('returns custom fallback', () => {
      expect(extractData(null, 'key', 'default')).toBe('default')
    })
  })

  describe('formatDate', () => {
    it('formats valid date', () => {
      const result = formatDate('2026-02-06T12:00:00Z')
      // Locale-agnostic: just check it contains 2026 and 6
      expect(result).toContain('2026')
      expect(result).toMatch(/6/)
    })

    it('returns dash for null', () => {
      expect(formatDate(null)).toBe('-')
    })

    it('returns dash for undefined', () => {
      expect(formatDate(undefined)).toBe('-')
    })

    it('returns dash for empty string', () => {
      expect(formatDate('')).toBe('-')
    })

    it('handles invalid date string', () => {
      // Invalid dates may return 'Invalid Date' or '-' depending on browser
      const result = formatDate('not-a-date')
      expect(['Invalid Date', '-']).toContain(result)
    })
  })

  describe('exportToCSV', () => {
    let mockLink
    let mockClick

    beforeEach(() => {
      mockClick = vi.fn()
      mockLink = {
        href: '',
        download: '',
        click: mockClick
      }
      vi.spyOn(document, 'createElement').mockReturnValue(mockLink)
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:url')
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    })

    it('does nothing for empty data', () => {
      exportToCSV([], [{ key: 'name', header: 'Name' }])
      expect(mockClick).not.toHaveBeenCalled()
    })

    it('does nothing for null data', () => {
      exportToCSV(null, [{ key: 'name', header: 'Name' }])
      expect(mockClick).not.toHaveBeenCalled()
    })

    it('creates and downloads CSV', () => {
      const data = [{ name: 'Test', value: 123 }]
      const columns = [
        { key: 'name', header: 'Name' },
        { key: 'value', header: 'Value' }
      ]
      exportToCSV(data, columns, 'test-export')
      
      expect(mockClick).toHaveBeenCalled()
      expect(mockLink.download).toMatch(/test-export-.*\.csv/)
    })

    it('escapes values with commas', () => {
      const data = [{ name: 'Test, with comma' }]
      const columns = [{ key: 'name', header: 'Name' }]
      exportToCSV(data, columns)
      expect(mockClick).toHaveBeenCalled()
    })

    it('handles null values in data', () => {
      const data = [{ name: null, value: undefined }]
      const columns = [
        { key: 'name', header: 'Name' },
        { key: 'value', header: 'Value' }
      ]
      exportToCSV(data, columns)
      expect(mockClick).toHaveBeenCalled()
    })

    it('uses accessor function when provided', () => {
      const data = [{ nested: { value: 'test' } }]
      const columns = [
        { key: 'nested', header: 'Value', accessor: (row) => row.nested.value }
      ]
      exportToCSV(data, columns)
      expect(mockClick).toHaveBeenCalled()
    })
  })

  describe('exportToJSON', () => {
    let mockLink
    let mockClick

    beforeEach(() => {
      mockClick = vi.fn()
      mockLink = {
        href: '',
        download: '',
        click: mockClick
      }
      vi.spyOn(document, 'createElement').mockReturnValue(mockLink)
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:url')
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    })

    it('does nothing for empty data', () => {
      exportToJSON([])
      expect(mockClick).not.toHaveBeenCalled()
    })

    it('does nothing for null data', () => {
      exportToJSON(null)
      expect(mockClick).not.toHaveBeenCalled()
    })

    it('creates and downloads JSON', () => {
      const data = [{ name: 'Test' }]
      exportToJSON(data, 'test-export')
      
      expect(mockClick).toHaveBeenCalled()
      expect(mockLink.download).toMatch(/test-export-.*\.json/)
    })
  })
})
