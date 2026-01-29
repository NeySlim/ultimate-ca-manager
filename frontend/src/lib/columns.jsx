/**
 * Table Column Definitions
 * Reusable column configurations for tables
 */
import { Badge } from '../components/Badge'
import { formatDate, formatDateTime } from '../lib/utils'
import { STATUS_COLORS } from '../constants/config'

/**
 * Name column with bold text
 */
export const nameColumn = (key = 'name', label = 'Name') => ({
  key,
  label,
  render: (val) => <span className="font-medium">{val || '-'}</span>
})

/**
 * Date column with locale formatting
 */
export const dateColumn = (key, label, options = {}) => ({
  key,
  label,
  render: (val) => {
    if (!val) return '-'
    return options.showTime ? formatDateTime(val) : formatDate(val)
  }
})

/**
 * Status badge column
 */
export const statusColumn = (key = 'status', label = 'Status', variantMap = {}) => ({
  key,
  label,
  render: (val) => {
    const variant = variantMap[val] || (val === 'valid' || val === 'active' ? 'success' : 'default')
    return <Badge variant={variant}>{val}</Badge>
  }
})

/**
 * Boolean column (Yes/No or checkmark)
 */
export const booleanColumn = (key, label, options = { trueText: 'Yes', falseText: 'No' }) => ({
  key,
  label,
  render: (val) => val ? options.trueText : options.falseText
})

/**
 * Email column
 */
export const emailColumn = (key = 'email', label = 'Email') => ({
  key,
  label,
  render: (val) => val ? <span className="text-text-secondary">{val}</span> : '-'
})

/**
 * Count/Number column
 */
export const countColumn = (key, label, suffix = '') => ({
  key,
  label,
  render: (val) => val !== null && val !== undefined ? `${val}${suffix}` : '-'
})

/**
 * Truncated text column (for long values)
 */
export const truncatedColumn = (key, label, maxLength = 30) => ({
  key,
  label,
  render: (val) => {
    if (!val) return '-'
    return val.length > maxLength ? `${val.substring(0, maxLength)}...` : val
  }
})

/**
 * Certificate status column with color coding
 */
export const certStatusColumn = () => ({
  key: 'status',
  label: 'Status',
  render: (val) => {
    const colors = STATUS_COLORS[val] || STATUS_COLORS.info
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}>
        {val}
      </span>
    )
  }
})

/**
 * Expiry column with warning coloring
 */
export const expiryColumn = (key = 'valid_to', label = 'Expires') => ({
  key,
  label,
  render: (val) => {
    if (!val) return '-'
    const date = new Date(val)
    const now = new Date()
    const daysUntil = Math.ceil((date - now) / (1000 * 60 * 60 * 24))
    
    let colorClass = 'text-text-primary'
    if (daysUntil < 0) colorClass = 'text-red-500'
    else if (daysUntil < 7) colorClass = 'text-red-500'
    else if (daysUntil < 30) colorClass = 'text-orange-500'
    
    return <span className={colorClass}>{formatDate(val)}</span>
  }
})
