/**
 * Application Configuration Constants
 * Centralized configuration values to avoid magic numbers
 */

// Certificate & Key Validity
export const VALIDITY = {
  DEFAULT_DAYS: 365,
  SHORT_DAYS: 90,
  LONG_DAYS: 730,
  CA_YEARS: 10,
  MTLS_DEFAULT_DAYS: 365,
  API_KEY_DEFAULT_DAYS: 90,
  SCEP_CHALLENGE_HOURS: 24,
}

// Pagination
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  SMALL_PAGE_SIZE: 10,
  LARGE_PAGE_SIZE: 50,
  EXPORT_ALL: 1000,
}

// Time Constants (in seconds)
export const TIME = {
  SECOND: 1,
  MINUTE: 60,
  HOUR: 3600,
  DAY: 86400,
  WEEK: 604800,
}

// Certificate Expiry Warnings (in days)
export const EXPIRY_WARNING = {
  CRITICAL: 7,
  WARNING: 30,
  INFO: 90,
}

// Audit & Retention
export const AUDIT = {
  DEFAULT_RETENTION_DAYS: 90,
  MIN_RETENTION_DAYS: 30,
  MAX_RETENTION_DAYS: 365,
  STATS_PERIOD_DAYS: 30,
}

// Session & Security
export const SESSION = {
  DEFAULT_TIMEOUT_MINUTES: 30,
  MAX_TIMEOUT_MINUTES: 1440,
  RATE_LIMIT_REQUESTS: 60,
  RATE_LIMIT_WINDOW_SECONDS: 60,
}

// Backup
export const BACKUP = {
  DEFAULT_RETENTION_DAYS: 30,
  MIN_PASSWORD_LENGTH: 12,
}

// UI Refresh Intervals (in milliseconds)
export const REFRESH = {
  DASHBOARD: 60000,      // 1 minute
  ACTIVITY_LOG: 30000,   // 30 seconds
  CERT_STATUS: 300000,   // 5 minutes
}

// Dashboard Limits
export const DASHBOARD = {
  RECENT_ACTIVITY_COUNT: 20,
  RECENT_CAS_COUNT: 5,
  EXPIRING_CERTS_DAYS: 30,
}

// File Size Limits (in bytes)
export const FILE_SIZE = {
  MAX_CERT_UPLOAD: 1024 * 1024,      // 1 MB
  MAX_BACKUP_UPLOAD: 100 * 1024 * 1024, // 100 MB
}

// Validity Period Options (for dropdowns)
export const VALIDITY_OPTIONS = [
  { value: '90', label: '90 days' },
  { value: '180', label: '180 days' },
  { value: '365', label: '1 year' },
  { value: '730', label: '2 years' },
  { value: '1095', label: '3 years' },
]

// Key Type Options
export const KEY_TYPE_OPTIONS = [
  { value: 'RSA-2048', label: 'RSA 2048' },
  { value: 'RSA-4096', label: 'RSA 4096' },
  { value: 'ECDSA-P256', label: 'ECDSA P-256' },
  { value: 'ECDSA-P384', label: 'ECDSA P-384' },
]

// Status Colors (semantic)
export const STATUS_COLORS = {
  valid: { bg: 'bg-green-500/10', text: 'text-green-500', border: 'border-green-500/30' },
  warning: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/30' },
  expired: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/30' },
  revoked: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/30' },
  pending: { bg: 'bg-orange-500/10', text: 'text-orange-500', border: 'border-orange-500/30' },
  info: { bg: 'bg-blue-500/10', text: 'text-blue-500', border: 'border-blue-500/30' },
}
