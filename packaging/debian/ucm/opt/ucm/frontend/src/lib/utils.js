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
