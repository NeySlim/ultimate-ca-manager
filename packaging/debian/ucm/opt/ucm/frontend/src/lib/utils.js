import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

/**
 * Safely parse JSON with fallback
 */
export function safeJsonParse(json, fallback = []) {
  if (!json) return fallback
  try {
    const parsed = JSON.parse(json)
    return parsed ?? fallback
  } catch {
    return fallback
  }
}

/**
 * Extract Common Name from subject DN
 */
export function extractCN(subject) {
  if (!subject) return ''
  const match = subject.match(/CN=([^,]+)/)
  return match ? match[1] : subject
}

/**
 * Extract data from API response
 * If key is provided, extracts that key. Otherwise extracts .data field.
 */
export function extractData(obj, key, fallback = null) {
  if (!obj) return fallback
  // If key provided, extract that specific key
  if (key !== undefined) {
    return obj?.[key] ?? fallback
  }
  // Default: extract .data field (standard API response format)
  return obj?.data ?? obj ?? fallback
}

/**
 * Format date for display
 */
export function formatDate(date, options = {}) {
  if (!date) return '-'
  try {
    return new Date(date).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      ...options
    })
  } catch {
    return '-'
  }
}

/**
 * Export data to CSV file
 * @param {Array} data - Array of objects to export
 * @param {Array} columns - Column definitions with { key, header }
 * @param {string} filename - File name without extension
 */
export function exportToCSV(data, columns, filename = 'export') {
  if (!data || data.length === 0) return
  
  // Build CSV headers
  const headers = columns.map(col => col.header || col.key)
  
  // Build CSV rows
  const rows = data.map(row => 
    columns.map(col => {
      let value = row[col.key]
      // Handle nested values
      if (col.accessor) value = col.accessor(row)
      // Escape quotes and wrap in quotes if contains comma
      if (value === null || value === undefined) value = ''
      value = String(value)
      if (value.includes(',') || value.includes('"') || value.includes('\n')) {
        value = `"${value.replace(/"/g, '""')}"`
      }
      return value
    }).join(',')
  )
  
  // Combine and download
  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${filename}-${new Date().toISOString().split('T')[0]}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

/**
 * Export data to JSON file
 * @param {Array} data - Data to export
 * @param {string} filename - File name without extension
 */
export function exportToJSON(data, filename = 'export') {
  if (!data || data.length === 0) return
  
  const json = JSON.stringify(data, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${filename}-${new Date().toISOString().split('T')[0]}.json`
  link.click()
  URL.revokeObjectURL(link.href)
}
