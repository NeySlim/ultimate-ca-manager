/**
 * ResponsiveTable - Table component with desktop/mobile optimization
 * 
 * DESKTOP:
 * - Dense rows with hover states
 * - All columns visible
 * - Compact pagination
 * - Click anywhere on row to select
 * 
 * MOBILE:
 * - Card-like rows with larger touch targets
 * - Key columns only (prioritized)
 * - Simplified pagination
 * - Full-width tap areas
 * 
 * Usage:
 * <ResponsiveTable
 *   data={certificates}
 *   columns={[
 *     { key: 'name', header: 'Name', priority: 1 },
 *     { key: 'status', header: 'Status', priority: 2, render: (val) => <Badge>{val}</Badge> },
 *     { key: 'expiry', header: 'Expires', priority: 3, hideOnMobile: true }
 *   ]}
 *   onRowClick={(row) => setSelectedItem(row)}
 *   selectedId={selectedItem?.id}
 *   loading={loading}
 *   emptyTitle="No certificates"
 *   emptyDescription="Issue your first certificate"
 *   searchable
 *   searchKeys={['name', 'subject']}
 *   sortable
 *   paginated
 *   pageSize={25}
 * />
 */
import { useState, useMemo, useCallback } from 'react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { LoadingSpinner } from './LoadingSpinner'
import { EmptyState } from './EmptyState'
import { SearchBar } from './SearchBar'
import { Badge } from './Badge'
import { FilterSelect } from './ui/Select'
import { 
  CaretUp, CaretDown, CaretLeft, CaretRight,
  DotsThreeVertical
} from '@phosphor-icons/react'

export function ResponsiveTable({
  // Data
  data = [],
  columns = [],
  loading = false,
  
  // Selection
  onRowClick,
  selectedId,
  idKey = 'id',
  
  // Row actions (dropdown menu)
  rowActions,          // (row) => [{ label, icon, onClick, variant }]
  
  // Search
  searchable = false,
  searchPlaceholder = 'Search...',
  searchKeys = [],
  onSearch,            // External search handler
  
  // Sort
  sortable = false,
  defaultSort,         // { key, direction: 'asc' | 'desc' }
  onSort,              // External sort handler
  
  // Pagination
  paginated = false,
  pageSize = 25,
  pageSizeOptions = [10, 25, 50, 100],
  
  // Empty state
  emptyIcon,
  emptyTitle = 'No data',
  emptyDescription,
  emptyAction,
  
  // Styling
  className,
}) {
  const { isMobile } = useMobile()
  
  // Internal state
  const [search, setSearch] = useState('')
  const [sortConfig, setSortConfig] = useState(defaultSort || null)
  const [page, setPage] = useState(1)
  const [currentPageSize, setCurrentPageSize] = useState(pageSize)
  
  // Filter columns for mobile (only show priority columns)
  const visibleColumns = useMemo(() => {
    if (!isMobile) return columns
    return columns.filter(col => !col.hideOnMobile)
  }, [columns, isMobile])
  
  // Apply search filter
  const searchedData = useMemo(() => {
    if (!search || searchKeys.length === 0 || onSearch) return data
    
    const searchLower = search.toLowerCase()
    return data.filter(item =>
      searchKeys.some(key => {
        const value = item[key]
        return value && String(value).toLowerCase().includes(searchLower)
      })
    )
  }, [data, search, searchKeys, onSearch])
  
  // Apply sort
  const sortedData = useMemo(() => {
    if (!sortConfig || onSort) return searchedData
    
    return [...searchedData].sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]
      
      if (aVal === bVal) return 0
      if (aVal === null || aVal === undefined) return 1
      if (bVal === null || bVal === undefined) return -1
      
      const comparison = aVal < bVal ? -1 : 1
      return sortConfig.direction === 'asc' ? comparison : -comparison
    })
  }, [searchedData, sortConfig, onSort])
  
  // Apply pagination
  const paginatedData = useMemo(() => {
    if (!paginated) return sortedData
    
    const start = (page - 1) * currentPageSize
    return sortedData.slice(start, start + currentPageSize)
  }, [sortedData, paginated, page, currentPageSize])
  
  const totalPages = Math.ceil(sortedData.length / currentPageSize)
  
  // Handlers
  const handleSort = useCallback((key) => {
    const newSort = {
      key,
      direction: sortConfig?.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc'
    }
    setSortConfig(newSort)
    onSort?.(newSort)
  }, [sortConfig, onSort])
  
  const handleSearch = useCallback((value) => {
    setSearch(value)
    setPage(1) // Reset to first page on search
    onSearch?.(value)
  }, [onSearch])
  
  const handlePageChange = useCallback((newPage) => {
    setPage(Math.max(1, Math.min(newPage, totalPages)))
  }, [totalPages])
  
  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <LoadingSpinner />
      </div>
    )
  }

  // =============================================================================
  // MOBILE LAYOUT - Card-like rows
  // =============================================================================
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full", className)}>
        {/* Search bar (mobile) */}
        {searchable && (
          <div className="p-3 border-b border-border">
            <SearchBar
              value={search}
              onChange={handleSearch}
              placeholder={searchPlaceholder}
            />
          </div>
        )}
        
        {/* Results count */}
        <div className="px-3 py-2 text-xs text-text-tertiary border-b border-border bg-bg-tertiary/30">
          {sortedData.length} result{sortedData.length !== 1 ? 's' : ''}
          {search && ` for "${search}"`}
        </div>
        
        {/* List */}
        <div className="flex-1 overflow-auto">
          {paginatedData.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={emptyIcon}
                title={emptyTitle}
                description={search ? `No results for "${search}"` : emptyDescription}
                action={emptyAction}
              />
            </div>
          ) : (
            <div className="divide-y divide-border">
              {paginatedData.map((row, rowIndex) => (
                <MobileRow
                  key={row[idKey] || rowIndex}
                  row={row}
                  columns={visibleColumns}
                  selected={selectedId && row[idKey] === selectedId}
                  onClick={() => onRowClick?.(row)}
                  actions={rowActions?.(row)}
                />
              ))}
            </div>
          )}
        </div>
        
        {/* Pagination (mobile) */}
        {paginated && totalPages > 1 && (
          <MobilePagination
            page={page}
            totalPages={totalPages}
            total={sortedData.length}
            onChange={handlePageChange}
          />
        )}
      </div>
    )
  }

  // =============================================================================
  // DESKTOP LAYOUT - Dense table
  // =============================================================================
  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Search bar (desktop) */}
      {searchable && (
        <div className="px-4 py-3 border-b border-border flex items-center gap-4">
          <div className="w-80">
            <SearchBar
              value={search}
              onChange={handleSearch}
              placeholder={searchPlaceholder}
            />
          </div>
          <span className="text-xs text-text-tertiary">
            {sortedData.length} result{sortedData.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}
      
      {/* Table */}
      <div className="flex-1 overflow-auto">
        {paginatedData.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={emptyIcon}
              title={emptyTitle}
              description={search ? `No results for "${search}"` : emptyDescription}
              action={emptyAction}
            />
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-bg-secondary z-10">
              <tr className="border-b border-border">
                {visibleColumns.map(col => (
                  <th
                    key={col.key}
                    className={cn(
                      "px-4 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider",
                      sortable && col.sortable !== false && "cursor-pointer select-none hover:text-text-primary",
                      col.align === 'right' && "text-right",
                      col.align === 'center' && "text-center",
                      col.width && `w-[${col.width}]`
                    )}
                    onClick={() => sortable && col.sortable !== false && handleSort(col.key)}
                  >
                    <div className="flex items-center gap-1">
                      <span>{col.header}</span>
                      {sortable && col.sortable !== false && sortConfig?.key === col.key && (
                        sortConfig.direction === 'asc' 
                          ? <CaretUp size={12} weight="bold" />
                          : <CaretDown size={12} weight="bold" />
                      )}
                    </div>
                  </th>
                ))}
                {rowActions && <th className="w-10" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {paginatedData.map((row, rowIndex) => (
                <DesktopRow
                  key={row[idKey] || rowIndex}
                  row={row}
                  columns={visibleColumns}
                  selected={selectedId && row[idKey] === selectedId}
                  onClick={() => onRowClick?.(row)}
                  actions={rowActions?.(row)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
      
      {/* Pagination (desktop) */}
      {paginated && sortedData.length > 0 && (
        <DesktopPagination
          page={page}
          totalPages={totalPages}
          total={sortedData.length}
          pageSize={currentPageSize}
          pageSizeOptions={pageSizeOptions}
          onPageChange={handlePageChange}
          onPageSizeChange={(size) => { setCurrentPageSize(size); setPage(1); }}
        />
      )}
    </div>
  )
}

// =============================================================================
// DESKTOP ROW
// =============================================================================

function DesktopRow({ row, columns, selected, onClick, actions }) {
  const [menuOpen, setMenuOpen] = useState(false)
  
  return (
    <tr
      className={cn(
        "group transition-colors cursor-pointer",
        selected 
          ? "bg-accent-primary/10" 
          : "hover:bg-bg-tertiary/50"
      )}
      onClick={onClick}
    >
      {columns.map(col => {
        const value = row[col.key]
        const rendered = col.render ? col.render(value, row) : (value ?? '—')
        
        return (
          <td
            key={col.key}
            className={cn(
              "px-4 py-2.5 text-sm text-text-primary",
              col.align === 'right' && "text-right",
              col.align === 'center' && "text-center"
            )}
          >
            {rendered}
          </td>
        )
      })}
      
      {actions && actions.length > 0 && (
        <td className="px-2 py-1">
          <div className="relative">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
              className={cn(
                "p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary",
                "opacity-0 group-hover:opacity-100 transition-opacity",
                menuOpen && "opacity-100"
              )}
            >
              <DotsThreeVertical size={16} weight="bold" />
            </button>
            
            {menuOpen && (
              <>
                <div 
                  className="fixed inset-0 z-10" 
                  onClick={(e) => { e.stopPropagation(); setMenuOpen(false); }}
                />
                <div className="absolute right-0 top-full mt-1 z-20 bg-bg-secondary border border-border rounded-lg shadow-lg py-1 min-w-[140px]">
                  {actions.map((action, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setMenuOpen(false)
                        action.onClick?.()
                      }}
                      className={cn(
                        "w-full px-3 py-1.5 text-sm text-left flex items-center gap-2 hover:bg-bg-tertiary",
                        action.variant === 'danger' && "text-status-error"
                      )}
                    >
                      {action.icon && <action.icon size={14} />}
                      {action.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </td>
      )}
    </tr>
  )
}

// =============================================================================
// MOBILE ROW - Card-like
// =============================================================================

function MobileRow({ row, columns, selected, onClick, actions }) {
  const [menuOpen, setMenuOpen] = useState(false)
  
  // Get primary column (first one) and secondary columns
  const primaryCol = columns[0]
  const secondaryColumns = columns.slice(1, 3) // Show max 2 secondary on mobile
  
  const primaryValue = primaryCol?.render 
    ? primaryCol.render(row[primaryCol.key], row) 
    : (row[primaryCol?.key] ?? '—')
  
  return (
    <div
      className={cn(
        "px-4 py-3 active:bg-bg-tertiary transition-colors",
        selected && "bg-accent-primary/10"
      )}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Primary value */}
          <div className="font-medium text-text-primary truncate">
            {primaryValue}
          </div>
          
          {/* Secondary values */}
          {secondaryColumns.length > 0 && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
              {secondaryColumns.map(col => {
                const value = row[col.key]
                const rendered = col.render ? col.render(value, row) : (value ?? '—')
                return (
                  <div key={col.key} className="flex items-center gap-1 text-xs text-text-secondary">
                    <span className="text-text-tertiary">{col.header}:</span>
                    {rendered}
                  </div>
                )
              })}
            </div>
          )}
        </div>
        
        {/* Actions button */}
        {actions && actions.length > 0 && (
          <div className="relative shrink-0">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
              className="w-10 h-10 flex items-center justify-center rounded-lg text-text-tertiary active:bg-bg-tertiary"
            >
              <DotsThreeVertical size={20} weight="bold" />
            </button>
            
            {menuOpen && (
              <>
                <div 
                  className="fixed inset-0 z-10" 
                  onClick={(e) => { e.stopPropagation(); setMenuOpen(false); }}
                />
                <div className="absolute right-0 top-full mt-1 z-20 bg-bg-secondary border border-border rounded-lg shadow-lg py-1 min-w-[160px]">
                  {actions.map((action, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setMenuOpen(false)
                        action.onClick?.()
                      }}
                      className={cn(
                        "w-full px-4 py-3 text-sm text-left flex items-center gap-3 active:bg-bg-tertiary",
                        action.variant === 'danger' && "text-status-error"
                      )}
                    >
                      {action.icon && <action.icon size={18} />}
                      {action.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// DESKTOP PAGINATION
// =============================================================================

function DesktopPagination({ 
  page, 
  totalPages, 
  total, 
  pageSize, 
  pageSizeOptions, 
  onPageChange, 
  onPageSizeChange 
}) {
  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)
  
  return (
    <div className="px-4 py-2 border-t border-border bg-bg-secondary flex items-center justify-between text-sm">
      <div className="flex items-center gap-4">
        <span className="text-text-tertiary">
          Showing {start}-{end} of {total}
        </span>
        
        <div className="flex items-center gap-2">
          <span className="text-text-tertiary">Per page:</span>
          <FilterSelect
            value={String(pageSize)}
            onChange={(val) => onPageSizeChange(Number(val))}
            options={pageSizeOptions.map(size => ({ value: String(size), label: String(size) }))}
            placeholder={String(pageSize)}
            size="sm"
          />
        </div>
      </div>
      
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className={cn(
            "p-1.5 rounded hover:bg-bg-tertiary transition-colors",
            page <= 1 ? "text-text-tertiary cursor-not-allowed" : "text-text-primary"
          )}
        >
          <CaretLeft size={16} />
        </button>
        
        <span className="px-3 text-text-primary">
          {page} / {totalPages}
        </span>
        
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className={cn(
            "p-1.5 rounded hover:bg-bg-tertiary transition-colors",
            page >= totalPages ? "text-text-tertiary cursor-not-allowed" : "text-text-primary"
          )}
        >
          <CaretRight size={16} />
        </button>
      </div>
    </div>
  )
}

// =============================================================================
// MOBILE PAGINATION
// =============================================================================

function MobilePagination({ page, totalPages, total, onChange }) {
  return (
    <div className="px-4 py-3 border-t border-border bg-bg-secondary flex items-center justify-between">
      <span className="text-xs text-text-tertiary">
        Page {page} of {totalPages}
      </span>
      
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className={cn(
            "w-10 h-10 flex items-center justify-center rounded-lg transition-colors",
            page <= 1 
              ? "text-text-tertiary" 
              : "text-text-primary active:bg-bg-tertiary"
          )}
        >
          <CaretLeft size={20} />
        </button>
        
        <button
          type="button"
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
          className={cn(
            "w-10 h-10 flex items-center justify-center rounded-lg transition-colors",
            page >= totalPages 
              ? "text-text-tertiary" 
              : "text-text-primary active:bg-bg-tertiary"
          )}
        >
          <CaretRight size={20} />
        </button>
      </div>
    </div>
  )
}

export default ResponsiveTable
