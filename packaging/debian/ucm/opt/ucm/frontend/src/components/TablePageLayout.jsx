/**
 * TablePageLayout - Full-width table layout with responsive filters
 * 
 * DESKTOP:
 * - Full table with search, pagination
 * - Inline filter panel on right (slim, always visible)
 * - Fine, dense UI with hover states
 * 
 * MOBILE:
 * - Full-width table (no inline panel)
 * - Filter drawer from bottom (touch-friendly)
 * - Larger touch targets, swipe gestures
 * 
 * Pattern: Audit logs style
 * - Best for: Lists with many columns, dense data, filtering needs
 * - Examples: Certificates, CAs, CSRs, Users, Audit Logs
 * 
 * Usage:
 * <TablePageLayout
 *   title="Certificates"
 *   data={certificates}
 *   columns={columns}
 *   loading={loading}
 *   onRowClick={setSelectedItem}
 *   filters={[{ key: 'status', label: 'Status', type: 'select', value, onChange, options }]}
 *   actions={<Button>Issue</Button>}
 *   pagination={{ page, total, perPage, onChange, onPerPageChange }}
 *   helpContent={<HelpCard>...</HelpCard>}
 * />
 */
import { useState, useMemo, useCallback } from 'react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { Table } from './Table'
import { SearchBar } from './SearchBar'
import { Button } from './Button'
import { Pagination } from './Pagination'
import { LoadingSpinner } from './LoadingSpinner'
import { EmptyState } from './EmptyState'
import { FilterPanel, FilterButton } from './FilterPanel'
import { HeaderBar } from './ActionBar'
import { 
  ArrowsClockwise,
  X,
  Question
} from '@phosphor-icons/react'
import { HelpModal } from './HelpModal'

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
  
  // Filters (rendered in filter panel / drawer)
  filters = [],  // [{ key, label, type: 'select'|'date'|'text', options?, value, onChange }]
  quickFilters = [], // [{ label, icon, onClick, active }]
  onClearFilters,
  
  // Sorting
  sortable = true,
  defaultSort,
  onSort,
  
  // Pagination
  pagination, // { page, total, perPage, onChange, onPerPageChange }
  
  // Actions (header buttons)
  actions,
  
  // Refresh
  onRefresh,
  
  // Empty state
  emptyIcon,
  emptyTitle = 'No data',
  emptyDescription,
  emptyAction,
  
  // Help content
  helpContent,
  
  // Stats for filter panel
  stats,  // [{ icon, label, value, color }]
  
  // Styling
  className,
  compact = false,
}) {
  const { isMobile, isTouch } = useMobile()
  
  // Filter panel / drawer state
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false)
  
  // Help modal state
  const [helpOpen, setHelpOpen] = useState(false)
  
  // Internal search state (if not controlled externally)
  const [internalSearch, setInternalSearch] = useState('')
  const search = externalSearch !== undefined ? externalSearch : internalSearch
  const setSearch = onSearch || setInternalSearch
  
  // Internal sort state
  const [sortConfig, setSortConfig] = useState(defaultSort || null)
  
  // Filter state tracking for "clear all" button
  const hasActiveFilters = filters.some(f => f.value && f.value !== '')
  const activeFilterCount = filters.filter(f => f.value && f.value !== '').length
  
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

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  // ============================================
  // MOBILE LAYOUT
  // ============================================
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full w-full bg-bg-primary", className)}>
        {/* Header */}
        <header className="shrink-0 h-14 px-4 flex items-center justify-between gap-3 border-b border-border bg-bg-secondary">
          <h1 className="text-base font-semibold text-text-primary truncate">{title}</h1>
          <div className="flex items-center gap-2 shrink-0">
            {actions}
            {helpContent && (
              <button
                type="button"
                onClick={() => setHelpOpen(true)}
                className="w-10 h-10 flex items-center justify-center rounded-lg text-text-secondary hover:bg-bg-tertiary"
              >
                <Question size={20} />
              </button>
            )}
          </div>
        </header>
        
        {/* Search + Filter bar */}
        <div className="shrink-0 px-4 py-3 border-b border-border bg-bg-primary space-y-2">
          <div className="flex items-center gap-2">
            {searchable && (
              <div className="flex-1">
                <SearchBar
                  value={search}
                  onChange={setSearch}
                  placeholder={searchPlaceholder}
                />
              </div>
            )}
            
            {/* Filter button - opens drawer */}
            {filters.length > 0 && (
              <FilterButton
                onClick={() => setFilterDrawerOpen(true)}
                activeCount={activeFilterCount}
              />
            )}
            
            {/* Refresh button */}
            {onRefresh && (
              <Button 
                variant="secondary" 
                size="md" 
                onClick={onRefresh}
                className="w-11 h-11 p-0"
              >
                <ArrowsClockwise size={18} />
              </Button>
            )}
          </div>
          
          {/* Results info */}
          <div className="text-xs text-text-secondary">
            {pagination ? (
              <>Showing {Math.min((pagination.page - 1) * pagination.perPage + 1, pagination.total)}-{Math.min(pagination.page * pagination.perPage, pagination.total)} of {pagination.total}</>
            ) : (
              <>Showing {filteredData.length} item(s)</>
            )}
            {hasActiveFilters && <span className="ml-1 text-accent-primary">(filtered)</span>}
          </div>
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
              compact={true} // Always compact on mobile
            />
          )}
        </div>
        
        {/* Pagination */}
        {pagination && pagination.total > 0 && (
          <div className="shrink-0 border-t border-border bg-bg-secondary">
            <Pagination
              page={pagination.page}
              total={pagination.total}
              perPage={pagination.perPage}
              onChange={pagination.onChange}
              onPerPageChange={pagination.onPerPageChange}
            />
          </div>
        )}
        
        {/* Filter Drawer */}
        <FilterPanel
          open={filterDrawerOpen}
          onOpenChange={setFilterDrawerOpen}
          filters={filters}
          stats={stats}
          quickFilters={quickFilters}
          onClearAll={onClearFilters}
        />
        
        {/* Help Modal */}
        <HelpModal
          open={helpOpen}
          onClose={() => setHelpOpen(false)}
          title={`${title} - Help`}
        >
          {helpContent}
        </HelpModal>
      </div>
    )
  }

  // ============================================
  // DESKTOP LAYOUT
  // ============================================
  return (
    <div className={cn("flex h-full w-full", className)}>
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header */}
        <header className="shrink-0 px-6 py-3 border-b border-border bg-bg-secondary">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
              {subtitle && (
                <p className="text-xs text-text-tertiary mt-0.5">{subtitle}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {actions}
              {helpContent && (
                <button
                  type="button"
                  onClick={() => setHelpOpen(true)}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition-colors",
                    "bg-accent-primary/10 border border-accent-primary/30",
                    "text-accent-primary hover:bg-accent-primary/20 text-xs font-medium"
                  )}
                >
                  <Question size={14} weight="bold" />
                  Help
                </button>
              )}
            </div>
          </div>
        </header>
        
        {/* Search bar */}
        <div className="shrink-0 px-4 py-3 border-b border-border flex items-center gap-3">
          {searchable && (
            <div className="flex-1 max-w-md">
              <SearchBar
                value={search}
                onChange={setSearch}
                placeholder={searchPlaceholder}
              />
            </div>
          )}
          
          {/* Results info */}
          <div className="text-xs text-text-secondary flex-1">
            {pagination ? (
              <>Showing {Math.min((pagination.page - 1) * pagination.perPage + 1, pagination.total)}-{Math.min(pagination.page * pagination.perPage, pagination.total)} of {pagination.total}</>
            ) : (
              <>Showing {filteredData.length} item(s)</>
            )}
            {hasActiveFilters && <span className="ml-1 text-accent-primary">(filtered)</span>}
          </div>
          
          {/* Refresh button */}
          {onRefresh && (
            <Button variant="secondary" size="sm" onClick={onRefresh}>
              <ArrowsClockwise size={14} />
              Refresh
            </Button>
          )}
        </div>

        {/* Table */}
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
        
        {/* Pagination */}
        {pagination && pagination.total > 0 && (
          <div className="shrink-0 border-t border-border bg-bg-secondary">
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
      
      {/* Filter Panel (Desktop - inline) */}
      {(filters.length > 0 || stats) && (
        <aside className="w-72 xl:w-80 border-l border-border bg-bg-secondary shrink-0 flex flex-col overflow-hidden">
          {/* Panel Header */}
          <div className="px-4 py-2.5 border-b border-border">
            <h2 className="text-sm font-semibold text-text-primary">Filters & Stats</h2>
          </div>
          
          {/* Panel Content */}
          <div className="flex-1 overflow-auto p-3">
            <FilterPanel
              open={true} // Always open on desktop (inline mode)
              onOpenChange={() => {}} // No-op on desktop
              filters={filters}
              stats={stats}
              quickFilters={quickFilters}
              onClearAll={onClearFilters}
            >
              {/* Help content at bottom of filters */}
              {helpContent && (
                <div className="pt-3 mt-3 border-t border-border">
                  {helpContent}
                </div>
              )}
            </FilterPanel>
          </div>
        </aside>
      )}
      
      {/* Help Modal */}
      <HelpModal
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title={`${title} - Help`}
      >
        {helpContent}
      </HelpModal>
    </div>
  )
}
