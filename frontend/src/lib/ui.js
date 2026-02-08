/**
 * Global UI Utilities
 * Centralized helpers for consistent UI across the app
 */

// =============================================================================
// LABELS / i18n
// =============================================================================

export const labels = {
  // Common actions
  help: 'Help',
  helpAndInfo: 'Help and information',
  save: 'Save',
  cancel: 'Cancel',
  delete: 'Delete',
  edit: 'Edit',
  create: 'Create',
  close: 'Close',
  enable: 'Enable',
  disable: 'Disable',
  test: 'Test',
  refresh: 'Refresh',
  export: 'Export',
  import: 'Import',
  search: 'Search',
  filter: 'Filter',
  clear: 'Clear',
  clearFilters: 'Clear filters',
  
  // Status
  enabled: 'Enabled',
  disabled: 'Disabled',
  active: 'Active',
  inactive: 'Inactive',
  pending: 'Pending',
  valid: 'Valid',
  expired: 'Expired',
  revoked: 'Revoked',
  
  // Empty states
  noData: 'No data',
  noResults: 'No results',
  selectItem: 'Select an item to view details',
  
  // Entities
  certificate: 'Certificate',
  certificates: 'Certificates',
  ca: 'CA',
  cas: 'CAs',
  user: 'User',
  users: 'Users',
  group: 'Group',
  groups: 'Groups',
  role: 'Role',
  roles: 'Roles',
  template: 'Template',
  templates: 'Templates',
  provider: 'Provider',
  providers: 'Providers',
  member: 'Member',
  members: 'Members',
}

/**
 * Get help title for a page
 * @param {string} pageTitle - The page title
 * @returns {string} - Formatted help title
 */
export function getHelpTitle(pageTitle) {
  return `${pageTitle} - ${labels.help}`
}

// =============================================================================
// PLURALIZATION
// =============================================================================

const irregularPlurals = {
  ca: 'CAs',
  CA: 'CAs',
  csr: 'CSRs',
  CSR: 'CSRs',
  certificate: 'certificates',
  Certificate: 'Certificates',
}

/**
 * Pluralize a word based on count
 * @param {number} count - The count
 * @param {string} singular - Singular form
 * @param {string} [plural] - Optional plural form (auto-generated if not provided)
 * @returns {string} - Formatted string like "1 member" or "5 members"
 */
export function pluralize(count, singular, plural) {
  const pluralForm = plural || irregularPlurals[singular] || `${singular}s`
  return count === 1 ? `${count} ${singular}` : `${count} ${pluralForm}`
}

/**
 * Get just the word form without the count
 * @param {number} count - The count
 * @param {string} singular - Singular form
 * @param {string} [plural] - Optional plural form
 * @returns {string} - Just the word in correct form
 */
export function pluralWord(count, singular, plural) {
  const pluralForm = plural || irregularPlurals[singular] || `${singular}s`
  return count === 1 ? singular : pluralForm
}

// =============================================================================
// TEXT FORMATTING
// =============================================================================

/**
 * Convert string to Title Case
 * @param {string} str - Input string
 * @returns {string} - Title cased string
 */
export function toTitleCase(str) {
  if (!str) return ''
  return str
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Format panel/section header (Title Case, never ALL CAPS)
 * @param {string} str - Input string
 * @returns {string} - Formatted header
 */
export function formatHeader(str) {
  if (!str) return ''
  // If all caps, convert to title case
  if (str === str.toUpperCase() && str.length > 1) {
    return toTitleCase(str)
  }
  return str
}

// =============================================================================
// STATUS DISPLAY
// =============================================================================

/**
 * Get status label with consistent casing
 * @param {boolean|string} status - Status value
 * @param {string} [trueLabel] - Label when true (default: 'Enabled')
 * @param {string} [falseLabel] - Label when false (default: 'Disabled')
 * @returns {string} - Formatted status label
 */
export function statusLabel(status, trueLabel = labels.enabled, falseLabel = labels.disabled) {
  if (typeof status === 'boolean') {
    return status ? trueLabel : falseLabel
  }
  return toTitleCase(String(status))
}

/**
 * Get status variant for Badge component
 * @param {string|boolean} status - Status value
 * @returns {string} - Badge variant
 */
export function statusVariant(status) {
  if (typeof status === 'boolean') {
    return status ? 'success' : 'secondary'
  }
  
  const statusMap = {
    active: 'success',
    enabled: 'success',
    valid: 'success',
    signed: 'success',
    approved: 'success',
    disabled: 'secondary',
    inactive: 'secondary',
    pending: 'warning',
    expiring: 'warning',
    expired: 'danger',
    revoked: 'danger',
    rejected: 'danger',
    error: 'danger',
  }
  
  return statusMap[String(status).toLowerCase()] || 'secondary'
}

// =============================================================================
// DATE/TIME FORMATTING
// =============================================================================

/**
 * Format date for display
 * @param {string|Date} date - Date value
 * @param {object} options - Intl.DateTimeFormat options
 * @returns {string} - Formatted date
 */
export function formatDate(date, options = {}) {
  if (!date) return '-'
  
  const defaultOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    ...options
  }
  
  try {
    return new Intl.DateTimeFormat('en-US', defaultOptions).format(new Date(date))
  } catch {
    return String(date)
  }
}

/**
 * Format date with time
 * @param {string|Date} date - Date value
 * @returns {string} - Formatted date and time
 */
export function formatDateTime(date) {
  return formatDate(date, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Format relative time (e.g., "2 hours ago")
 * @param {string|Date} date - Date value
 * @param {function} t - Optional translation function
 * @returns {string} - Relative time string
 */
export function formatRelativeTime(date, t) {
  if (!date) return '-'
  
  const now = new Date()
  const then = new Date(date)
  const diffMs = now - then
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffSecs / 60)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)
  
  // Use translation function if provided, otherwise fallback to English
  if (t) {
    if (diffSecs < 60) return t('common.justNow')
    if (diffMins < 60) return t('common.minutesAgo', { count: diffMins })
    if (diffHours < 24) return t('common.hoursAgo', { count: diffHours })
    if (diffDays < 7) return t('common.daysAgo', { count: diffDays })
  } else {
    if (diffSecs < 60) return 'just now'
    if (diffMins < 60) return `${diffMins} ${pluralWord(diffMins, 'minute')} ago`
    if (diffHours < 24) return `${diffHours} ${pluralWord(diffHours, 'hour')} ago`
    if (diffDays < 7) return `${diffDays} ${pluralWord(diffDays, 'day')} ago`
  }
  
  return formatDate(date)
}

// =============================================================================
// NUMBER FORMATTING
// =============================================================================

/**
 * Format large numbers with K/M suffix
 * @param {number} num - Number to format
 * @returns {string} - Formatted number
 */
export function formatNumber(num) {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return String(num)
}

// =============================================================================
// UI DENSITY SYSTEM
// =============================================================================

/**
 * Density presets for consistent spacing across the app
 * Use these in layouts, tables, cards, and forms
 */
export const DENSITY = {
  compact: {
    gap: 'gap-2',        // 8px
    padding: 'p-3',      // 12px
    space: 'space-y-2',  // 8px vertical
    iconSize: 'table',   // 28px container, 14px icon
  },
  default: {
    gap: 'gap-3',        // 12px
    padding: 'p-4',      // 16px
    space: 'space-y-3',  // 12px vertical
    iconSize: 'sm',      // 32px container, 16px icon
  },
  comfortable: {
    gap: 'gap-4',        // 16px
    padding: 'p-6',      // 24px
    space: 'space-y-4',  // 16px vertical
    iconSize: 'md',      // 40px container, 20px icon
  }
}

/**
 * Icon size scale - matches IconBadge sizes
 * Use for consistent icon sizing across all components
 */
export const ICON_SCALE = {
  table: { container: 'w-7 h-7', size: 14, rounded: 'rounded-lg' },   // 28px - dense tables
  xs: { container: 'w-6 h-6', size: 12, rounded: 'rounded-md' },      // 24px
  sm: { container: 'w-8 h-8', size: 16, rounded: 'rounded-lg' },      // 32px
  md: { container: 'w-10 h-10', size: 20, rounded: 'rounded-xl' },    // 40px - cards/mobile
  lg: { container: 'w-12 h-12', size: 24, rounded: 'rounded-xl' },    // 48px
  xl: { container: 'w-14 h-14', size: 28, rounded: 'rounded-2xl' },   // 56px - hero/empty states
}

/**
 * Get density-appropriate icon scale
 * @param {string} density - 'compact' | 'default' | 'comfortable'
 * @returns {object} - Icon scale object with container, size, rounded
 */
export function getIconScale(density = 'default') {
  const iconSize = DENSITY[density]?.iconSize || 'sm'
  return ICON_SCALE[iconSize]
}
