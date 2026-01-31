/**
 * TablePageLayout - Full-width table layout with filters in focus panel
 * 
 * Pattern: Audit logs style
 * - ContentPanel: Full table with search, pagination
 * - FocusPanel: Filters + Actions
 * - Modal: Item details (on row click)
 * 
 * Best for: Lists with many columns, dense data, filtering needs
 * Examples: Certificates, CAs, CSRs, Users, Audit Logs
 * 
 * Usage:
 * <TablePageLayout
 *   title="Certificates"
 *   data={certificates}
 *   columns={columns}
 *   loading={loading}
 *   onRowClick={setSelectedItem}
 *   filters={[{ key: 'status', label: 'Status', options: [...] }]}
 *   actions={<Button>Issue</Button>}
 *   pagination={{ page, total, perPage, onChange, onPerPageChange }}
 *   helpContent={<HelpCard>...</HelpCard>}
 * />
 */
import { useState, useMemo, useCallback } from 'react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { PageLayout, FocusItem } from './PageLayout'
import { Table } from './Table'
import { SearchBar } from './SearchBar'
import { SelectComponent as Select } from './Select'
import { Button } from './Button'
import { Badge } from './Badge'
import { Pagination } from './Pagination'
import { LoadingSpinner } from './LoadingSpinner'
import { EmptyState } from './EmptyState'
import { Input } from './Input'

// Simple native select for filters
function FilterSelect({ value, onChange, options = [], placeholder, className }) {
  return (
    <select
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "w-full px-2.5 py-1.5 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary",
        "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary",
        className
      )}
    >
      <option value="">{placeholder || 'All'}</option>
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  )
}
import { 
  ArrowsClockwise, 
  FunnelSimple, 
  X,
  CaretDown
} from '@phosphor-icons/react'

export function TablePageLayout({
  // Page metadata
  title,
  subtitle,
  
  // Data
  data = [],
  columns = [],
  loading = false,
  
  // Row interaction
  onRowClick,
  rowActions,
  
  // Search
  searchable = true,
  searchPlaceholder = 'Search...',
  searchKeys = [],
  onSearch,
  externalSearch, // If provided, search is controlled externally
  
  // Filters (rendered in focus panel)
  filters = [],  // [{ key, label, type: 'select'|'date'|'text', options?, value, onChange }]
  quickFilters = [], // [{ icon, title, subtitle, filter: { key, value } }]
  onClearFilters,
  
  // Sorting
  sortable = true,
  defaultSort,
  onSort,
  
  // Pagination
  pagination, // { page, total, perPage, onChange, onPerPageChange }
  
  // Actions (rendered in focus panel header or as buttons)
  actions,
  focusActions, // Additional actions in focus panel footer
  
  // Refresh
  onRefresh,
  
  // Empty state
  emptyIcon,
  emptyTitle = 'No data',
  emptyDescription,
  emptyAction,
  
  // Help content (rendered in help modal)
  helpContent,
  
  // Stats for focus panel header
  stats,  // [{ icon, label, value, color }]
  
  // Custom focus panel content (replaces default filters)
  focusContent,
  focusFooter,
  
  // Styling
  className,
  compact = false,
}) {
  const { isMobile } = useMobile()
  
  // Internal search state (if not controlled externally)
  const [internalSearch, setInternalSearch] = useState('')
  const search = externalSearch !== undefined ? externalSearch : internalSearch
  const setSearch = onSearch || setInternalSearch
  
  // Internal sort state
  const [sortConfig, setSortConfig] = useState(defaultSort || null)
  
  // Filter state tracking for "clear all" button
  const hasActiveFilters = filters.some(f => f.value && f.value !== '')
  
  // Client-side filtering (if no external handler)
  const filteredData = useMemo(() => {
    if (!data || data.length === 0) return []
    
    let result = [...data]
    
    // Apply search filter (client-side)
    if (search && searchKeys.length > 0 && !onSearch) {
      const searchLower = search.toLowerCase()
      result = result.filter(item => 
        searchKeys.some(key => {
          const value = item[key]
          return value && String(value).toLowerCase().includes(searchLower)
        })
      )
    }
    
    // Apply sort
    if (sortConfig && !onSort) {
      result.sort((a, b) => {
        const aVal = a[sortConfig.key]
        const bVal = b[sortConfig.key]
        if (aVal === bVal) return 0
        if (aVal === null || aVal === undefined) return 1
        if (bVal === null || bVal === undefined) return -1
        const comparison = aVal < bVal ? -1 : 1
        return sortConfig.direction === 'asc' ? comparison : -comparison
      })
    }
    
    return result
  }, [data, search, searchKeys, onSearch, sortConfig, onSort])
  
  // Handle sort
  const handleSort = useCallback((key) => {
    const newSort = {
      key,
      direction: sortConfig?.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc'
    }
    setSortConfig(newSort)
    onSort?.(newSort)
  }, [sortConfig, onSort])
  
  // Build focus panel content with filters
  const defaultFocusContent = (
    <div className="p-3 space-y-4">
      {/* Stats */}
      {stats && stats.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {stats.map((stat, i) => {
            const StatIcon = stat.icon
            return (
              <div key={i} className="text-center p-2 bg-bg-tertiary rounded-lg">
                {StatIcon && <StatIcon size={16} className={cn("mx-auto mb-1", stat.color || "text-accent-primary")} />}
                <p className={cn("text-lg font-bold", stat.color || "text-text-primary")}>{stat.value}</p>
                <p className="text-[10px] text-text-secondary">{stat.label}</p>
              </div>
            )
          })}
        </div>
      )}
      
      {/* Filters */}
      {filters.length > 0 && (
        <div className="space-y-3">
          {filters.map((filter, i) => (
            <div key={filter.key || i} className="space-y-1.5">
              <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
                {filter.label}
              </label>
              
              {filter.type === 'select' && (
                <FilterSelect
                  value={filter.value || ''}
                  onChange={filter.onChange}
                  options={filter.options || []}
                  placeholder={filter.placeholder || `All ${filter.label}`}
                  className="w-full"
                />
              )}
              
              {filter.type === 'date' && (
                <Input
                  type="date"
                  value={filter.value || ''}
                  onChange={(e) => filter.onChange(e.target.value)}
                  className="w-full"
                />
              )}
              
              {filter.type === 'text' && (
                <Input
                  type="text"
                  value={filter.value || ''}
                  onChange={(e) => filter.onChange(e.target.value)}
                  placeholder={filter.placeholder}
                  className="w-full"
                />
              )}
            </div>
          ))}
        </div>
      )}
      
      {/* Quick Filters */}
      {quickFilters.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Quick Filters
          </h4>
          <div className="space-y-1">
            {quickFilters.map((qf, i) => (
              <FocusItem 
                key={i}
                icon={qf.icon}
                title={qf.title}
                subtitle={qf.subtitle}
                selected={qf.selected}
                onClick={qf.onClick}
              />
            ))}
          </div>
        </div>
      )}
      
      {/* Clear Filters */}
      {hasActiveFilters && onClearFilters && (
        <Button 
          variant="ghost" 
          size="sm" 
          className="w-full" 
          onClick={onClearFilters}
        >
          <X size={14} />
          Clear All Filters
        </Button>
      )}
      
      {/* Help Content */}
      {helpContent && (
        <div className="pt-2 border-t border-border space-y-3">
          {helpContent}
        </div>
      )}
    </div>
  )
  
  // Actions for focus panel
  const defaultFocusActions = (
    <>
      {onRefresh && (
        <Button variant="secondary" size="sm" onClick={onRefresh} className="flex-1">
          <ArrowsClockwise size={14} />
          Refresh
        </Button>
      )}
      {focusActions}
    </>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <PageLayout
      title={title}
      focusTitle="Filters & Actions"
      focusContent={focusContent || defaultFocusContent}
      focusActions={actions || focusActions ? (
        <div className="flex gap-2">
          {actions}
          {!actions && defaultFocusActions}
        </div>
      ) : undefined}
      focusFooter={focusFooter || `${filteredData.length} item(s)`}
      helpContent={null} // Help is in focus panel
    >
      {/* Main Content */}
      <div className={cn("flex flex-col h-full", className)}>
        {/* Header - Search Bar */}
        <div className="p-4 border-b border-border space-y-3">
          <div className="flex items-center gap-3">
            {searchable && (
              <div className="flex-1">
                <SearchBar
                  value={search}
                  onChange={setSearch}
                  placeholder={searchPlaceholder}
                />
              </div>
            )}
            {onRefresh && (
              <Button variant="secondary" size="sm" onClick={onRefresh}>
                <ArrowsClockwise size={14} />
              </Button>
            )}
          </div>

          {/* Results info */}
          {subtitle ? (
            <div className="text-xs text-text-secondary">{subtitle}</div>
          ) : (
            <div className="text-xs text-text-secondary">
              {pagination ? (
                <>Showing {Math.min((pagination.page - 1) * pagination.perPage + 1, pagination.total)}-{Math.min(pagination.page * pagination.perPage, pagination.total)} of {pagination.total}</>
              ) : (
                <>Showing {filteredData.length} item(s)</>
              )}
              {hasActiveFilters && <span className="ml-1">(filtered)</span>}
            </div>
          )}
        </div>

        {/* Table - Scrollable */}
        <div className="flex-1 overflow-auto">
          {filteredData.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={emptyIcon}
                title={emptyTitle}
                description={search || hasActiveFilters ? "Try adjusting your filters" : emptyDescription}
                action={emptyAction}
              />
            </div>
          ) : (
            <Table
              data={filteredData}
              columns={columns}
              onRowClick={onRowClick}
              sortable={sortable}
              sortConfig={sortConfig}
              onSort={handleSort}
              rowActions={rowActions}
              compact={compact}
            />
          )}
        </div>
        
        {/* Pagination - Fixed at bottom */}
        {pagination && pagination.total > pagination.perPage && (
          <div className="border-t border-border bg-bg-secondary">
            <Pagination
              page={pagination.page}
              total={pagination.total}
              perPage={pagination.perPage}
              onChange={pagination.onChange}
              onPerPageChange={pagination.onPerPageChange}
            />
          </div>
        )}
      </div>
    </PageLayout>
  )
}
