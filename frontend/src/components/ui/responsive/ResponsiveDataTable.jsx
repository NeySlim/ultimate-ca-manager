/**
 * ResponsiveDataTable - Unified table component
 * 
 * DESKTOP: Dense table with sticky header, hover rows, dropdown actions
 * MOBILE: Card-style rows with primary/secondary info, large touch targets
 */
import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { 
  MagnifyingGlass, CaretUp, CaretDown, DotsThreeVertical,
  CaretLeft, CaretRight, FunnelSimple, X
} from '@phosphor-icons/react'
import { useMobile } from '../../../contexts'
import { cn } from '../../../lib/utils'

export function ResponsiveDataTable({
  // Data
  data = [],
  columns = [],
  
  // Selection
  selectedId,
  onRowClick,
  selectable = true,
  
  // Row actions (dropdown menu)
  rowActions, // (row) => [{ label, icon, onClick, variant }]
  
  // Search
  searchable = false,
  searchPlaceholder = 'Search...',
  searchKeys = [], // keys to search in
  externalSearch, // controlled search
  onSearchChange,
  
  // Sorting
  sortable = false,
  defaultSort, // { key, direction: 'asc' | 'desc' }
  
  // Pagination (external OR auto)
  pagination, // { page, total, perPage, onChange, onPerPageChange } OR true for auto
  defaultPerPage = 25, // default items per page for auto-pagination
  
  // Empty state (individual props OR object)
  emptyIcon: EmptyIconProp,
  emptyTitle: emptyTitleProp = 'No data',
  emptyDescription: emptyDescriptionProp,
  emptyAction: emptyActionProp,
  emptyState, // { icon, title, description, action } - alternative format
  
  // Loading
  loading = false,
  
  // Custom class
  className
}) {
  const { isMobile, isDesktop, isTouch } = useMobile()
  
  // Support both individual props and emptyState object
  const EmptyIcon = emptyState?.icon || EmptyIconProp
  const emptyTitle = emptyState?.title || emptyTitleProp
  const emptyDescription = emptyState?.description || emptyDescriptionProp
  const emptyAction = emptyState?.action || emptyActionProp
  
  // Local search state (if not controlled)
  const [localSearch, setLocalSearch] = useState('')
  const searchValue = externalSearch !== undefined ? externalSearch : localSearch
  const setSearchValue = onSearchChange || setLocalSearch
  
  // Sort state
  const [sort, setSort] = useState(defaultSort || null)
  
  // Row actions dropdown
  const [openActionMenu, setOpenActionMenu] = useState(null)
  const actionMenuRef = useRef(null)
  
  // Close action menu on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (actionMenuRef.current && !actionMenuRef.current.contains(e.target)) {
        setOpenActionMenu(null)
      }
    }
    if (openActionMenu !== null) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [openActionMenu])
  
  // Filter data by search
  const filteredData = useMemo(() => {
    if (!searchValue || searchKeys.length === 0) return data
    
    const query = searchValue.toLowerCase()
    return data.filter(row => 
      searchKeys.some(key => {
        const value = row[key]
        return value && String(value).toLowerCase().includes(query)
      })
    )
  }, [data, searchValue, searchKeys])
  
  // Sort filtered data
  const sortedData = useMemo(() => {
    if (!sort || !sort.key) return filteredData
    
    return [...filteredData].sort((a, b) => {
      const aVal = a[sort.key]
      const bVal = b[sort.key]
      
      if (aVal === bVal) return 0
      if (aVal === null || aVal === undefined) return 1
      if (bVal === null || bVal === undefined) return -1
      
      const comparison = String(aVal).localeCompare(String(bVal), undefined, { numeric: true })
      return sort.direction === 'desc' ? -comparison : comparison
    })
  }, [filteredData, sort])
  
  // ==========================================================================
  // AUTO-PAGINATION: Internal state for client-side pagination
  // ==========================================================================
  const [internalPage, setInternalPage] = useState(1)
  const [internalPerPage, setInternalPerPage] = useState(defaultPerPage)
  
  // Determine if we should use pagination (external, auto, or none)
  const useAutoPagination = pagination === true || (pagination === undefined && sortedData.length > defaultPerPage)
  const useExternalPagination = pagination && typeof pagination === 'object'
  
  // Reset internal page when data changes significantly
  useEffect(() => {
    if (useAutoPagination) {
      const maxPage = Math.ceil(sortedData.length / internalPerPage)
      if (internalPage > maxPage) {
        setInternalPage(Math.max(1, maxPage))
      }
    }
  }, [sortedData.length, internalPerPage, internalPage, useAutoPagination])
  
  // Paginated data (only for auto-pagination)
  const paginatedData = useMemo(() => {
    if (useExternalPagination) {
      // External pagination: assume data is already sliced by parent/API
      return sortedData
    }
    if (useAutoPagination) {
      // Auto pagination: slice locally
      const start = (internalPage - 1) * internalPerPage
      return sortedData.slice(start, start + internalPerPage)
    }
    // No pagination: return all data
    return sortedData
  }, [sortedData, useAutoPagination, useExternalPagination, internalPage, internalPerPage])
  
  // Build pagination props for PaginationBar
  const paginationProps = useMemo(() => {
    if (useExternalPagination) {
      return pagination
    }
    if (useAutoPagination) {
      return {
        page: internalPage,
        total: sortedData.length,
        perPage: internalPerPage,
        onChange: setInternalPage,
        onPerPageChange: (v) => { setInternalPerPage(v); setInternalPage(1) }
      }
    }
    return null
  }, [useExternalPagination, useAutoPagination, pagination, internalPage, internalPerPage, sortedData.length])
  
  // Handle sort click
  const handleSort = useCallback((key) => {
    if (!sortable) return
    
    setSort(prev => {
      if (prev?.key !== key) return { key, direction: 'asc' }
      if (prev.direction === 'asc') return { key, direction: 'desc' }
      return null // Remove sort
    })
  }, [sortable])
  
  // Get visible columns based on device
  const visibleColumns = useMemo(() => {
    if (isDesktop) return columns
    // On mobile, filter columns that have hideOnMobile
    return columns.filter(col => !col.hideOnMobile)
  }, [columns, isDesktop])
  
  // Get primary and secondary columns for mobile cards
  const { primaryCol, secondaryCol, tertiaryCol } = useMemo(() => {
    const sorted = [...columns].sort((a, b) => (a.priority || 99) - (b.priority || 99))
    return {
      primaryCol: sorted[0],
      secondaryCol: sorted[1],
      tertiaryCol: sorted[2]
    }
  }, [columns])
  
  // Empty state
  if (!loading && sortedData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        {EmptyIcon && (
          <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4">
            <EmptyIcon size={32} className="text-text-secondary" />
          </div>
        )}
        <h3 className="text-lg font-medium text-text-primary mb-1">
          {emptyTitle}
        </h3>
        {emptyDescription && (
          <p className="text-sm text-text-secondary text-center max-w-sm mb-4">
            {emptyDescription}
          </p>
        )}
        {emptyAction}
      </div>
    )
  }
  
  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* SEARCH BAR */}
      {searchable && (
        <SearchBar
          value={searchValue}
          onChange={setSearchValue}
          placeholder={searchPlaceholder}
          isMobile={isMobile}
        />
      )}
      
      {/* TABLE / CARDS */}
      {isMobile ? (
        <MobileCardList
          data={paginatedData}
          primaryCol={primaryCol}
          secondaryCol={secondaryCol}
          tertiaryCol={tertiaryCol}
          selectedId={selectedId}
          onRowClick={onRowClick}
          rowActions={rowActions}
          loading={loading}
        />
      ) : (
        <DesktopTable
          data={paginatedData}
          columns={visibleColumns}
          selectedId={selectedId}
          onRowClick={onRowClick}
          rowActions={rowActions}
          sort={sort}
          onSort={handleSort}
          sortable={sortable}
          openActionMenu={openActionMenu}
          setOpenActionMenu={setOpenActionMenu}
          actionMenuRef={actionMenuRef}
          loading={loading}
        />
      )}
      
      {/* PAGINATION */}
      {paginationProps && sortedData.length > 0 && (
        <PaginationBar
          {...paginationProps}
          isMobile={isMobile}
        />
      )}
    </div>
  )
}

// =============================================================================
// SEARCH BAR
// =============================================================================

function SearchBar({ value, onChange, placeholder, isMobile }) {
  return (
    <div className={cn(
      'shrink-0 border-b border-border/50 bg-bg-secondary/30',
      isMobile ? 'px-4 py-3' : 'px-4 py-2.5'
    )}>
      <div className="relative group">
        <MagnifyingGlass 
          size={isMobile ? 20 : 16} 
          className={cn(
            "absolute left-3 top-1/2 -translate-y-1/2",
            "text-text-tertiary group-focus-within:text-accent-primary transition-colors"
          )}
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={cn(
            'w-full rounded-lg border border-border bg-bg-primary',
            'text-text-primary placeholder:text-text-tertiary',
            'transition-all duration-200',
            'focus:outline-none focus:ring-2 focus:ring-accent-primary/30 focus:border-accent-primary',
            'hover:border-border-hover',
            isMobile 
              ? 'h-11 pl-10 pr-4 text-base' 
              : 'h-8 pl-9 pr-3 text-sm'
          )}
        />
        {value && (
          <button
            onClick={() => onChange('')}
            className={cn(
              'absolute right-2 top-1/2 -translate-y-1/2 rounded-md',
              'text-text-tertiary hover:text-text-primary hover:bg-bg-hover',
              'transition-all duration-150',
              isMobile ? 'p-2' : 'p-1'
            )}
          >
            <X size={isMobile ? 18 : 14} weight="bold" />
          </button>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// DESKTOP TABLE
// =============================================================================

function DesktopTable({
  data,
  columns,
  selectedId,
  onRowClick,
  rowActions,
  sort,
  onSort,
  sortable,
  openActionMenu,
  setOpenActionMenu,
  actionMenuRef,
  loading
}) {
  return (
    <div className="flex-1 overflow-auto">
      <table className="w-full text-sm">
        {/* Header */}
        <thead className="sticky top-0 z-10 bg-bg-secondary/95 backdrop-blur-sm border-b border-border shadow-sm">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => sortable && col.sortable !== false && onSort(col.key)}
                className={cn(
                  'text-left px-4 py-2.5 text-xs font-semibold text-text-secondary uppercase tracking-wider',
                  'transition-colors duration-150',
                  sortable && col.sortable !== false && 'cursor-pointer hover:text-text-primary hover:bg-bg-tertiary/50',
                  sort?.key === col.key && 'text-accent-primary',
                  col.width && `w-[${col.width}]`
                )}
              >
                <div className="flex items-center gap-1.5">
                  {col.header || col.label}
                  {sort?.key === col.key && (
                    sort.direction === 'asc' 
                      ? <CaretUp size={12} weight="bold" className="text-accent-primary" />
                      : <CaretDown size={12} weight="bold" className="text-accent-primary" />
                  )}
                </div>
              </th>
            ))}
            {rowActions && <th className="w-12" />}
          </tr>
        </thead>
        
        {/* Body */}
        <tbody className="divide-y divide-border/50">
          {loading ? (
            <tr>
              <td colSpan={columns.length + (rowActions ? 1 : 0)} className="py-12 text-center">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-8 h-8 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
                  <span className="text-xs text-text-secondary">Loading...</span>
                </div>
              </td>
            </tr>
          ) : (
            data.map((row, idx) => (
              <tr
                key={row.id || idx}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  'group transition-all duration-150 table-row-hover',
                  onRowClick && 'cursor-pointer',
                  // Selected state - uses theme-aware CSS class
                  selectedId === row.id && 'row-selected'
                )}>
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 transition-colors">
                    {col.render 
                      ? col.render(row[col.key], row)
                      : row[col.key] ?? '—'
                    }
                  </td>
                ))}
                {rowActions && (
                  <td className="px-2 py-2.5 relative">
                    <RowActionMenu
                      row={row}
                      idx={idx}
                      actions={rowActions(row)}
                      isOpen={openActionMenu === idx}
                      onToggle={() => setOpenActionMenu(openActionMenu === idx ? null : idx)}
                      menuRef={openActionMenu === idx ? actionMenuRef : null}
                    />
                  </td>
                )}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// =============================================================================
// ROW ACTION MENU (Desktop)
// =============================================================================

function RowActionMenu({ row, idx, actions, isOpen, onToggle, menuRef }) {
  if (!actions || actions.length === 0) return null
  
  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
        className={cn(
          'w-8 h-8 rounded-lg flex items-center justify-center',
          'text-text-tertiary opacity-0 group-hover:opacity-100',
          'hover:bg-bg-tertiary hover:text-text-primary',
          'transition-all duration-150',
          isOpen && 'opacity-100 bg-accent-primary/10 text-accent-primary'
        )}
      >
        <DotsThreeVertical size={18} weight="bold" />
      </button>
      
      {isOpen && (
        <div className={cn(
          'absolute right-0 top-full mt-1 z-20',
          'min-w-[180px] py-1.5 rounded-xl border border-border bg-bg-primary',
          'shadow-xl shadow-black/10',
          'animate-fade-in'
        )}>
          {actions.map((action, i) => {
            const Icon = action.icon
            return (
              <button
                key={i}
                onClick={(e) => {
                  e.stopPropagation()
                  action.onClick?.()
                  onToggle()
                }}
                className={cn(
                  'w-full flex items-center gap-2.5 px-3 py-2 text-sm',
                  'transition-all duration-150',
                  action.variant === 'danger'
                    ? 'status-danger-text hover:status-danger-bg'
                    : 'text-text-primary hover:bg-accent-primary/5 hover:text-accent-primary'
                )}
              >
                {Icon && <Icon size={16} weight="duotone" />}
                {action.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// MOBILE CARD LIST
// =============================================================================

function MobileCardList({
  data,
  primaryCol,
  secondaryCol,
  tertiaryCol,
  selectedId,
  onRowClick,
  rowActions,
  loading
}) {
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center py-12">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-3 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
          <span className="text-sm text-text-secondary">Loading...</span>
        </div>
      </div>
    )
  }
  
  return (
    <div className="flex-1 overflow-auto">
      <div className="divide-y divide-border/50">
        {data.map((row, idx) => (
          <MobileCardRow
            key={row.id || idx}
            row={row}
            primaryCol={primaryCol}
            secondaryCol={secondaryCol}
            tertiaryCol={tertiaryCol}
            isSelected={selectedId === row.id}
            onClick={() => onRowClick?.(row)}
            actions={rowActions?.(row)}
          />
        ))}
      </div>
    </div>
  )
}

function MobileCardRow({
  row,
  primaryCol,
  secondaryCol,
  tertiaryCol,
  isSelected,
  onClick,
  actions
}) {
  const [showActions, setShowActions] = useState(false)
  
  return (
    <div
      onClick={onClick}
      className={cn(
        'px-4 py-3.5 transition-all duration-150',
        'active:bg-bg-tertiary active:scale-[0.99]',
        // Selected state - uses theme color via CSS
        isSelected && 'mobile-row-selected'
      )}
    >
      <div className="flex items-start gap-3">
        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Primary */}
          {primaryCol && (
            <div className={cn(
              "font-medium truncate transition-colors",
              isSelected ? "text-accent-primary" : "text-text-primary"
            )}>
              {primaryCol.render 
                ? primaryCol.render(row[primaryCol.key], row)
                : row[primaryCol.key]
              }
            </div>
          )}
          
          {/* Secondary */}
          {secondaryCol && (
            <div className="text-sm text-text-secondary mt-0.5">
              {secondaryCol.render 
                ? secondaryCol.render(row[secondaryCol.key], row)
                : row[secondaryCol.key]
              }
            </div>
          )}
          
          {/* Tertiary (badge/status) */}
          {tertiaryCol && (
            <div className="mt-1.5">
              {tertiaryCol.render 
                ? tertiaryCol.render(row[tertiaryCol.key], row)
                : row[tertiaryCol.key]
              }
            </div>
          )}
        </div>
        
        {/* Action button */}
        {actions && actions.length > 0 && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setShowActions(!showActions)
            }}
            className={cn(
              'w-11 h-11 shrink-0 rounded-lg flex items-center justify-center',
              'text-text-secondary hover:bg-bg-tertiary active:bg-bg-hover'
            )}
          >
            <DotsThreeVertical size={22} weight="bold" />
          </button>
        )}
      </div>
      
      {/* Expanded actions */}
      {showActions && actions && (
        <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-2">
          {actions.map((action, i) => {
            const Icon = action.icon
            return (
              <button
                key={i}
                onClick={(e) => {
                  e.stopPropagation()
                  action.onClick?.()
                  setShowActions(false)
                }}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
                  'border border-border transition-colors',
                  action.variant === 'danger'
                    ? 'status-danger-text hover:status-danger-bg'
                    : 'text-text-primary hover:bg-bg-tertiary'
                )}
              >
                {Icon && <Icon size={16} />}
                {action.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// PAGINATION BAR
// =============================================================================

function PaginationBar({ page, total, perPage, onChange, onPerPageChange, isMobile }) {
  const totalPages = Math.ceil(total / perPage)
  const start = (page - 1) * perPage + 1
  const end = Math.min(page * perPage, total)
  
  return (
    <div className={cn(
      'shrink-0 border-t border-border bg-bg-secondary/30',
      'flex items-center justify-between',
      isMobile ? 'px-4 py-3' : 'px-4 py-2'
    )}>
      {/* Info */}
      <p className={cn(
        'text-text-secondary font-medium',
        isMobile ? 'text-sm' : 'text-xs'
      )}>
        <span className="text-text-primary">{start}-{end}</span> of <span className="text-text-primary">{total}</span>
      </p>
      
      {/* Controls */}
      <div className={cn(
        'flex items-center',
        isMobile ? 'gap-2' : 'gap-1.5'
      )}>
        {/* Per page selector (desktop only) */}
        {!isMobile && onPerPageChange && (
          <select
            value={perPage}
            onChange={(e) => onPerPageChange(Number(e.target.value))}
            className={cn(
              'h-7 px-2 pr-6 rounded-md border border-border bg-bg-primary',
              'text-xs text-text-primary cursor-pointer',
              'focus:outline-none focus:ring-1 focus:ring-accent-primary',
              'hover:border-accent-primary/50 transition-colors'
            )}
          >
            {[10, 25, 50, 100].map(n => (
              <option key={n} value={n}>{n}/page</option>
            ))}
          </select>
        )}
        
        {/* Prev button */}
        <button
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className={cn(
            'rounded-lg flex items-center justify-center',
            'border border-border bg-bg-primary',
            'transition-all duration-150',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'enabled:hover:bg-accent-primary/5 enabled:hover:border-accent-primary/50 enabled:hover:text-accent-primary',
            'enabled:active:scale-95',
            isMobile ? 'w-11 h-11' : 'w-8 h-8'
          )}
        >
          <CaretLeft size={isMobile ? 20 : 16} weight="bold" />
        </button>
        
        {/* Page indicator */}
        <span className={cn(
          'px-3 py-1 rounded-md bg-bg-tertiary/50 text-text-primary font-medium',
          isMobile ? 'text-sm' : 'text-xs'
        )}>
          <span className="text-accent-primary">{page}</span>
          <span className="text-text-tertiary mx-0.5">/</span>
          {totalPages}
        </span>
        
        {/* Next button */}
        <button
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
          className={cn(
            'rounded-lg flex items-center justify-center',
            'border border-border bg-bg-primary',
            'transition-all duration-150',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'enabled:hover:bg-accent-primary/5 enabled:hover:border-accent-primary/50 enabled:hover:text-accent-primary',
            'enabled:active:scale-95',
            isMobile ? 'w-11 h-11' : 'w-8 h-8'
          )}
        >
          <CaretRight size={isMobile ? 20 : 16} weight="bold" />
        </button>
      </div>
    </div>
  )
}

export default ResponsiveDataTable
