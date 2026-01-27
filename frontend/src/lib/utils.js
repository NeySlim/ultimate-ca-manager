import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

/**
 * Extract Common Name from DN (Distinguished Name) string
 */
export function extractCN(dnString) {
  if (!dnString) return 'Unknown'
  
  const parts = dnString.split(',')
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith('CN=')) {
      return trimmed.substring(3)
    }
  }
  
  // Fallback to first component
  const firstPart = parts[0].trim()
  if (firstPart.includes('=')) {
    return firstPart.split('=')[1]
  }
  
  return dnString.substring(0, 30)
}

/**
 * Format date with fallback
 */
export function formatDate(date, fallback = 'N/A') {
  if (!date) return fallback
  
  try {
    const d = new Date(date)
    if (isNaN(d.getTime())) return fallback
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  } catch {
    return fallback
  }
}

/**
 * Format datetime with fallback
 */
export function formatDateTime(date, fallback = 'N/A') {
  if (!date) return fallback
  
  try {
    const d = new Date(date)
    if (isNaN(d.getTime())) return fallback
    return d.toLocaleString()
  } catch {
    return fallback
  }
}

/**
 * Parse API response with auto-extraction of .data field
 */
export function extractData(response) {
  if (!response) return null
  
  // If response has .data, extract it
  if (typeof response === 'object' && 'data' in response) {
    return response.data
  }
  
  return response
}
