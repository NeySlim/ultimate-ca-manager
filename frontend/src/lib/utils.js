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
 * Extract data field with fallback
 */
export function extractData(obj, key, fallback = '') {
  return obj?.[key] ?? fallback
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
