/**
 * DataTable - Powerful table system with pagination, filters, column management
 * 
 * Features:
 * - Pagination with configurable page sizes
 * - Search/filter with dropdown filters
 * - Column visibility toggle
 * - Sortable columns
 * - Row selection (single/multi)
 * - Hierarchical/tree display
 * - Responsive (cards on mobile)
 * - Theme-aware styling
 * - Multiple variants (default, compact, striped)
 */
import { useState, useMemo, useEffect } from 'react'
import { cn } from '../lib/utils'
import { 
  MagnifyingGlass, CaretUp, CaretDown, CaretLeft, CaretRight,
  Columns, Funnel, Check, X, DotsThree, ArrowsDownUp,
  CaretDoubleLeft, CaretDoubleRight, CaretRight as ChevronRight
} from '@phosphor-icons/react'
import { useMobile } from '../contexts'
import { Button } from './Button'
import { Badge } from './Badge'

// ============================================
// DataTable - Main component
// ============================================
export function DataTable({
  // Data
  data = [],
  columns = [],
  
  // Selection
  selectable = false,
  multiSelect = false,
  selectedRows = [],
  onSelectionChange,
  
  // Pagination
  paginated = true,
  pageSize: initialPageSize = 10,
  pageSizeOptions = [10, 25, 50, 100],
  
  // Search
  searchable = true,
  searchPlaceholder = "Search...",
  searchKeys = [], // Which columns to search in (empty = all)
  
  // Filters
  filters = [], // [{ key: 'status', label: 'Status', options: [{value, label}] }]
  
  // Sorting
  sortable = true,
  defaultSort = null, // { key: 'name', direction: 'asc' }
  
  // Column management
  columnToggle = true,
  
  // Tree/hierarchy display
  hierarchical = false,   // Enable tree view
  parentKey = 'parent_id', // Key for parent reference
  childrenKey = 'children', // Key for nested children (if pre-built)
  expandedRows = null,     // Controlled expanded state
  defaultExpanded = true,  // Expand all by default
  indentWidth = 24,        // Pixels per level
  
  // Styling
  variant = 'default', // default, compact, striped
  stickyHeader = true,
  
  // Row actions
  onRowClick,
  rowActions, // (row) => [{ label, icon, onClick }]
  
  // Empty state
  emptyIcon,
  emptyTitle = "No data",
  emptyDescription = "No items to display",
  emptyAction,
  
  // Loading
  loading = false,
  
  // Custom render
  rowClassName,
  
  className
}) {
  const { isMobile } = useMobile()
  
  // State
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(initialPageSize)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortConfig, setSortConfig] = useState(defaultSort)
  const [visibleColumns, setVisibleColumns] = useState(
    columns.filter(c => c.visible !== false).map(c => c.key)
  )
  const [showColumnMenu, setShowColumnMenu] = useState(false)
  const [showFiltersMenu, setShowFiltersMenu] = useState(false)
  const [internalSelection, setInternalSelection] = useState(selectedRows)
  const [activeFilters, setActiveFilters] = useState({}) // { status: 'active', type: 'root' }
  const [internalExpanded, setInternalExpanded] = useState(
    expandedRows !== null ? expandedRows : (defaultExpanded ? 'all' : new Set())
  )
  
  // Sync selection with prop
  useEffect(() => {
    setInternalSelection(selectedRows)
  }, [selectedRows])
  
  // Build tree structure if hierarchical
  const treeData = useMemo(() => {
    if (!hierarchical) return null
    
    // If data already has children, use it directly
    if (data.some(item => item[childrenKey]?.length > 0)) {
      return data.filter(item => !item[parentKey])
    }
    
    // Build tree from flat data
    const idMap = new Map()
    const roots = []
    
    // First pass: create map
    data.forEach(item => {
      idMap.set(item.id, { ...item, _children: [], _level: 0 })
    })
    
    // Second pass: build tree
    data.forEach(item => {
      const node = idMap.get(item.id)
      const parentId = item[parentKey]
      
      if (parentId && idMap.has(parentId)) {
        const parent = idMap.get(parentId)
        parent._children.push(node)
        node._level = parent._level + 1
        node._parent = parent
      } else {
        roots.push(node)
      }
    })
    
    return roots
  }, [data, hierarchical, parentKey, childrenKey])
  
  // Flatten tree for display (respects expansion)
  const flattenedTreeData = useMemo(() => {
    if (!hierarchical || !treeData) return null
    
    const result = []
    
    // Sort function for nodes at same level
    const sortNodes = (nodes) => {
      return [...nodes].sort((a, b) => {
        // Roots first (type = root), then intermediates
        if (a.type !== b.type) {
          return a.type === 'root' ? -1 : 1
        }
        // Then by name
        const aName = a.name || a.descr || ''
        const bName = b.name || b.descr || ''
        return aName.localeCompare(bName)
      })
    }
    
    const traverse = (nodes, level = 0) => {
      const sorted = sortNodes(nodes)
      sorted.forEach(node => {
        const nodeWithLevel = { ...node, _level: level, _hasChildren: node._children?.length > 0 }
        result.push(nodeWithLevel)
        
        const isExpanded = internalExpanded === 'all' || internalExpanded.has?.(node.id)
        if (isExpanded && node._children?.length > 0) {
          traverse(node._children, level + 1)
        }
      })
    }
    
    traverse(treeData)
    return result
  }, [treeData, hierarchical, internalExpanded])
  
  // Use flattened tree or regular data
  const baseData = hierarchical && flattenedTreeData ? flattenedTreeData : data
  
  // Filter data by search and active filters
  const filteredData = useMemo(() => {
    let result = baseData
    
    // Apply search
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      const keysToSearch = searchKeys.length > 0 
        ? searchKeys 
        : columns.map(c => c.key)
      
      result = result.filter(row => 
        keysToSearch.some(key => {
          const value = row[key]
          if (value == null) return false
          return String(value).toLowerCase().includes(query)
        })
      )
    }
    
    // Apply dropdown filters
    if (Object.keys(activeFilters).length > 0) {
      result = result.filter(row => {
        return Object.entries(activeFilters).every(([key, value]) => {
          if (value === '' || value === 'all') return true
          // Handle boolean comparisons (select converts to string)
          const rowValue = row[key]
          if (typeof rowValue === 'boolean') {
            return String(rowValue) === String(value)
          }
          return rowValue === value
        })
      })
    }
    
    return result
  }, [baseData, searchQuery, searchKeys, columns, activeFilters])
  
  // Sort data (disabled for hierarchical mode - tree order takes precedence)
  const sortedData = useMemo(() => {
    // In hierarchical mode, don't sort globally (tree structure defines order)
    if (hierarchical) return filteredData
    
    if (!sortConfig) return filteredData
    
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]
      
      if (aVal == null) return 1
      if (bVal == null) return -1
      
      const column = columns.find(c => c.key === sortConfig.key)
      const sortType = column?.sortType || 'string'
      
      let comparison = 0
      if (sortType === 'number') {
        comparison = Number(aVal) - Number(bVal)
      } else if (sortType === 'date') {
        comparison = new Date(aVal) - new Date(bVal)
      } else {
        comparison = String(aVal).localeCompare(String(bVal))
      }
      
      return sortConfig.direction === 'desc' ? -comparison : comparison
    })
  }, [filteredData, sortConfig, columns, hierarchical])
  
  // Paginate data
  const paginatedData = useMemo(() => {
    if (!paginated) return sortedData
    
    const start = (currentPage - 1) * pageSize
    return sortedData.slice(start, start + pageSize)
  }, [sortedData, currentPage, pageSize, paginated])
  
  const totalPages = Math.ceil(sortedData.length / pageSize)
  
  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1)
  }, [searchQuery, pageSize, activeFilters])
  
  // Handle filter change
  const handleFilterChange = (key, value) => {
    setActiveFilters(prev => ({
      ...prev,
      [key]: value
    }))
  }
  
  // Handle expand/collapse for tree
  const toggleExpand = (rowId) => {
    setInternalExpanded(prev => {
      if (prev === 'all') {
        // First collapse: expand all except this one
        const newSet = new Set(flattenedTreeData.filter(r => r._hasChildren).map(r => r.id))
        newSet.delete(rowId)
        return newSet
      }
      const newSet = new Set(prev)
      if (newSet.has(rowId)) {
        newSet.delete(rowId)
      } else {
        newSet.add(rowId)
      }
      return newSet
    })
  }
  
  // Handlers
  const handleSort = (key) => {
    if (!sortable) return
    
    const column = columns.find(c => c.key === key)
    if (column?.sortable === false) return
    
    setSortConfig(prev => {
      if (prev?.key === key) {
        if (prev.direction === 'asc') return { key, direction: 'desc' }
        if (prev.direction === 'desc') return null
      }
      return { key, direction: 'asc' }
    })
  }
  
  const handleRowSelect = (row) => {
    if (!selectable) return
    
    let newSelection
    if (multiSelect) {
      const isSelected = internalSelection.some(r => r.id === row.id)
      newSelection = isSelected
        ? internalSelection.filter(r => r.id !== row.id)
        : [...internalSelection, row]
    } else {
      newSelection = [row]
    }
    
    setInternalSelection(newSelection)
    onSelectionChange?.(newSelection)
  }
  
  const handleSelectAll = () => {
    if (!multiSelect) return
    
    const allSelected = paginatedData.every(row => 
      internalSelection.some(r => r.id === row.id)
    )
    
    let newSelection
    if (allSelected) {
      newSelection = internalSelection.filter(r => 
        !paginatedData.some(pr => pr.id === r.id)
      )
    } else {
      newSelection = [
        ...internalSelection.filter(r => !paginatedData.some(pr => pr.id === r.id)),
        ...paginatedData
      ]
    }
    
    setInternalSelection(newSelection)
    onSelectionChange?.(newSelection)
  }
  
  const toggleColumn = (key) => {
    setVisibleColumns(prev => 
      prev.includes(key) 
        ? prev.filter(k => k !== key)
        : [...prev, key]
    )
  }
  
  // Get visible columns
  const displayColumns = columns.filter(c => visibleColumns.includes(c.key))
  
  // Variant styles
  const variantStyles = {
    default: {
      header: 'bg-bg-secondary',
      row: 'hover:bg-bg-tertiary/50',
      cell: 'py-2 px-3 text-sm',
    },
    compact: {
      header: 'bg-bg-secondary',
      row: 'hover:bg-bg-tertiary/50',
      cell: 'py-1.5 px-3 text-sm',
    },
    striped: {
      header: 'bg-bg-secondary',
      row: 'even:bg-bg-tertiary/30 hover:bg-bg-tertiary/50',
      cell: 'py-2 px-3 text-sm',
    }
  }
  
  const styles = variantStyles[variant]
  
  // Mobile card view
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full", className)}>
        {/* Mobile toolbar */}
        <MobileToolbar
          searchable={searchable}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={searchPlaceholder}
          columnToggle={columnToggle}
          columns={columns}
          visibleColumns={visibleColumns}
          onToggleColumn={toggleColumn}
        />
        
        {/* Cards list */}
        <div className="flex-1 overflow-auto p-3 space-y-2">
          {loading ? (
            <LoadingState />
          ) : paginatedData.length === 0 ? (
            <EmptyState 
              icon={emptyIcon}
              title={emptyTitle}
              description={emptyDescription}
              action={emptyAction}
            />
          ) : (
            paginatedData.map((row, idx) => (
              <MobileCard
                key={row.id || idx}
                row={row}
                columns={displayColumns}
                selected={internalSelection.some(r => r.id === row.id)}
                selectable={selectable}
                onSelect={() => handleRowSelect(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                actions={rowActions?.(row)}
              />
            ))
          )}
        </div>
        
        {/* Mobile pagination */}
        {paginated && totalPages > 1 && (
          <MobilePagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={setCurrentPage}
          />
        )}
      </div>
    )
  }
  
  // Desktop table view
  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Toolbar */}
      <TableToolbar
        searchable={searchable}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={searchPlaceholder}
        columnToggle={columnToggle}
        columns={columns}
        visibleColumns={visibleColumns}
        onToggleColumn={toggleColumn}
        showColumnMenu={showColumnMenu}
        setShowColumnMenu={setShowColumnMenu}
        selectedCount={internalSelection.length}
        filters={filters}
        activeFilters={activeFilters}
        onFilterChange={handleFilterChange}
        showFiltersMenu={showFiltersMenu}
        setShowFiltersMenu={setShowFiltersMenu}
      />
      
      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead className={cn(
            styles.header,
            stickyHeader && "sticky top-0 z-10"
          )}>
            <tr className="border-b border-border">
              {selectable && (
                <th className="w-10 px-3 py-3">
                  {multiSelect && (
                    <input
                      type="checkbox"
                      checked={paginatedData.length > 0 && paginatedData.every(row => 
                        internalSelection.some(r => r.id === row.id)
                      )}
                      onChange={handleSelectAll}
                      className="w-4 h-4 rounded border-border bg-bg-primary accent-accent-primary"
                    />
                  )}
                </th>
              )}
              {displayColumns.map(column => (
                <th
                  key={column.key}
                  className={cn(
                    "text-left text-xs font-semibold text-text-secondary uppercase tracking-wider",
                    styles.cell,
                    sortable && column.sortable !== false && "cursor-pointer select-none hover:text-text-primary",
                    column.width && `w-[${column.width}]`,
                    column.align === 'center' && 'text-center',
                    column.align === 'right' && 'text-right'
                  )}
                  onClick={() => handleSort(column.key)}
                >
                  <div className={cn(
                    "flex items-center gap-1.5",
                    column.align === 'center' && 'justify-center',
                    column.align === 'right' && 'justify-end'
                  )}>
                    {column.header || column.key}
                    {sortable && column.sortable !== false && (
                      <SortIndicator 
                        active={sortConfig?.key === column.key}
                        direction={sortConfig?.key === column.key ? sortConfig.direction : null}
                      />
                    )}
                  </div>
                </th>
              ))}
              {rowActions && <th className="w-12"></th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={displayColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0)}>
                  <LoadingState />
                </td>
              </tr>
            ) : paginatedData.length === 0 ? (
              <tr>
                <td colSpan={displayColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0)}>
                  <EmptyState 
                    icon={emptyIcon}
                    title={emptyTitle}
                    description={emptyDescription}
                    action={emptyAction}
                  />
                </td>
              </tr>
            ) : (
              paginatedData.map((row, idx) => {
                const isSelected = internalSelection.some(r => r.id === row.id)
                const level = hierarchical ? (row._level || 0) : 0
                const hasChildren = hierarchical && row._hasChildren
                const isExpanded = internalExpanded === 'all' || internalExpanded.has?.(row.id)
                
                return (
                  <tr
                    key={row.id || idx}
                    className={cn(
                      "border-b border-border/50 transition-colors",
                      styles.row,
                      isSelected && "bg-accent-primary/10",
                      onRowClick && "cursor-pointer",
                      typeof rowClassName === 'function' ? rowClassName(row) : rowClassName
                    )}
                    onClick={() => {
                      if (selectable && !onRowClick) handleRowSelect(row)
                      onRowClick?.(row)
                    }}
                  >
                    {selectable && (
                      <td className="w-10 px-3" onClick={e => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => handleRowSelect(row)}
                          className="w-4 h-4 rounded border-border bg-bg-primary accent-accent-primary"
                        />
                      </td>
                    )}
                    {displayColumns.map((column, colIdx) => (
                      <td
                        key={column.key}
                        className={cn(
                          "text-text-primary",
                          styles.cell,
                          column.align === 'center' && 'text-center',
                          column.align === 'right' && 'text-right'
                        )}
                      >
                        {/* First column gets tree indentation */}
                        {hierarchical && colIdx === 0 ? (
                          <div className="flex items-center" style={{ paddingLeft: level * indentWidth }}>
                            {hasChildren ? (
                              <button
                                onClick={(e) => { e.stopPropagation(); toggleExpand(row.id) }}
                                className="p-0.5 mr-1 rounded hover:bg-bg-tertiary text-text-secondary"
                              >
                                <ChevronRight 
                                  size={14} 
                                  className={cn(
                                    "transition-transform duration-150",
                                    isExpanded && "rotate-90"
                                  )}
                                />
                              </button>
                            ) : (
                              <span className="w-5 mr-1" /> // Spacer for alignment
                            )}
                            {column.render 
                              ? column.render(row[column.key], row)
                              : row[column.key]
                            }
                          </div>
                        ) : (
                          column.render 
                            ? column.render(row[column.key], row)
                            : row[column.key]
                        )}
                      </td>
                    ))}
                    {rowActions && (
                      <td className="w-12 px-2" onClick={e => e.stopPropagation()}>
                        <RowActionsMenu actions={rowActions(row)} />
                      </td>
                    )}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
      
      {/* Pagination */}
      {paginated && (
        <TablePagination
          currentPage={currentPage}
          totalPages={totalPages}
          pageSize={pageSize}
          pageSizeOptions={pageSizeOptions}
          totalItems={sortedData.length}
          onPageChange={setCurrentPage}
          onPageSizeChange={setPageSize}
        />
      )}
    </div>
  )
}

// ============================================
// Sub-components
// ============================================

function TableToolbar({
  searchable,
  searchQuery,
  onSearchChange,
  searchPlaceholder,
  columnToggle,
  columns,
  visibleColumns,
  onToggleColumn,
  showColumnMenu,
  setShowColumnMenu,
  selectedCount,
  filters = [],
  activeFilters = {},
  onFilterChange,
  showFiltersMenu,
  setShowFiltersMenu
}) {
  const activeFilterCount = Object.values(activeFilters).filter(v => v && v !== 'all').length
  
  return (
    <div className="flex items-center justify-between gap-4 p-3 border-b border-border bg-bg-secondary/50">
      <div className="flex items-center gap-3 flex-1">
        {/* Search */}
        {searchable && (
          <div className="relative flex-1 max-w-sm">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
            <input
              type="text"
              placeholder={searchPlaceholder}
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-bg-tertiary border border-border rounded-lg 
                focus:outline-none focus:border-accent-primary text-text-primary placeholder:text-text-tertiary"
            />
            {searchQuery && (
              <button
                onClick={() => onSearchChange('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-bg-primary rounded"
              >
                <X size={14} className="text-text-tertiary" />
              </button>
            )}
          </div>
        )}
        
        {/* Filter dropdowns */}
        {filters.length > 0 && (
          <div className="flex items-center gap-2">
            {filters.map(filter => (
              <select
                key={filter.key}
                value={activeFilters[filter.key] || 'all'}
                onChange={(e) => onFilterChange(filter.key, e.target.value)}
                className="bg-bg-tertiary border border-border rounded-lg px-2.5 py-1.5 text-sm text-text-primary 
                  focus:outline-none focus:border-accent-primary cursor-pointer"
              >
                <option value="all">{filter.label}: All</option>
                {filter.options.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            ))}
            {activeFilterCount > 0 && (
              <button
                onClick={() => filters.forEach(f => onFilterChange(f.key, 'all'))}
                className="text-xs text-accent-primary hover:text-accent-primary/80 px-2"
              >
                Clear filters
              </button>
            )}
          </div>
        )}
        
        {/* Selection count */}
        {selectedCount > 0 && (
          <Badge variant="primary">
            {selectedCount} selected
          </Badge>
        )}
      </div>
      
      <div className="flex items-center gap-2">
        {/* Column toggle */}
        {columnToggle && (
          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowColumnMenu(!showColumnMenu)}
              className="gap-1.5"
            >
              <Columns size={16} />
              Columns
            </Button>
            
            {showColumnMenu && (
              <>
                <div 
                  className="fixed inset-0 z-40" 
                  onClick={() => setShowColumnMenu(false)} 
                />
                <div className="absolute right-0 top-full mt-1 w-48 bg-bg-secondary border border-border rounded-lg shadow-xl z-50 py-1">
                  {columns.map(column => (
                    <button
                      key={column.key}
                      onClick={() => onToggleColumn(column.key)}
                      className="w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-bg-tertiary"
                    >
                      <div className={cn(
                        "w-4 h-4 rounded border flex items-center justify-center",
                        visibleColumns.includes(column.key)
                          ? "bg-accent-primary border-accent-primary"
                          : "border-border"
                      )}>
                        {visibleColumns.includes(column.key) && (
                          <Check size={12} className="text-white" weight="bold" />
                        )}
                      </div>
                      {column.header || column.key}
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

function TablePagination({
  currentPage,
  totalPages,
  pageSize,
  pageSizeOptions,
  totalItems,
  onPageChange,
  onPageSizeChange
}) {
  const startItem = (currentPage - 1) * pageSize + 1
  const endItem = Math.min(currentPage * pageSize, totalItems)
  
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 border-t border-border bg-bg-secondary/50">
      {/* Items info */}
      <div className="text-sm text-text-secondary">
        Showing <span className="font-medium text-text-primary">{startItem}</span> to{' '}
        <span className="font-medium text-text-primary">{endItem}</span> of{' '}
        <span className="font-medium text-text-primary">{totalItems}</span> results
      </div>
      
      {/* Page size selector */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-text-secondary">Rows:</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="bg-bg-tertiary border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-accent-primary"
        >
          {pageSizeOptions.map(size => (
            <option key={size} value={size}>{size}</option>
          ))}
        </select>
      </div>
      
      {/* Page navigation */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(1)}
          disabled={currentPage === 1}
          className="p-1.5 rounded hover:bg-bg-tertiary disabled:opacity-30 disabled:cursor-not-allowed text-text-secondary hover:text-text-primary"
        >
          <CaretDoubleLeft size={16} />
        </button>
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
          className="p-1.5 rounded hover:bg-bg-tertiary disabled:opacity-30 disabled:cursor-not-allowed text-text-secondary hover:text-text-primary"
        >
          <CaretLeft size={16} />
        </button>
        
        <div className="flex items-center gap-1 mx-2">
          {generatePageNumbers(currentPage, totalPages).map((page, idx) => (
            page === '...' ? (
              <span key={`ellipsis-${idx}`} className="px-2 text-text-tertiary">...</span>
            ) : (
              <button
                key={page}
                onClick={() => onPageChange(page)}
                className={cn(
                  "w-8 h-8 rounded text-sm font-medium transition-colors",
                  page === currentPage
                    ? "bg-accent-primary text-white"
                    : "hover:bg-bg-tertiary text-text-secondary hover:text-text-primary"
                )}
              >
                {page}
              </button>
            )
          ))}
        </div>
        
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
          className="p-1.5 rounded hover:bg-bg-tertiary disabled:opacity-30 disabled:cursor-not-allowed text-text-secondary hover:text-text-primary"
        >
          <CaretRight size={16} />
        </button>
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage === totalPages}
          className="p-1.5 rounded hover:bg-bg-tertiary disabled:opacity-30 disabled:cursor-not-allowed text-text-secondary hover:text-text-primary"
        >
          <CaretDoubleRight size={16} />
        </button>
      </div>
    </div>
  )
}

function SortIndicator({ active, direction }) {
  return (
    <span className={cn(
      "flex flex-col",
      !active && "opacity-30"
    )}>
      <CaretUp 
        size={10} 
        weight="bold"
        className={cn(
          "-mb-0.5",
          active && direction === 'asc' ? "text-accent-primary" : "text-text-tertiary"
        )} 
      />
      <CaretDown 
        size={10} 
        weight="bold"
        className={cn(
          active && direction === 'desc' ? "text-accent-primary" : "text-text-tertiary"
        )} 
      />
    </span>
  )
}

function RowActionsMenu({ actions }) {
  const [open, setOpen] = useState(false)
  
  if (!actions || actions.length === 0) return null
  
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="p-1.5 rounded hover:bg-bg-tertiary text-text-secondary hover:text-text-primary"
      >
        <DotsThree size={18} weight="bold" />
      </button>
      
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 w-40 bg-bg-secondary border border-border rounded-lg shadow-xl z-50 py-1">
            {actions.map((action, idx) => (
              <button
                key={idx}
                onClick={() => { setOpen(false); action.onClick?.() }}
                disabled={action.disabled}
                className={cn(
                  "w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-bg-tertiary transition-colors",
                  action.variant === 'danger' && "text-red-500 hover:bg-red-500/10",
                  action.disabled && "opacity-50 cursor-not-allowed"
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
  )
}

// Mobile components
function MobileToolbar({ searchable, searchQuery, onSearchChange, searchPlaceholder, columnToggle, columns, visibleColumns, onToggleColumn }) {
  // Don't show column toggle on mobile by default - cards show all data
  // Column toggle is mainly useful for table views on desktop
  
  return (
    <div className="p-3 border-b border-border bg-bg-secondary/50">
      {searchable && (
        <div className="relative">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm bg-bg-tertiary border border-border rounded-lg 
              focus:outline-none focus:border-accent-primary text-text-primary placeholder:text-text-tertiary"
          />
        </div>
      )}
    </div>
  )
}

function MobileCard({ row, columns, selected, selectable, onSelect, onClick, actions }) {
  return (
    <div 
      className={cn(
        "p-3 rounded-lg border transition-colors",
        selected ? "bg-accent-primary/10 border-accent-primary/30" : "bg-bg-secondary border-border",
        onClick && "cursor-pointer active:scale-[0.99]"
      )}
      onClick={onClick}
    >
      <div className="space-y-2">
        {columns.slice(0, 4).map(col => (
          <div key={col.key} className="flex justify-between items-start gap-2">
            <span className="text-xs text-text-tertiary uppercase">{col.header || col.key}</span>
            <span className="text-sm text-text-primary text-right">
              {col.render ? col.render(row[col.key], row) : row[col.key]}
            </span>
          </div>
        ))}
      </div>
      
      {(selectable || actions) && (
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/50">
          {selectable && (
            <button 
              onClick={(e) => { e.stopPropagation(); onSelect() }}
              className={cn(
                "px-3 py-1 rounded text-xs font-medium",
                selected ? "bg-accent-primary text-white" : "bg-bg-tertiary text-text-secondary"
              )}
            >
              {selected ? 'Selected' : 'Select'}
            </button>
          )}
          {actions && <RowActionsMenu actions={actions} />}
        </div>
      )}
    </div>
  )
}

function MobilePagination({ currentPage, totalPages, onPageChange }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-bg-secondary/50">
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-bg-tertiary text-sm text-text-secondary disabled:opacity-30"
      >
        <CaretLeft size={14} /> Prev
      </button>
      
      <span className="text-sm text-text-secondary">
        {currentPage} / {totalPages}
      </span>
      
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-bg-tertiary text-sm text-text-secondary disabled:opacity-30"
      >
        Next <CaretRight size={14} />
      </button>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent-primary border-t-transparent" />
    </div>
  )
}

function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {Icon && (
        <div className="w-16 h-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
          <Icon size={32} className="text-text-tertiary" />
        </div>
      )}
      <h3 className="text-lg font-medium text-text-primary mb-1">{title}</h3>
      <p className="text-sm text-text-secondary mb-4">{description}</p>
      {action}
    </div>
  )
}

// Helper
function generatePageNumbers(current, total) {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  
  if (current <= 3) {
    return [1, 2, 3, 4, 5, '...', total]
  }
  
  if (current >= total - 2) {
    return [1, '...', total - 4, total - 3, total - 2, total - 1, total]
  }
  
  return [1, '...', current - 1, current, current + 1, '...', total]
}

// ============================================
// SimpleTable - Lightweight table without features
// ============================================
export function SimpleTable({ 
  data = [], 
  columns = [], 
  onRowClick,
  className,
  variant = 'default'
}) {
  const styles = {
    default: { cell: 'py-2 px-3 text-sm' },
    compact: { cell: 'py-1.5 px-3 text-sm' },
  }
  
  return (
    <table className={cn("w-full border-collapse", className)}>
      <thead className="bg-bg-secondary">
        <tr className="border-b border-border">
          {columns.map(col => (
            <th 
              key={col.key}
              className={cn(
                "text-left text-xs font-semibold text-text-secondary uppercase tracking-wider",
                styles[variant].cell
              )}
            >
              {col.header || col.key}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, idx) => (
          <tr 
            key={row.id || idx}
            onClick={() => onRowClick?.(row)}
            className={cn(
              "border-b border-border/50 hover:bg-bg-tertiary/50 transition-colors",
              onRowClick && "cursor-pointer"
            )}
          >
            {columns.map(col => (
              <td key={col.key} className={cn("text-text-primary", styles[variant].cell)}>
                {col.render ? col.render(row[col.key], row) : row[col.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ============================================
// CardGrid - Alternative to table
// ============================================
export function CardGrid({
  data = [],
  renderCard,
  columns = 3,
  gap = 4,
  className
}) {
  const { isMobile } = useMobile()
  const actualColumns = isMobile ? 1 : columns
  
  return (
    <div 
      className={cn("grid", className)}
      style={{ 
        gridTemplateColumns: `repeat(${actualColumns}, minmax(0, 1fr))`,
        gap: `${gap * 4}px`
      }}
    >
      {data.map((item, idx) => renderCard(item, idx))}
    </div>
  )
}
