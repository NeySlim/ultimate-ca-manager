/**
 * ResponsiveDataTable - Unified table component
 * 
 * DESKTOP: Dense table with sticky header, hover rows, dropdown actions
 * MOBILE: Card-style rows with primary/secondary info, large touch targets
 */
import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { 
  MagnifyingGlass, CaretUp, CaretDown, DotsThreeVertical,
  CaretLeft, CaretRight, FunnelSimple, X, Columns, Eye, EyeSlash, Check,
  BookmarkSimple, FloppyDisk, Trash, Export
} from '@phosphor-icons/react'
import { useMobile } from '../../../contexts'
import { cn, exportToCSV, exportToJSON } from '../../../lib/utils'
import { FilterSelect } from '../Select'

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
  
  // Toolbar (filters + actions next to search)
  toolbarFilters, // Array of { key, value, onChange, placeholder, options: [{value, label}] }
  toolbarActions, // ReactNode - buttons to show on right side of toolbar
  
  // Column customization
  columnStorageKey, // localStorage key for saving column preferences (e.g. 'ucm-certs-columns')
  
  // Filter presets
  filterPresetsKey, // localStorage key for saving filter presets (e.g. 'ucm-certs-presets')
  onApplyFilterPreset, // (preset) => void - callback when a preset is applied
  
  // Export
  exportEnabled = false, // Enable export button
  exportFilename = 'export', // Base filename for exports
  
  // Sorting
  sortable = false,
  defaultSort, // { key, direction: 'asc' | 'desc' }
  onSortChange, // (sort: { key, direction }) => void - for server-side sorting
  
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
  
  // Column visibility state
  const [showColumnMenu, setShowColumnMenu] = useState(false)
  const columnMenuRef = useRef(null)
  const [hiddenColumns, setHiddenColumns] = useState(() => {
    if (columnStorageKey) {
      try {
        const saved = localStorage.getItem(columnStorageKey)
        return saved ? JSON.parse(saved) : []
      } catch {
        return []
      }
    }
    return []
  })
  
  // Save column preferences
  useEffect(() => {
    if (columnStorageKey) {
      localStorage.setItem(columnStorageKey, JSON.stringify(hiddenColumns))
    }
  }, [hiddenColumns, columnStorageKey])
  
  // Toggle column visibility
  const toggleColumn = (key) => {
    setHiddenColumns(prev => 
      prev.includes(key) 
        ? prev.filter(k => k !== key)
        : [...prev, key]
    )
  }
  
  // Filter columns by user preference
  const userVisibleColumns = useMemo(() => {
    return columns.filter(col => !hiddenColumns.includes(col.key))
  }, [columns, hiddenColumns])
  
  // Filter presets state
  const [showPresetsMenu, setShowPresetsMenu] = useState(false)
  const [showSavePresetModal, setShowSavePresetModal] = useState(false)
  const [presetName, setPresetName] = useState('')
  const presetsMenuRef = useRef(null)
  const [filterPresets, setFilterPresets] = useState(() => {
    if (filterPresetsKey) {
      try {
        const saved = localStorage.getItem(filterPresetsKey)
        return saved ? JSON.parse(saved) : []
      } catch {
        return []
      }
    }
    return []
  })
  
  // Save presets to localStorage
  useEffect(() => {
    if (filterPresetsKey) {
      localStorage.setItem(filterPresetsKey, JSON.stringify(filterPresets))
    }
  }, [filterPresets, filterPresetsKey])
  
  // Get current filter values for saving
  const getCurrentFilterValues = useCallback(() => {
    if (!toolbarFilters) return {}
    const values = {}
    toolbarFilters.forEach(filter => {
      if (filter.type === 'dateRange') {
        if (filter.from) values[`${filter.key}_from`] = filter.from
        if (filter.to) values[`${filter.key}_to`] = filter.to
      } else if (filter.value) {
        values[filter.key] = filter.value
      }
    })
    if (searchValue) values._search = searchValue
    return values
  }, [toolbarFilters, searchValue])
  
  // Check if any filters are active
  const hasActiveFilters = useMemo(() => {
    if (searchValue) return true
    if (!toolbarFilters) return false
    return toolbarFilters.some(f => 
      f.type === 'dateRange' ? (f.from || f.to) : f.value
    )
  }, [toolbarFilters, searchValue])
  
  // Save current filters as preset
  const savePreset = () => {
    if (!presetName.trim()) return
    const newPreset = {
      id: Date.now(),
      name: presetName.trim(),
      filters: getCurrentFilterValues()
    }
    setFilterPresets(prev => [...prev, newPreset])
    setPresetName('')
    setShowSavePresetModal(false)
  }
  
  // Delete a preset
  const deletePreset = (id) => {
    setFilterPresets(prev => prev.filter(p => p.id !== id))
  }
  
  // Apply a preset
  const applyPreset = (preset) => {
    if (onApplyFilterPreset) {
      onApplyFilterPreset(preset.filters)
    }
    setShowPresetsMenu(false)
  }
  
  // Export menu state (functions defined after sortedData/visibleColumns)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const exportMenuRef = useRef(null)
  
  // Close export menu on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target)) {
        setShowExportMenu(false)
      }
    }
    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showExportMenu])
  
  // Close presets menu on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (presetsMenuRef.current && !presetsMenuRef.current.contains(e.target)) {
        setShowPresetsMenu(false)
        setShowSavePresetModal(false)
      }
    }
    if (showPresetsMenu || showSavePresetModal) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPresetsMenu, showSavePresetModal])
  
  // Close column menu on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (columnMenuRef.current && !columnMenuRef.current.contains(e.target)) {
        setShowColumnMenu(false)
      }
    }
    if (showColumnMenu) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showColumnMenu])
  
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
    // If server-side sorting is enabled, don't sort client-side
    if (onSortChange) return filteredData
    
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
  }, [filteredData, sort, onSortChange])
  
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
      let newSort
      if (prev?.key !== key) {
        newSort = { key, direction: 'asc' }
      } else if (prev.direction === 'asc') {
        newSort = { key, direction: 'desc' }
      } else {
        newSort = null // Remove sort
      }
      
      // Notify parent for server-side sorting
      if (onSortChange) {
        onSortChange(newSort)
      }
      
      return newSort
    })
  }, [sortable, onSortChange])
  
  // Get visible columns based on device + user preferences
  const visibleColumns = useMemo(() => {
    // First filter by user preference (hidden columns)
    let cols = userVisibleColumns
    // On mobile, also filter columns that have hideOnMobile
    if (!isDesktop) {
      cols = cols.filter(col => !col.hideOnMobile)
    }
    return cols
  }, [userVisibleColumns, isDesktop])
  
  // Export functions (must be after sortedData and visibleColumns)
  const handleExportCSV = useCallback(() => {
    exportToCSV(sortedData, visibleColumns, exportFilename)
    setShowExportMenu(false)
  }, [sortedData, visibleColumns, exportFilename])
  
  const handleExportJSON = useCallback(() => {
    exportToJSON(sortedData, exportFilename)
    setShowExportMenu(false)
  }, [sortedData, exportFilename])
  
  // Get primary and secondary columns for mobile cards
  const { primaryCol, secondaryCol, tertiaryCol } = useMemo(() => {
    const sorted = [...columns].sort((a, b) => (a.priority || 99) - (b.priority || 99))
    return {
      primaryCol: sorted[0],
      secondaryCol: sorted[1],
      tertiaryCol: sorted[2]
    }
  }, [columns])
  
  // Empty state - but ALWAYS show toolbar if there are filters to clear
  if (!loading && sortedData.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Always show toolbar when there are filters or actions */}
        {(searchable || toolbarFilters || toolbarActions || columnStorageKey || filterPresetsKey) && (
          <SearchBar
            value={searchValue}
            onChange={setSearchValue}
            placeholder={searchPlaceholder}
            isMobile={isMobile}
            searchable={searchable}
            filters={toolbarFilters}
            actions={toolbarActions}
            columns={columnStorageKey ? columns : null}
            hiddenColumns={hiddenColumns}
            toggleColumn={toggleColumn}
            showColumnMenu={showColumnMenu}
            setShowColumnMenu={setShowColumnMenu}
            columnMenuRef={columnMenuRef}
            // Filter presets
            filterPresetsKey={filterPresetsKey}
            filterPresets={filterPresets}
            showPresetsMenu={showPresetsMenu}
            setShowPresetsMenu={setShowPresetsMenu}
            showSavePresetModal={showSavePresetModal}
            setShowSavePresetModal={setShowSavePresetModal}
            presetName={presetName}
            setPresetName={setPresetName}
            presetsMenuRef={presetsMenuRef}
            hasActiveFilters={hasActiveFilters}
            savePreset={savePreset}
            deletePreset={deletePreset}
            applyPreset={applyPreset}
            // Export - disabled in empty state
            exportEnabled={false}
          />
        )}
        
        {/* Empty state content */}
        <div className="flex-1 flex flex-col items-center justify-center py-16 px-4">
          {EmptyIcon && (
            <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4">
              <EmptyIcon size={32} className="text-text-secondary" />
            </div>
          )}
          <h3 className="text-lg font-medium text-text-primary mb-1">
            {hasActiveFilters ? 'No matching results' : emptyTitle}
          </h3>
          <p className="text-sm text-text-secondary text-center max-w-sm mb-4">
            {hasActiveFilters 
              ? 'Try adjusting your filters or search terms'
              : emptyDescription
            }
          </p>
          {hasActiveFilters ? (
            <button
              onClick={() => {
                setSearchValue('')
                toolbarFilters?.forEach(f => {
                  f.onChange?.('')
                  // Clear date range filters
                  if (f.type === 'dateRange') {
                    f.onFromChange?.('')
                    f.onToChange?.('')
                  }
                })
              }}
              className="text-sm text-accent-primary hover:text-accent-primary/80 font-medium"
            >
              Clear all filters
            </button>
          ) : emptyAction}
        </div>
      </div>
    )
  }
  
  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* SEARCH BAR + TOOLBAR */}
      {(searchable || toolbarFilters || toolbarActions || columnStorageKey || filterPresetsKey) && (
        <SearchBar
          value={searchValue}
          onChange={setSearchValue}
          placeholder={searchPlaceholder}
          isMobile={isMobile}
          searchable={searchable}
          filters={toolbarFilters}
          actions={toolbarActions}
          columns={columnStorageKey ? columns : null}
          hiddenColumns={hiddenColumns}
          toggleColumn={toggleColumn}
          showColumnMenu={showColumnMenu}
          setShowColumnMenu={setShowColumnMenu}
          columnMenuRef={columnMenuRef}
          // Filter presets
          filterPresetsKey={filterPresetsKey}
          filterPresets={filterPresets}
          showPresetsMenu={showPresetsMenu}
          setShowPresetsMenu={setShowPresetsMenu}
          showSavePresetModal={showSavePresetModal}
          setShowSavePresetModal={setShowSavePresetModal}
          presetName={presetName}
          setPresetName={setPresetName}
          presetsMenuRef={presetsMenuRef}
          hasActiveFilters={hasActiveFilters}
          savePreset={savePreset}
          deletePreset={deletePreset}
          applyPreset={applyPreset}
          // Export
          exportEnabled={exportEnabled}
          showExportMenu={showExportMenu}
          setShowExportMenu={setShowExportMenu}
          exportMenuRef={exportMenuRef}
          handleExportCSV={handleExportCSV}
          handleExportJSON={handleExportJSON}
          dataCount={sortedData.length}
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
// SEARCH BAR + TOOLBAR
// =============================================================================

function SearchBar({ 
  value, 
  onChange, 
  placeholder, 
  isMobile, 
  searchable = true, 
  filters, 
  actions,
  // Column customization
  columns,
  hiddenColumns,
  toggleColumn,
  showColumnMenu,
  setShowColumnMenu,
  columnMenuRef,
  // Filter presets
  filterPresetsKey,
  filterPresets,
  showPresetsMenu,
  setShowPresetsMenu,
  showSavePresetModal,
  setShowSavePresetModal,
  presetName,
  setPresetName,
  presetsMenuRef,
  hasActiveFilters,
  savePreset,
  deletePreset,
  applyPreset,
  // Export
  exportEnabled,
  showExportMenu,
  setShowExportMenu,
  exportMenuRef,
  handleExportCSV,
  handleExportJSON,
  dataCount
}) {
  return (
    <div className={cn(
      'shrink-0 border-b border-border/50 bg-bg-secondary/30',
      isMobile ? 'px-4 py-3' : 'px-4 py-2.5'
    )}>
      <div className="flex items-center gap-2">
        {/* Search input */}
        {searchable && (
          <div className="relative group flex-1 min-w-0">
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
        )}
        
        {/* Filters (desktop only) */}
        {!isMobile && filters && filters.length > 0 && (
          <div className="flex items-center gap-2 shrink-0">
            {filters.map((filter) => {
              // Date range filter
              if (filter.type === 'dateRange') {
                return (
                  <div key={filter.key} className="flex items-center gap-1.5 shrink-0">
                    <input
                      type="date"
                      value={filter.from || ''}
                      onChange={(e) => filter.onFromChange?.(e.target.value)}
                      className={cn(
                        'h-7 w-28 px-2 text-xs rounded-md border border-border bg-bg-primary',
                        'text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-primary',
                        '[color-scheme:dark]',
                        filter.from && 'border-accent-primary/50'
                      )}
                      title={filter.fromPlaceholder || 'From date'}
                    />
                    <span className="text-text-tertiary text-xs">→</span>
                    <input
                      type="date"
                      value={filter.to || ''}
                      onChange={(e) => filter.onToChange?.(e.target.value)}
                      className={cn(
                        'h-7 w-28 px-2 text-xs rounded-md border border-border bg-bg-primary',
                        'text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-primary',
                        '[color-scheme:dark]',
                        filter.to && 'border-accent-primary/50'
                      )}
                      title={filter.toPlaceholder || 'To date'}
                    />
                  </div>
                )
              }
              // Default: FilterSelect
              return (
                <FilterSelect
                  key={filter.key}
                  value={filter.value || ''}
                  onChange={filter.onChange}
                  placeholder={filter.placeholder || 'All'}
                  options={filter.options || []}
                  size="sm"
                />
              )
            })}
          </div>
        )}
        
        {/* Column Selector (desktop only) */}
        {!isMobile && columns && columns.length > 0 && (
          <div className="relative shrink-0" ref={columnMenuRef}>
            <button
              onClick={() => setShowColumnMenu?.(!showColumnMenu)}
              className={cn(
                'flex items-center gap-1.5 h-7 px-2 rounded-md border text-xs font-medium transition-colors',
                showColumnMenu
                  ? 'border-accent-primary bg-accent-primary/10 text-accent-primary'
                  : 'border-border bg-bg-primary text-text-secondary hover:text-text-primary hover:border-border-hover'
              )}
              title="Customize columns"
            >
              <Columns size={14} />
            </button>
            
            {/* Dropdown menu */}
            {showColumnMenu && (
              <div className="absolute right-0 top-full mt-1 z-50 w-48 rounded-lg border border-border bg-bg-primary shadow-lg py-1">
                <div className="px-3 py-1.5 text-[10px] font-semibold text-text-tertiary uppercase tracking-wider border-b border-border mb-1">
                  Show columns
                </div>
                {columns.map(col => (
                  <button
                    key={col.key}
                    onClick={() => toggleColumn?.(col.key)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-bg-hover transition-colors"
                  >
                    <span className={cn(
                      'w-4 h-4 rounded border flex items-center justify-center',
                      hiddenColumns?.includes(col.key)
                        ? 'border-border bg-bg-secondary'
                        : 'border-accent-primary bg-accent-primary text-white'
                    )}>
                      {!hiddenColumns?.includes(col.key) && <Check size={10} weight="bold" />}
                    </span>
                    <span className={cn(
                      hiddenColumns?.includes(col.key) ? 'text-text-tertiary' : 'text-text-primary'
                    )}>
                      {col.header || col.key}
                    </span>
                  </button>
                ))}
                {hiddenColumns?.length > 0 && (
                  <>
                    <div className="border-t border-border my-1" />
                    <button
                      onClick={() => {
                        columns.forEach(col => {
                          if (hiddenColumns.includes(col.key)) {
                            toggleColumn?.(col.key)
                          }
                        })
                      }}
                      className="w-full px-3 py-1.5 text-xs text-accent-primary hover:bg-bg-hover transition-colors text-left"
                    >
                      Show all columns
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Filter Presets (desktop only) */}
        {!isMobile && filterPresetsKey && (
          <div className="relative shrink-0" ref={presetsMenuRef}>
            <button
              onClick={() => setShowPresetsMenu?.(!showPresetsMenu)}
              className={cn(
                'flex items-center gap-1.5 h-7 px-2 rounded-md border text-xs font-medium transition-colors',
                showPresetsMenu
                  ? 'border-accent-primary bg-accent-primary/10 text-accent-primary'
                  : 'border-border bg-bg-primary text-text-secondary hover:text-text-primary hover:border-border-hover'
              )}
              title="Filter presets"
            >
              <BookmarkSimple size={14} />
              {filterPresets?.length > 0 && (
                <span className="text-[10px] bg-accent-primary/20 text-accent-primary px-1 rounded">
                  {filterPresets.length}
                </span>
              )}
            </button>
            
            {/* Presets dropdown */}
            {showPresetsMenu && (
              <div className="absolute right-0 top-full mt-1 z-50 w-56 rounded-lg border border-border bg-bg-primary shadow-lg py-1">
                <div className="px-3 py-1.5 text-[10px] font-semibold text-text-tertiary uppercase tracking-wider border-b border-border mb-1">
                  Filter Presets
                </div>
                
                {/* Save current filter button */}
                {hasActiveFilters && !showSavePresetModal && (
                  <button
                    onClick={() => setShowSavePresetModal?.(true)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-bg-hover transition-colors text-accent-primary"
                  >
                    <FloppyDisk size={14} />
                    Save current filters
                  </button>
                )}
                
                {/* Save preset input */}
                {showSavePresetModal && (
                  <div className="px-3 py-2 border-b border-border">
                    <input
                      type="text"
                      value={presetName}
                      onChange={(e) => setPresetName?.(e.target.value)}
                      placeholder="Preset name..."
                      className="w-full h-7 px-2 text-xs rounded border border-border bg-bg-secondary text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent-primary"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') savePreset?.()
                        if (e.key === 'Escape') setShowSavePresetModal?.(false)
                      }}
                    />
                    <div className="flex gap-2 mt-2">
                      <button
                        onClick={savePreset}
                        disabled={!presetName?.trim()}
                        className="flex-1 h-6 text-xs rounded bg-accent-primary text-white hover:bg-accent-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setShowSavePresetModal?.(false)}
                        className="h-6 px-2 text-xs rounded border border-border hover:bg-bg-hover"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                
                {/* Preset list */}
                {filterPresets?.length > 0 ? (
                  <>
                    {hasActiveFilters && <div className="border-t border-border my-1" />}
                    {filterPresets.map(preset => (
                      <div
                        key={preset.id}
                        className="group flex items-center gap-2 px-3 py-1.5 hover:bg-bg-hover transition-colors"
                      >
                        <button
                          onClick={() => applyPreset?.(preset)}
                          className="flex-1 text-xs text-left text-text-primary truncate"
                          title={Object.entries(preset.filters || {}).map(([k, v]) => `${k}: ${v}`).join(', ')}
                        >
                          {preset.name}
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            deletePreset?.(preset.id)
                          }}
                          className="opacity-0 group-hover:opacity-100 p-1 text-text-tertiary hover:text-red-500 transition-all"
                          title="Delete preset"
                        >
                          <Trash size={12} />
                        </button>
                      </div>
                    ))}
                  </>
                ) : !hasActiveFilters && (
                  <div className="px-3 py-4 text-xs text-text-tertiary text-center">
                    No saved presets.<br/>
                    Apply filters and save them here.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Export Button (desktop only) */}
        {!isMobile && exportEnabled && dataCount > 0 && (
          <div className="relative shrink-0" ref={exportMenuRef}>
            <button
              onClick={() => setShowExportMenu?.(!showExportMenu)}
              className={cn(
                'flex items-center gap-1.5 h-7 px-2 rounded-md border text-xs font-medium transition-colors',
                showExportMenu
                  ? 'border-accent-primary bg-accent-primary/10 text-accent-primary'
                  : 'border-border bg-bg-primary text-text-secondary hover:text-text-primary hover:border-border-hover'
              )}
              title="Export data"
            >
              <Export size={14} />
            </button>
            
            {/* Export dropdown */}
            {showExportMenu && (
              <div className="absolute right-0 top-full mt-1 z-50 w-44 rounded-lg border border-border bg-bg-primary shadow-lg py-1">
                <div className="px-3 py-1.5 text-[10px] font-semibold text-text-tertiary uppercase tracking-wider border-b border-border mb-1">
                  Export {dataCount} items
                </div>
                <button
                  onClick={handleExportCSV}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-bg-hover transition-colors"
                >
                  <Export size={14} />
                  Export as CSV
                </button>
                <button
                  onClick={handleExportJSON}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-bg-hover transition-colors"
                >
                  <Export size={14} />
                  Export as JSON
                </button>
              </div>
            )}
          </div>
        )}
        
        {/* Actions */}
        {actions && (
          <div className="flex items-center gap-2 shrink-0">
            {actions}
          </div>
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
  // Calculate column flex styles based on content type
  const getColStyle = (col) => {
    if (col.width) return { width: col.width, minWidth: col.width, maxWidth: col.width }
    // Dynamic sizing with constraints
    const defaults = {
      minWidth: col.minWidth || '80px',
      maxWidth: col.maxWidth || '300px',
      flex: col.flex || '1 1 auto'
    }
    return defaults
  }

  return (
    <div className="flex-1 overflow-auto">
      <table className="w-full text-sm" style={{ tableLayout: 'auto' }}>
        {/* Header */}
        <thead className="sticky top-0 z-10 bg-bg-secondary/95 backdrop-blur-sm border-b border-border shadow-sm">
          <tr>
            {columns.map((col) => {
              const style = getColStyle(col)
              return (
                <th
                  key={col.key}
                  onClick={() => sortable && col.sortable !== false && onSort(col.key)}
                  style={style}
                  className={cn(
                    'text-left px-4 py-1.5 text-[11px] font-medium text-text-tertiary tracking-wide',
                    'transition-colors duration-200',
                    sortable && col.sortable !== false && 'cursor-pointer hover:text-text-secondary',
                    sort?.key === col.key && 'text-accent-primary'
                  )}
                >
                  <div className="flex items-center gap-1.5 truncate">
                    {col.header || col.label}
                    {sort?.key === col.key && (
                      sort.direction === 'asc' 
                        ? <CaretUp size={10} weight="bold" className="text-accent-primary" />
                        : <CaretDown size={10} weight="bold" className="text-accent-primary" />
                    )}
                  </div>
                </th>
              )
            })}
            {rowActions && <th className="w-12 min-w-[48px]" />}
          </tr>
        </thead>
        
        {/* Body */}
        <tbody className="divide-y divide-border/50 border-b border-border">
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
                  'group transition-all duration-200 table-row-hover',
                  onRowClick && 'cursor-pointer',
                  // Selected state - uses theme-aware CSS class
                  selectedId === row.id && 'row-selected'
                )}>
                {columns.map((col) => {
                  const style = getColStyle(col)
                  return (
                    <td 
                      key={col.key}
                      style={style}
                      className={cn(
                        "px-4 py-1.5 transition-colors duration-200",
                        col.className
                      )}
                    >
                      <div 
                        className={cn(
                          // Global overflow protection
                          !col.noTruncate && "truncate"
                        )}
                        title={!col.noTruncate && typeof row[col.key] === 'string' ? row[col.key] : undefined}
                      >
                        {col.render 
                          ? col.render(row[col.key], row)
                          : row[col.key] ?? '—'
                        }
                      </div>
                    </td>
                  )
                })}
                {rowActions && (
                  <td className="px-2 py-1.5 relative">
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
          'text-text-tertiary hover:text-text-primary',
          'hover:bg-bg-tertiary',
          'transition-all duration-150',
          isOpen && 'bg-accent-primary/10 text-accent-primary'
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
          <FilterSelect
            value={String(perPage)}
            onChange={(val) => onPerPageChange(Number(val))}
            options={[10, 25, 50, 100].map(n => ({ value: String(n), label: `${n}/page` }))}
            placeholder={`${perPage}/page`}
            size="sm"
          />
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
