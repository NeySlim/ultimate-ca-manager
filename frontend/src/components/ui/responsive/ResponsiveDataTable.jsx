/**
 * ResponsiveDataTable - Unified table component
 * 
 * DESKTOP: Dense table with sticky header, hover rows, dropdown actions
 * MOBILE: Card-style rows with primary/secondary info, large touch targets
 */
import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  MagnifyingGlass, CaretUp, CaretDown, DotsThreeVertical,
  CaretLeft, CaretRight, X, Columns, Check,
  BookmarkSimple, FloppyDisk, Trash, Export, Rows, DownloadSimple
} from '@phosphor-icons/react'
import { useMobile } from '../../../contexts'
import { cn, exportToCSV, exportToJSON } from '../../../lib/utils'
import { fetchPages } from '../../../lib/fetchAllPages'
import { FilterSelect } from '../Select'
import { MultiSelectFilter } from '../MultiSelectFilter'
import { FilterChips } from '../FilterChips'
import { ListTable } from './ListTable'
import { ListDialog } from '../../list/ListDialog'
import { ListCards } from './ListCards'
import { ColumnsIcon, RowsIcon } from '../../list/atelierIcons'
import { useToolbarMenu } from '../../list/useToolbarMenu'
import '../../list/list.css'

const EXPORT_MAX_ROWS = 10000
// Row height of each density in the list template (list.css --lv-row)
const ROW_PX = { compact: 36, default: 40, comfortable: 44 }
// Beyond this many pages the list footer offers to jump to a page by its number
const PAGE_JUMP_ABOVE = 20
const PAGE_SIZES = [10, 25, 50, 100]
const EXPORT_PAGE_SIZE = 100

export function ResponsiveDataTable({
  // Data
  data = [],
  columns = [],
  
  // Selection
  selectedId,
  onRowClick,
  selectable = true,
  
  // Multi-select (all optional — existing pages don't pass these)
  multiSelect = false,
  selectedIds,          // Set<number|string>
  onSelectionChange,    // (Set) => void
  bulkActions,          // ReactNode: shown when items selected
  
  // Row actions (dropdown menu)
  rowActions, // (row) => [{ label, icon, onClick, variant }]
  
  // Search
  searchable = false,
  searchPlaceholder = 'Search...',
  searchKeys = [], // keys to search in
  externalSearch, // controlled search
  onSearchChange,
  
  // Toolbar (filters + actions next to search)
  toolbarFilters, // Array of { key, type, value, onChange, placeholder, options: [{value, label}] }
                  // type 'toggle': { label, value: bool, onChange, disabled, disabledReason }
  toolbarActions, // ReactNode - buttons to show on right side of toolbar
  
  // Column customization
  columnStorageKey, // localStorage key for saving column preferences (e.g. 'ucm-certs-columns')
  
  // Filter presets
  filterPresetsKey, // localStorage key for saving filter presets (e.g. 'ucm-certs-presets')
  presetExtras, // object merged into every saved preset (state the toolbar filters do not carry)
  onApplyFilterPreset, // (preset) => void - callback when a preset is applied
  
  // Export
  exportEnabled = false, // Enable export button
  exportFilename = 'export', // Base filename for exports
  // A server-paged table exports through this: ({ page, per_page }) => Promise<{ data: rows[], meta: { total } }>
  // returning a page of the list as filtered and sorted on screen. Without it such a table offers no export.
  exportLoader,
  
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
  
  // Density - affects row height, padding, gaps
  // 'compact': Dense rows (py-1, gap-2) - default for tables
  // 'default': Standard rows (py-1.5, gap-3)
  // 'comfortable': Spacious rows (py-2, gap-4)
  density: densityProp = 'compact',
  
  // Density toggle - when provided, enables density toggle button
  densityStorageKey, // localStorage key for density preference (e.g. 'ucm-certs-density')
  
  // List template (all optional): variant="list" draws the flat toolbar, the content-sized
  // table with one `grow` column, rows of one height, a checkbox per row beside a row click
  // that still opens, the row actions and an opening chevron, and the worded footer.
  // Column flags it reads: grow, maxWidth, muted, small, title(row); defaultHidden works in both.
  variant = 'default',
  rowLabel, // (row) => string: names the row in the labels of its checkbox and actions
  rangeLabel, // ({ start, end, total }) => string: "1–25 of 276 certificates"
  tableLabel, // accessible name of the table
  footNote, // text under the table, left of the density and column count
  searchLabel, // accessible name of the search field (list template)
  belowToolbar, // ReactNode under the toolbar (active filters), list template
  openFromName = false, // list template: only the name and the chevron open a row
  lockRowsOnSelect = false, // list template: names and row actions wait while rows are ticked
  card, // list template on a phone: row => { description, meta, status, end } draws Atelier records
  noMatch, // list template, nothing matches the filters: { title, description, action }
  columnsNote, // list template: the sentence of the columns dialog
  selectionLabel, // list template: (count) => words of the selection bar (« 3 certificats sélectionnés sur cette page »)

  // Custom class
  className
}) {
  const { isMobile, isDesktop, isTouch } = useMobile()
  const { t } = useTranslation()
  const list = variant === 'list'
  // The list template draws the desktop, and phones too when the page gives its records
  // (`card`); a list without them keeps the older card list on a phone
  const cards = list && isMobile && typeof card === 'function'
  const flat = list && (!isMobile || cards)
  
  // Density state (persisted if key provided); the list template has two, compact and comfortable
  const [density, setDensity] = useState(() => {
    let saved = densityProp
    if (densityStorageKey) {
      try { saved = localStorage.getItem(densityStorageKey) || densityProp } catch { /* storage unavailable */ }
    }
    return list && saved !== 'comfortable' ? 'compact' : saved
  })
  
  const cycleDensity = useCallback(() => {
    const next = list
      ? (density === 'comfortable' ? 'compact' : 'comfortable')
      : density === 'compact' ? 'default' : density === 'default' ? 'comfortable' : 'compact'
    setDensity(next)
    if (densityStorageKey) {
      try { localStorage.setItem(densityStorageKey, next) } catch {}
    }
  }, [density, densityStorageKey, list])
  
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
  
  // Column widths state for resizing
  const [columnWidths, setColumnWidths] = useState(() => {
    if (columnStorageKey) {
      try {
        const saved = localStorage.getItem(`${columnStorageKey}-widths`)
        return saved ? JSON.parse(saved) : {}
      } catch {
        return {}
      }
    }
    return {}
  })
  
  // Save column widths to localStorage
  useEffect(() => {
    if (columnStorageKey && Object.keys(columnWidths).length > 0) {
      try { localStorage.setItem(`${columnStorageKey}-widths`, JSON.stringify(columnWidths)) } catch {}
    }
  }, [columnWidths, columnStorageKey])
  
  // Update column width
  const setColumnWidth = useCallback((key, width) => {
    setColumnWidths(prev => ({ ...prev, [key]: width }))
  }, [])
  
  // Reset column width to default
  const resetColumnWidth = useCallback((key) => {
    setColumnWidths(prev => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }, [])
  
  // Multi-select handlers
  const handleToggleRow = useCallback((rowId) => {
    if (!multiSelect || !onSelectionChange) return
    const next = new Set(selectedIds || [])
    if (next.has(rowId)) next.delete(rowId)
    else next.add(rowId)
    onSelectionChange(next)
  }, [multiSelect, selectedIds, onSelectionChange])

  const handleToggleAll = useCallback((visibleData) => {
    if (!multiSelect || !onSelectionChange) return
    const visibleIds = visibleData.map(r => r.id).filter(Boolean)
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds?.has(id))
    if (allSelected) {
      const next = new Set(selectedIds || [])
      visibleIds.forEach(id => next.delete(id))
      onSelectionChange(next)
    } else {
      const next = new Set(selectedIds || [])
      visibleIds.forEach(id => next.add(id))
      onSelectionChange(next)
    }
  }, [multiSelect, selectedIds, onSelectionChange])

  const selectionCount = selectedIds?.size || 0

  // Row actions dropdown
  const [openActionMenu, setOpenActionMenu] = useState(null)
  const actionMenuRef = useRef(null)
  
  // Column visibility state
  const [showColumnMenu, setShowColumnMenu] = useState(false)
  const columnMenuRef = useRef(null)
  const [hiddenColumns, setHiddenColumns] = useState(() => {
    // Until the user chooses, the columns flagged defaultHidden stay out
    const initial = columns.filter(col => col.defaultHidden).map(col => col.key)
    if (columnStorageKey) {
      try {
        const saved = localStorage.getItem(columnStorageKey)
        return saved ? JSON.parse(saved) : initial
      } catch {
        return initial
      }
    }
    return initial
  })
  
  // Save column preferences
  useEffect(() => {
    if (columnStorageKey) {
      try { localStorage.setItem(columnStorageKey, JSON.stringify(hiddenColumns)) } catch {}
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
      try { localStorage.setItem(filterPresetsKey, JSON.stringify(filterPresets)) } catch {}
    }
  }, [filterPresets, filterPresetsKey])
  
  // Get current filter values for saving
  const getCurrentFilterValues = useCallback(() => {
    if (!toolbarFilters) return {}
    const values = {}
    toolbarFilters.forEach(filter => {
      if (filter.type === 'toggle') {
        // A toggle is a view switch, not a filter: saving it would put its
        // value into every preset and restore it behind the user's back.
        return
      }
      if (filter.type === 'dateRange') {
        if (filter.from) values[`${filter.key}_from`] = filter.from
        if (filter.to) values[`${filter.key}_to`] = filter.to
      } else if (filter.value) {
        values[filter.key] = filter.value
      }
    })
    if (searchValue) values._search = searchValue
    return { ...values, ...presetExtras }
  }, [toolbarFilters, searchValue, presetExtras])
  
  // Check if any filters are active
  const hasActiveFilters = useMemo(() => {
    if (searchValue) return true
    if (!toolbarFilters) return false
    return toolbarFilters.some(f => {
      if (f.type === 'dateRange') return f.from || f.to
      if (f.type === 'toggle') return false
      if (f.type === 'multiSelect') return Array.isArray(f.value) && f.value.length > 0
      return f.value
    })
  }, [toolbarFilters, searchValue])
  // State carried only by presetExtras (a link view) is savable too
  const canSavePreset = hasActiveFilters || Object.keys(presetExtras || {}).length > 0

  // Build filter chips from active toolbar filters
  const filterChipsArray = useMemo(() => {
    if (!toolbarFilters) return []
    return toolbarFilters
      .filter(f => {
        if (f.type === 'toggle' || f.hideChip) return false // hideChip: shown elsewhere already
        if (f.type === 'multiSelect') return Array.isArray(f.value) && f.value.length > 0
        if (f.type === 'dateRange') return f.from || f.to
        return f.value !== '' && f.value !== null && f.value !== undefined
      })
      .map(f => {
        const optMap = {}
        ;(f.options || []).forEach(o => { optMap[o.value] = o.label })
        return {
          key: f.key,
          label: f.label || f.placeholder || f.key,
          value: f.value,
          options: optMap
        }
      })
  }, [toolbarFilters])

  const handleRemoveChip = useCallback((key, value) => {
    if (!toolbarFilters) return
    const filter = toolbarFilters.find(f => {
      if (f.type === 'dateRange') return key === `${f.key}_from` || key === `${f.key}_to`
      return f.key === key
    })
    if (!filter) return
    if (filter.type === 'dateRange') {
      if (key.endsWith('_from')) filter.onFromChange?.('')
      else filter.onToChange?.('')
    } else if (filter.type === 'multiSelect' && Array.isArray(filter.value)) {
      filter.onChange(filter.value.filter(v => v !== value))
    } else {
      filter.onChange('')
    }
  }, [toolbarFilters])

  // Clearing sets each filter back to its own empty value. A toggle has none:
  // onChange('') would switch it off and persist the empty string, so it is
  // left alone -- it is not counted as an active filter either. Both Clear
  // filters buttons, the chip row's and the empty state's, come through here.
  const handleClearAllChips = useCallback(() => {
    setSearchValue('')
    toolbarFilters?.forEach(f => {
      if (f.type === 'toggle') return
      if (f.type === 'dateRange') {
        f.onFromChange?.('')
        f.onToChange?.('')
      } else if (f.type === 'multiSelect') {
        f.onChange?.([])
      } else {
        f.onChange?.('')
      }
    })
  }, [toolbarFilters])

  
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
      // Normalize: accept both onChange and onPageChange for compatibility
      return {
        ...pagination,
        onChange: pagination.onChange || pagination.onPageChange
      }
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
        // The list template toggles between two directions; elsewhere a third click removes the sort
        newSort = list ? { key, direction: 'asc' } : null
      }
      
      // Notify parent for server-side sorting
      if (onSortChange) {
        onSortChange(newSort)
      }
      
      return newSort
    })
  }, [sortable, onSortChange, list])
  
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
  // A table is paged by the server when it is handed a pagination object: its rows
  // are then one page, and the file is built from the loader walking every page.
  const serverPaged = useExternalPagination
  const exportCount = serverPaged ? Math.min(pagination.total || 0, EXPORT_MAX_ROWS) : sortedData.length
  const canExport = exportEnabled && (!serverPaged || typeof exportLoader === 'function')
  const [exportState, setExportState] = useState({ busy: false, notice: null })

  const runExport = useCallback(async (write) => {
    setShowExportMenu(false)
    if (!serverPaged) {
      write(sortedData)
      return
    }
    setExportState({ busy: true, notice: null })
    try {
      const { rows, total, complete } = await fetchPages(exportLoader, {
        perPage: EXPORT_PAGE_SIZE, max: EXPORT_MAX_ROWS,
      })
      if (!complete) {
        setExportState({ busy: false, notice: { key: 'table.exportFailed' } })
        return
      }
      write(rows)
      const available = pagination.total || total
      setExportState({
        busy: false,
        notice: available > EXPORT_MAX_ROWS
          ? { key: 'table.exportTruncated', values: { count: EXPORT_MAX_ROWS, total: available } }
          : null,
      })
    } catch {
      setExportState({ busy: false, notice: { key: 'table.exportFailed' } })
    }
  }, [serverPaged, sortedData, exportLoader, pagination])

  const handleExportCSV = useCallback(
    () => runExport((rows) => exportToCSV(rows, visibleColumns, exportFilename)),
    [runExport, visibleColumns, exportFilename])

  const handleExportJSON = useCallback(
    () => runExport((rows) => exportToJSON(rows, exportFilename)),
    [runExport, exportFilename])
  
  // Get primary and secondary columns for mobile cards
  // NOTE: If secondaryCol has mobileRender, it likely includes tertiary info already
  const { primaryCol, secondaryCol, tertiaryCol } = useMemo(() => {
    // Filter out hideOnMobile columns, then sort by priority
    const mobileColumns = columns.filter(col => col.hideOnMobile !== true)
    const sorted = [...mobileColumns].sort((a, b) => (a.priority || 99) - (b.priority || 99))
    
    const primary = sorted[0]
    const secondary = sorted[1]
    // Only show tertiary if secondary doesn't have mobileRender (which combines info)
    const tertiary = sorted.length > 2 && !secondary?.mobileRender ? sorted[2] : null
    
    return { primaryCol: primary, secondaryCol: secondary, tertiaryCol: tertiary }
  }, [columns])
  
  // Empty state - but ALWAYS show toolbar if there are filters to clear; the list
  // template keeps its toolbar, header and footer and draws the empty block in its table
  if (!flat && !loading && sortedData.length === 0) {
    return (
      <div className={cn(flat ? 'lv-workspace' : 'flex flex-col h-full', className)}>
        {/* Always show toolbar when there are filters or actions */}
        {(searchable || toolbarFilters || toolbarActions || columnStorageKey || filterPresetsKey) && (
          <SearchBar
            flat={flat}
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
            hasActiveFilters={canSavePreset}
            savePreset={savePreset}
            deletePreset={deletePreset}
            applyPreset={applyPreset}
            // Export - disabled in empty state
            exportEnabled={false}
          />
        )}
        
        {/* Empty state content */}
        {flat ? (
          <div className="lv-table-box">
            <div className="lv-empty" data-testid="list-empty">
              {EmptyIcon && <EmptyIcon aria-hidden="true" />}
              <h3>{hasActiveFilters ? t('table.noResults') : emptyTitle}</h3>
              <p>{hasActiveFilters ? t('table.adjustFilters') : emptyDescription}</p>
              {hasActiveFilters ? (
                <button type="button" className="lv-btn" onClick={handleClearAllChips}>{t('table.clearFilters')}</button>
              ) : emptyAction}
            </div>
          </div>
        ) : (
          // The same empty block outside the list template, without its table box
          <div className="lv-empty" data-testid="list-empty">
            {EmptyIcon && <EmptyIcon aria-hidden="true" />}
            <h3>{hasActiveFilters ? t('table.noResults') : emptyTitle}</h3>
            <p>{hasActiveFilters ? t('table.adjustFilters') : emptyDescription}</p>
            {hasActiveFilters ? (
              <button type="button" className="lv-btn" onClick={handleClearAllChips}>{t('table.clearFilters')}</button>
            ) : emptyAction}
          </div>
        )}
      </div>
    )
  }
  
  const rangeOf = ({ start, end, total }) => (
    rangeLabel ? rangeLabel({ start, end, total }) : t('table.range', { start, end, total })
  )
  // List template, nothing to show: the block stands in the table, under its header
  const nothing = flat && !loading && sortedData.length === 0
  const emptyContent = nothing ? (
    <div className="lv-empty" data-testid="list-empty">
      {hasActiveFilters ? <MagnifyingGlass aria-hidden="true" /> : EmptyIcon && <EmptyIcon aria-hidden="true" />}
      <h3>{hasActiveFilters ? (noMatch?.title || t('table.noResults')) : emptyTitle}</h3>
      <p>{hasActiveFilters ? (noMatch?.description || t('table.adjustFilters')) : emptyDescription}</p>
      {hasActiveFilters ? (
        <button type="button" className="lv-btn" onClick={noMatch?.onReset || handleClearAllChips}>
          {noMatch?.action || t('table.clearFilters')}
        </button>
      ) : emptyAction}
    </div>
  ) : null
  const totalPages = paginationProps ? Math.max(1, Math.ceil((paginationProps.total || 0) / paginationProps.perPage)) : 1
  // A long list says how many results its search found, or that it is still searching
  const searchStatus = flat && paginationProps && searchValue && totalPages > PAGE_JUMP_ABOVE
    ? (loading ? t('table.searching') : t('table.results', { count: paginationProps.total || 0 }))
    : null

  return (
    <div className={cn(flat ? 'lv-workspace' : 'flex flex-col h-full', className)}>
      {/* SEARCH BAR + TOOLBAR */}
      {(searchable || toolbarFilters || toolbarActions || columnStorageKey || filterPresetsKey) && (
        <SearchBar
          flat={flat}
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
          hasActiveFilters={canSavePreset}
          savePreset={savePreset}
          deletePreset={deletePreset}
          applyPreset={applyPreset}
          // Export
          exportEnabled={canExport}
          exportBusy={exportState.busy}
          exportNotice={exportState.notice}
          showExportMenu={showExportMenu}
          setShowExportMenu={setShowExportMenu}
          exportMenuRef={exportMenuRef}
          handleExportCSV={handleExportCSV}
          handleExportJSON={handleExportJSON}
          dataCount={exportCount}
          densityStorageKey={densityStorageKey}
          density={density}
          cycleDensity={cycleDensity}
          searchLabel={searchLabel}
          searchStatus={searchStatus}
          columnsNote={columnsNote}
        />
      )}
      {flat && belowToolbar}

      {/* ACTIVE FILTER CHIPS */}
      {hasActiveFilters && filterChipsArray.length > 0 && (
        <div className={flat ? undefined : 'px-1 pb-1'}>
          <FilterChips
            filters={filterChipsArray}
            onRemove={handleRemoveChip}
            onClearAll={handleClearAllChips}
            className={flat ? 'lv-chips' : undefined}
          />
        </div>
      )}
      
      {/* BULK ACTION BAR */}
      {flat && multiSelect && selectionCount > 0 && bulkActions && (
        <div className="lv-batch" role="group" aria-label={t('table.selection')}>
          <strong>{selectionLabel ? selectionLabel(selectionCount) : t('table.selectedCount', { count: selectionCount })}</strong>
          {bulkActions}
          <span className="lv-spacer" />
          <button type="button" className="lv-btn is-quiet" onClick={() => onSelectionChange(new Set())}>
            {t('table.clearSelection')}
          </button>
        </div>
      )}
      {!flat && multiSelect && selectionCount > 0 && bulkActions && (
        <div className="flex items-center gap-3 px-4 py-2 bg-accent-primary-op10 border border-accent-primary-op20 rounded-lg mx-1 mb-1">
          <span className="text-sm font-medium text-accent-primary">
            {selectionCount} {t('table.selected')}
          </span>
          <div className="flex items-center gap-2 ml-auto">
            {bulkActions}
            <button
              onClick={() => onSelectionChange(new Set())}
              className="text-xs text-text-secondary hover:text-text-primary transition-colors px-2 py-1"
            >
              {t('common.clear')}
            </button>
          </div>
        </div>
      )}

      {/* TABLE / CARDS */}
      {cards ? (
        <>
        <div className="lv-table-box is-cards">
          <ListCards
            data={paginatedData}
            card={card}
            rowLabel={rowLabel}
            label={tableLabel}
            onRowClick={onRowClick}
            multiSelect={multiSelect}
            selectedIds={selectedIds}
            onToggleRow={handleToggleRow}
            selectedId={selectedId}
            locked={lockRowsOnSelect && selectionCount > 0}
            loading={loading}
            emptyContent={emptyContent}
          />
          {paginationProps && (
            <PaginationBar {...paginationProps} isMobile flat compact range={rangeOf} busy={loading && !sortedData.length} />
          )}
        </div>
        {/* On a phone the caption keeps its first half, as the mockup */}
        {footNote && <div className="lv-caption" data-testid="list-caption"><span>{footNote}</span></div>}
        </>
      ) : isMobile ? (
        <MobileCardList
          data={paginatedData}
          primaryCol={primaryCol}
          secondaryCol={secondaryCol}
          tertiaryCol={tertiaryCol}
          selectedId={selectedId}
          onRowClick={onRowClick}
          rowActions={rowActions}
          loading={loading}
          density={density}
          multiSelect={multiSelect}
          selectedIds={selectedIds}
          onToggleRow={handleToggleRow}
          onToggleAll={() => handleToggleAll(paginatedData)}
          rowClickOpens={list}
        />
      ) : list ? (
        <>
        <div className="lv-table-box">
          <ListTable
            data={paginatedData}
            columns={visibleColumns}
            selectedId={selectedId}
            onRowClick={onRowClick}
            rowActions={rowActions}
            rowLabel={rowLabel}
            label={tableLabel}
            sort={sort}
            onSort={handleSort}
            sortable={sortable}
            loading={loading}
            density={density}
            columnWidths={columnWidths}
            setColumnWidth={setColumnWidth}
            resetColumnWidth={resetColumnWidth}
            multiSelect={multiSelect}
            selectedIds={selectedIds}
            onToggleRow={handleToggleRow}
            onToggleAll={() => handleToggleAll(paginatedData)}
            openFromName={openFromName}
            locked={lockRowsOnSelect && selectionCount > 0}
            emptyContent={emptyContent}
            skeletonRows={Math.max(1, Math.min(paginationProps?.perPage || 12, 12))}
          />
          {/* The footer stays, loading and empty included */}
          {paginationProps ? (
            <PaginationBar {...paginationProps} isMobile={false} flat range={rangeOf} busy={loading && !sortedData.length} />
          ) : (
            <footer className="lv-footer">
              <span>{rangeOf({ start: sortedData.length ? 1 : 0, end: sortedData.length, total: sortedData.length })}</span>
            </footer>
          )}
        </div>
        <div className="lv-caption" data-testid="list-caption">
          <span>{footNote}</span>
          <span>{t('table.rowsNote', { px: ROW_PX[density] || ROW_PX.compact, count: visibleColumns.length })}</span>
        </div>
        </>
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
          density={density}
          columnWidths={columnWidths}
          setColumnWidth={setColumnWidth}
          resetColumnWidth={resetColumnWidth}
          multiSelect={multiSelect}
          selectedIds={selectedIds}
          onToggleRow={handleToggleRow}
          onToggleAll={() => handleToggleAll(paginatedData)}
        />
      )}
      
      {/* PAGINATION */}
      {!flat && paginationProps && sortedData.length > 0 && (
        <PaginationBar
          {...paginationProps}
          isMobile={isMobile}
          range={rangeOf}
        />
      )}
    </div>
  )
}

// =============================================================================
// SEARCH BAR + TOOLBAR
// =============================================================================

function SearchBar({ 
  flat = false,
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
  exportBusy,
  exportNotice,
  showExportMenu,
  setShowExportMenu,
  exportMenuRef,
  handleExportCSV,
  handleExportJSON,
  dataCount,
  // Density toggle
  densityStorageKey,
  density,
  cycleDensity,
  searchLabel,
  searchStatus,
  columnsNote,
}) {
  const { t } = useTranslation()
  // Toolbar button: flat and labelled in the list template, the compact square elsewhere
  const tool = (active) => (flat ? 'lv-btn' : cn(
    'flex items-center gap-1.5 h-7 px-2 rounded-md border text-xs font-medium transition-colors',
    active
      ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary'
      : 'border-border bg-bg-primary text-text-secondary hover:text-text-primary hover:border-border-hover'
  ))
  const shownFilters = (filters || []).filter(f => !f.hideControl)
  // Closing the presets menu also leaves the naming form
  const setPresetsOpen = useCallback((next) => {
    setShowPresetsMenu?.(next)
    if (!next) setShowSavePresetModal?.(false)
  }, [setShowPresetsMenu, setShowSavePresetModal])
  const presetsMenu = useToolbarMenu(Boolean(showPresetsMenu), setPresetsOpen)
  const exportMenu = useToolbarMenu(Boolean(showExportMenu), setShowExportMenu)
  return (
    <div className={flat ? 'shrink-0' : cn(
      'shrink-0 border-b border-border-op30',
      isMobile ? 'px-3 py-2 bg-secondary-op10' : 'px-4 py-2 bg-secondary-op30'
    )}>
      <div className={flat ? 'lv-toolbar' : 'flex items-center gap-2 flex-wrap'}>
        {/* List template: a full-width field whose placeholder names what is searched */}
        {searchable && flat && (
          <label className="lv-search">
            <MagnifyingGlass size={16} aria-hidden="true" />
            <span className="sr-only">{searchLabel || t('common.search')}</span>
            <input
              type="search"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholder}
              autoComplete="off"
              spellCheck={false}
            />
            {value && (
              <button type="button" className="lv-search-clear" aria-label={t('common.clear')} onClick={() => onChange('')}>
                <X size={14} weight="bold" aria-hidden="true" />
              </button>
            )}
          </label>
        )}
        {flat && searchStatus && <span className="lv-search-status" role="status">{searchStatus}</span>}
        {/* Search input - premium styling on mobile */}
        {searchable && !flat && (
          <div className={cn(
            "relative group flex-1 min-w-0",
            isMobile && "search-bar-premium"
          )}>
            <MagnifyingGlass 
              size={isMobile ? 14 : 16} 
              className={cn(
                "absolute left-2.5 top-1/2 -translate-y-1/2",
                isMobile 
                  ? "text-accent-primary-op60 group-focus-within:text-accent-primary"
                  : "text-text-tertiary group-focus-within:text-accent-primary",
                "transition-colors"
              )}
            />
            <input
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholder}
              className={cn(
                'w-full text-text-primary placeholder:text-text-tertiary',
                'transition-all duration-200',
                'focus:outline-none',
                isMobile 
                  ? 'h-9 pl-8 pr-3 text-sm bg-transparent border-none rounded-xl' 
                  : 'h-8 pl-9 pr-3 text-sm bg-bg-primary border border-border rounded-lg focus:ring-2 focus:ring-accent-primary-op30 focus:border-accent-primary hover:border-border-hover'
              )}
            />
            {value && (
              <button
                onClick={() => onChange('')}
                className={cn(
                  'absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md',
                  'text-text-tertiary hover:text-text-primary hover:bg-bg-hover',
                  'transition-all duration-150 p-1'
                )}
              >
                <X size={14} weight="bold" />
              </button>
            )}
          </div>
        )}
        
        {/* Filters (desktop only) */}
        {(flat || !isMobile) && shownFilters.length > 0 && (
          <div className={flat ? 'lv-tools' : 'flex items-center gap-2 shrink-0'}>
            {shownFilters.map((filter) => {
              // Boolean toggle filter -- a checkbox-style pill for the
              // "show/hide this class of row" case, where a multiSelect with
              // one option would read as a filter the user must unset rather
              // than a switch. `disabled` covers the case where turning it
              // off would empty the table.
              if (filter.type === 'toggle') {
                const checked = Boolean(filter.value)
                return (
                  <button
                    key={filter.key}
                    type="button"
                    role="switch"
                    aria-checked={checked}
                    disabled={filter.disabled}
                    onClick={() => { if (!filter.disabled) filter.onChange?.(!checked) }}
                    title={filter.disabled ? (filter.disabledReason || filter.label) : filter.label}
                    className={cn(
                      'h-7 px-2.5 inline-flex items-center gap-1.5 shrink-0',
                      'text-xs rounded-md border transition-colors',
                      filter.disabled
                        ? 'border-border text-text-tertiary opacity-50 cursor-not-allowed'
                        : checked
                          ? 'border-accent-primary-op50 bg-accent-primary-op10 text-text-primary'
                          : 'border-border text-text-secondary hover:text-text-primary'
                    )}
                  >
                    <span className={cn(
                      'w-3.5 h-3.5 rounded-sm border flex items-center justify-center shrink-0',
                      checked ? 'bg-accent-primary border-accent-primary' : 'border-text-tertiary'
                    )}>
                      {checked && <Check size={10} weight="bold" className="text-on-accent" />}
                    </span>
                    {filter.label}
                  </button>
                )
              }
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
                        filter.from && 'border-accent-primary-op50'
                      )}
                      title={filter.fromPlaceholder || t('table.fromDate')}
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
                        filter.to && 'border-accent-primary-op50'
                      )}
                      title={filter.toPlaceholder || t('table.toDate')}
                    />
                  </div>
                )
              }
              // Multi-select filter
              if (filter.type === 'multiSelect') {
                return (
                  <MultiSelectFilter
                    key={filter.key}
                    options={filter.options || []}
                    value={filter.value || []}
                    onChange={filter.onChange}
                    placeholder={filter.placeholder || t('common.all')}
                    className={flat ? 'lv-filter' : undefined}
                  />
                )
              }
              // Default: FilterSelect
              return (
                <FilterSelect
                  key={filter.key}
                  value={filter.value || ''}
                  onChange={filter.onChange}
                  placeholder={filter.placeholder || t('common.all')}
                  options={filter.options || []}
                  size="sm"
                />
              )
            })}
          </div>
        )}
        
        {flat && !isMobile && <span className="lv-divider" aria-hidden="true" />}

        {/* List template: the columns dialog; the columns that always show are not offered */}
        {flat && !isMobile && columns && columns.length > 0 && (
          <>
            <button type="button" className="lv-btn" onClick={() => setShowColumnMenu?.(true)} aria-haspopup="dialog">
              <ColumnsIcon size={17} />
              <span>{t('table.columns')}</span>
            </button>
            <ListDialog open={Boolean(showColumnMenu)} onOpenChange={(open) => setShowColumnMenu?.(open)}
              title={t('table.columnsDialogTitle')} testId="columns-dialog">
              {columnsNote && <p className="lv-dialog-note">{columnsNote}</p>}
              <div className="lv-dialog-list">
                {columns.filter((col) => !col.alwaysVisible).map((col) => (
                  <label key={col.key} className="lv-check-line">
                    <input type="checkbox" checked={!hiddenColumns?.includes(col.key)} onChange={() => toggleColumn?.(col.key)} />
                    {col.columnLabel || col.header || col.key}
                  </label>
                ))}
              </div>
              <div className="lv-dialog-actions">
                <button type="button" className="lv-btn is-primary" data-write="false" onClick={() => setShowColumnMenu?.(false)}>{t('table.done')}</button>
              </div>
            </ListDialog>
          </>
        )}
        {/* Column Selector (desktop only) */}
        {!flat && !isMobile && columns && columns.length > 0 && (
          <div className="relative shrink-0" ref={columnMenuRef}>
            <button
              type="button"
              onClick={() => setShowColumnMenu?.(!showColumnMenu)}
              className={tool(showColumnMenu)}
              title={t('table.customizeColumns')}
              aria-expanded={flat ? Boolean(showColumnMenu) : undefined}
            >
              <Columns size={flat ? 16 : 14} aria-hidden={flat ? 'true' : undefined} />
              {flat && <span>{t('table.columns')}</span>}
            </button>
            
            {/* Dropdown menu */}
            {showColumnMenu && (
              <div className="absolute right-0 top-full mt-1 z-50 w-48 rounded-lg border border-border bg-bg-primary shadow-lg py-1">
                <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider border-b border-border mb-1">
                  {t('table.showColumns')}
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
                        : 'border-accent-primary bg-accent-primary text-on-accent'
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
                      {t('table.showAllColumns')}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Density toggle (desktop only): in the list template a switch to the comfortable rows */}
        {flat && !isMobile && densityStorageKey && (
          <button type="button" onClick={cycleDensity} className="lv-btn is-icon is-bare"
            aria-label={t('table.densityComfortable')} aria-pressed={density === 'comfortable'} title={t('table.changeDensity')}>
            <RowsIcon size={16} />
          </button>
        )}
        {!flat && !isMobile && densityStorageKey && (
          <button
            type="button"
            onClick={cycleDensity}
            aria-label={t('table.density')}
            className={flat ? 'lv-btn is-icon' : cn(
              'flex items-center gap-1.5 h-7 px-2 rounded-md border text-xs font-medium transition-colors shrink-0',
              'border-border bg-bg-primary text-text-secondary hover:text-text-primary hover:border-border-hover'
            )}
            title={`${t('table.density')}: ${t(`table.${density}`)}`}
          >
            <Rows size={flat ? 16 : 14} weight={density === 'comfortable' ? 'fill' : density === 'default' ? 'duotone' : 'regular'} />
          </button>
        )}
        
        {/* Filter Presets (desktop only) */}
        {!isMobile && filterPresetsKey && (
          <div className="relative shrink-0" ref={presetsMenuRef}>
            <button
              type="button"
              ref={presetsMenu.buttonRef}
              onClick={() => setPresetsOpen(!showPresetsMenu)}
              onKeyDown={presetsMenu.onButtonKeyDown}
              // A bare icon like its neighbours until presets are saved and counted
              className={flat ? cn('lv-btn', !filterPresets?.length && 'is-icon is-bare') : tool(showPresetsMenu)}
              title={t('table.filterPresets')}
              aria-label={t('table.filterPresets')}
              aria-haspopup="menu"
              aria-expanded={Boolean(showPresetsMenu)}
            >
              <BookmarkSimple size={flat ? 16 : 14} aria-hidden="true" />
              {filterPresets?.length > 0 && (
                <span className="text-2xs bg-accent-primary-op20 text-accent-primary px-1 rounded" aria-hidden="true">
                  {filterPresets.length}
                </span>
              )}
            </button>

            {/* Presets: the mockup's pop menu; naming a new preset turns it into a small form */}
            {showPresetsMenu && (
              <div ref={presetsMenu.menuRef} tabIndex={-1}
                role={showSavePresetModal ? 'dialog' : 'menu'} aria-label={t('table.filterPresets')}
                className="ui-pop lv-tool-menu is-wide absolute right-0 z-50">
                <p className="ui-pop-heading" aria-hidden="true">{t('table.filterPresets')}</p>

                {/* Save current filter button */}
                {hasActiveFilters && !showSavePresetModal && (
                  <button type="button" role="menuitem" className="ui-pop-item" onClick={() => setShowSavePresetModal?.(true)}>
                    <span className="ui-pop-icon"><FloppyDisk size={15} aria-hidden="true" /></span>
                    {t('table.saveFilters')}
                  </button>
                )}

                {/* Save preset input */}
                {showSavePresetModal && (
                  <div className="lv-tool-menu-form">
                    <input
                      type="text"
                      value={presetName}
                      onChange={(e) => setPresetName?.(e.target.value)}
                      placeholder={t('table.presetName')}
                      aria-label={t('table.presetName')}
                      className="ui-control"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') savePreset?.()
                        // Escape leaves the form only; the menu answers the next one
                        if (e.key === 'Escape') { e.preventDefault(); setShowSavePresetModal?.(false) }
                      }}
                    />
                    <div className="lv-tool-menu-actions">
                      <button type="button" className="lv-btn" onClick={() => setShowSavePresetModal?.(false)}>
                        {t('common.cancel')}
                      </button>
                      <button type="button" className="lv-btn is-primary" onClick={savePreset} disabled={!presetName?.trim()}>
                        {t('common.save')}
                      </button>
                    </div>
                  </div>
                )}

                {/* Preset list: apply, and delete beside it (Left and Right move between the two) */}
                {filterPresets?.length > 0 ? (
                  <>
                    {hasActiveFilters && !showSavePresetModal && <div className="ui-pop-sep" role="separator" />}
                    {!showSavePresetModal && filterPresets.map(preset => (
                      <div key={preset.id} className="lv-tool-menu-line" role="none">
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => applyPreset?.(preset)}
                          className="ui-pop-item"
                          title={Object.entries(preset.filters || {}).map(([k, v]) => `${k}: ${v}`).join(', ')}
                        >
                          <span className="ui-pop-icon"><BookmarkSimple size={15} aria-hidden="true" /></span>
                          <span className="ui-pop-label">{preset.name}</span>
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          onClick={(e) => {
                            e.stopPropagation()
                            deletePreset?.(preset.id)
                          }}
                          className="ui-pop-item lv-tool-menu-delete"
                          aria-label={t('table.deletePreset', { name: preset.name })}
                          title={t('table.deletePreset', { name: preset.name })}
                        >
                          <Trash size={14} aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </>
                ) : !hasActiveFilters && (
                  <p className="lv-tool-menu-empty">
                    {t('table.noPresets')}<br/>
                    {t('table.applyAndSave')}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Export Button (desktop only) */}
        {(flat || !isMobile) && exportNotice && (
          <span role="status" className="text-2xs text-status-warning shrink-0">
            {t(exportNotice.key, exportNotice.values)}
          </span>
        )}
        {(flat || !isMobile) && exportEnabled && (flat || dataCount > 0) && (
          <div className="relative shrink-0" ref={exportMenuRef}>
            <button
              type="button"
              ref={exportMenu.buttonRef}
              onClick={() => setShowExportMenu?.(!showExportMenu)}
              onKeyDown={exportMenu.onButtonKeyDown}
              className={flat ? 'lv-btn is-icon is-bare' : tool(showExportMenu)}
              title={t('table.exportData')}
              aria-label={t('table.exportData')}
              aria-haspopup="menu"
              aria-expanded={Boolean(showExportMenu)}
            >
              {flat ? <DownloadSimple size={16} aria-hidden="true" /> : <Export size={14} aria-hidden="true" />}
            </button>

            {/* Export: the mockup's pop menu, the count in its heading */}
            {showExportMenu && (
              <div ref={exportMenu.menuRef} tabIndex={-1} role="menu" aria-label={t('table.exportData')}
                className="ui-pop lv-tool-menu absolute right-0 z-50">
                <p className="ui-pop-heading" aria-hidden="true">
                  {exportBusy ? t('table.exporting') : t('table.exportItems', { count: dataCount })}
                </p>
                <button type="button" role="menuitem" onClick={handleExportCSV} disabled={exportBusy} className="ui-pop-item">
                  <span className="ui-pop-icon"><Export size={15} aria-hidden="true" /></span>
                  {t('table.exportCSV')}
                </button>
                <button type="button" role="menuitem" onClick={handleExportJSON} disabled={exportBusy} className="ui-pop-item">
                  <span className="ui-pop-icon"><Export size={15} aria-hidden="true" /></span>
                  {t('table.exportJSON')}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Actions - same height as search bar on mobile. Wraps when the
            available width is too narrow (e.g. split-view with detail panel)
            instead of forcing a horizontal scrollbar. */}
        {actions && (
          <div className={cn(
            "flex items-center gap-2 flex-wrap justify-end",
            isMobile && "[&>button]:h-9 [&>button]:px-3 [&>button]:text-xs"
          )}>
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
  loading,
  density = 'compact',
  columnWidths = {},
  setColumnWidth,
  resetColumnWidth,
  multiSelect,
  selectedIds,
  onToggleRow,
  onToggleAll
}) {
  // Resizing state
  const [resizingColumn, setResizingColumn] = useState(null)
  const resizeStartX = useRef(0)
  const resizeStartWidth = useRef(0)
  const tableRef = useRef(null)
  
  // Check if any column has a custom width
  
  // Density-based padding for rows
  const densityStyles = {
    // Row heights of the mockup's table view: 36, 40 and 44 px (`--ui-row`)
    compact: { cell: '', header: '', row: '36px' },
    default: { cell: '', header: '', row: '40px' },
    comfortable: { cell: '', header: '', row: '44px' }
  }
  const dStyle = densityStyles[density] || densityStyles.compact
  
  // Column sizing: table-layout:fixed with proportional widths
  // Each column gets a "size" weight. Total weights are summed and each column
  // gets a percentage of the available space. This is how TanStack Table works.
  // User-resized columns use exact px widths, remaining space is redistributed.
  // Width of the row-actions column, from what it actually holds: each button is
  // w-6 with a gap-0.5 between them, inside a px-2 cell. Without reserving it the
  // data columns take the whole 100% and the buttons overlap the last one.
  const actionsWidth = (() => {
    if (!rowActions) return 0
    const counts = data.slice(0, 20).map(r => rowActions(r)?.length || 0)
    const n = counts.length ? Math.max(...counts) : 0
    return n ? n * 24 + (n - 1) * 2 + 16 : 0
  })()

  // That width has to become a percentage: under table-layout:fixed a column width
  // given as calc() mixing % and px is dropped, and every column ends up equal.
  const [tableWidth, setTableWidth] = useState(0)
  useEffect(() => {
    const el = tableRef.current
    if (!el || !actionsWidth || typeof ResizeObserver === 'undefined') return
    const measure = () => setTableWidth(el.clientWidth)
    measure()
    let ro
    try {
      ro = new ResizeObserver(measure)
      ro.observe(el)
    } catch {
      return   // no usable observer: the one measurement above still holds
    }
    return () => ro.disconnect()
  }, [actionsWidth])
  const actionsShare = tableWidth > actionsWidth ? actionsWidth / tableWidth : 0

  const getColStyle = (col) => {
    // User-resized: use exact px width
    if (columnWidths[col.key]) {
      return { width: `${columnWidths[col.key]}px` }
    }
    // Column has explicit width (e.g. '120px', '80px') — lock it
    if (col.width) return { width: col.width, minWidth: col.width, maxWidth: col.width }
    // Use proportional sizing based on column "size" hint or smart defaults
    const size = col.size || getDefaultColumnSize(col)
    const totalSize = columns.reduce((sum, c) => {
      if (columnWidths[c.key] || c.width) return sum // fixed-width cols excluded from proportion
      return sum + (c.size || getDefaultColumnSize(c))
    }, 0)
    if (totalSize > 0) {
      const ratio = (size / totalSize) * (1 - actionsShare)
      return { width: `${(ratio * 100).toFixed(2)}%` }
    }
    return {}
  }
  
  // Smart default column sizes based on key name patterns
  function getDefaultColumnSize(col) {
    const k = col.key?.toLowerCase() || ''
    // Name/subject/description columns get more space
    if (k.includes('name') || k.includes('cn') || k.includes('subject') || k.includes('descr') || k.includes('description') || k.includes('email') || k.includes('domain')) return 3
    // Medium columns
    if (k.includes('issuer') || k.includes('organization')) return 2
    // Narrow columns: status, dates, types, booleans
    if (k.includes('status') || k.includes('type') || k.includes('role') || k.includes('active') || k.includes('enabled')) return 1
    if (k.includes('date') || k.includes('valid') || k.includes('created') || k.includes('expires') || k.includes('login') || k.includes('timestamp')) return 1.5
    if (k.includes('key') || k.includes('serial') || k.includes('id') || k.includes('count') || k.includes('days')) return 1
    // Default
    return 1.5
  }
  
  // Handle resize start
  const handleResizeStart = useCallback((e, colKey) => {
    e.preventDefault()
    e.stopPropagation()
    
    // Get the th element to measure its current width
    const th = e.target.closest('th')
    if (!th) return
    
    resizeStartX.current = e.clientX
    resizeStartWidth.current = th.offsetWidth
    setResizingColumn(colKey)
  }, [])
  
  // Handle resize move
  useEffect(() => {
    if (!resizingColumn) return
    
    const handleMouseMove = (e) => {
      const diff = e.clientX - resizeStartX.current
      const newWidth = Math.max(50, resizeStartWidth.current + diff) // Minimum 50px
      setColumnWidth(resizingColumn, newWidth)
    }
    
    const handleMouseUp = () => {
      setResizingColumn(null)
    }
    
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [resizingColumn, setColumnWidth])

  return (
    <div className="flex-1 overflow-auto" ref={tableRef}>
      <table 
        className={cn("ui-table", resizingColumn && "select-none")} 
        style={{ tableLayout: 'fixed', borderCollapse: 'separate', borderSpacing: 0, '--ui-row': dStyle.row }}
      >
        {/* Header: the mockup's table view, 34 px on the raised surface */}
        <thead className="sticky top-0 z-10">
          <tr>
            {multiSelect && (
              <th className="w-10 min-w-[40px] !px-1.5">
                <input
                  type="checkbox"
                  checked={data.length > 0 && data.every(r => selectedIds?.has(r.id))}
                  onChange={onToggleAll}
                  className="w-4 h-4 rounded border-border text-accent-primary cursor-pointer"
                />
              </th>
            )}
            {columns.map((col, colIdx) => {
              const style = getColStyle(col)
              const isLast = colIdx === columns.length - 1 && !rowActions
              return (
                <th
                  key={col.key}
                  onClick={() => sortable && col.sortable !== false && onSort(col.key)}
                  style={style}
                  className={cn(
                    'text-left relative group',
                    col.compact && '!px-1',
                    sortable && col.sortable !== false && 'cursor-pointer hover:text-text-primary',
                    sort?.key === col.key && '!text-text-primary'
                  )}
                >
                  <div className={cn("flex items-center gap-1.5 truncate", col.compact ? 'justify-center pr-0' : 'pr-3')}>
                    {col.header || col.label}
                    {sort?.key === col.key && (
                      sort.direction === 'asc' 
                        ? <CaretUp size={10} weight="bold" className="text-accent-primary" />
                        : <CaretDown size={10} weight="bold" className="text-accent-primary" />
                    )}
                  </div>
                  {/* Resize handle */}
                  {setColumnWidth && !isLast && (
                    <div 
                      className={cn(
                        "absolute right-0 top-0 h-full w-2 cursor-col-resize -mr-1 z-10",
                        "bg-transparent hover:bg-accent-primary-op60",
                        "transition-all duration-150",
                        resizingColumn === col.key && "bg-accent-primary"
                      )}
                      onMouseDown={(e) => handleResizeStart(e, col.key)}
                      onDoubleClick={(e) => {
                        e.stopPropagation()
                        resetColumnWidth(col.key)
                      }}
                    />
                  )}
                </th>
              )
            })}
            {rowActions && (
              <th className="whitespace-nowrap" style={{ width: `${actionsWidth}px` }} />
            )}
          </tr>
        </thead>
        
        {/* Body */}
        <tbody className="border-b border-border">
          {loading ? (
            <tr>
              <td colSpan={columns.length + (rowActions ? 1 : 0) + (multiSelect ? 1 : 0)} className="py-12 text-center">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-8 h-8 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
                  <span className="text-xs text-text-secondary">Loading...</span>
                </div>
              </td>
            </tr>
          ) : (
            data.map((row, idx) => (
              <tr
                key={row.id || idx}
                onClick={() => multiSelect ? onToggleRow(row.id) : onRowClick?.(row)}
                className={cn(
                  'group group/row',
                  (onRowClick || multiSelect) && 'cursor-pointer',
                  // Opened row: selected surface and the accent edge; checked rows the surface only
                  selectedId === row.id && 'is-opened',
                  multiSelect && selectedIds?.has(row.id) && 'is-checked'
                )}>
                {multiSelect && (
                  <td className="w-10 min-w-[40px] !px-1.5">
                    <input
                      type="checkbox"
                      checked={selectedIds?.has(row.id) || false}
                      onChange={(e) => { e.stopPropagation(); onToggleRow(row.id) }}
                      onClick={(e) => e.stopPropagation()}
                      className="w-4 h-4 rounded border-border text-accent-primary cursor-pointer"
                    />
                  </td>
                )}
                {columns.map((col, colIdx) => {
                  const style = getColStyle(col)
                  // eslint-disable-next-line no-unused-vars
                  const isLast = colIdx === columns.length - 1 && !rowActions
                  return (
                    <td 
                      key={col.key}
                      style={style}
                      className={cn(
                        col.compact && '!px-1',
                        col.mono && "font-mono",
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
                  <td className="relative !px-2">
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
    <div className="flex items-center justify-end gap-0.5">
      {actions.map((action, i) => {
        const Icon = action.icon
        return (
          <button
            key={i}
            onClick={(e) => {
              e.stopPropagation()
              action.onClick?.()
            }}
            title={action.label}
            className={cn(
              'w-6 h-6 rounded-lg flex items-center justify-center',
              'transition-all duration-150',
              action.variant === 'danger'
                ? 'text-text-tertiary hover:text-status-danger hover:bg-status-danger-op10'
                : 'text-text-tertiary hover:text-accent-primary hover:bg-accent-primary-op10'
            )}
          >
            {Icon && <Icon size={15} weight="duotone" />}
          </button>
        )
      })}
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
  loading,
  multiSelect,
  selectedIds,
  onToggleRow,
  onToggleAll,
  // List template: the checkbox selects, a tap on the card still opens it
  rowClickOpens = false
}) {
  const { t } = useTranslation()
  const tapSelects = multiSelect && !rowClickOpens
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center py-12">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-3 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
          <span className="text-sm text-text-secondary">Loading...</span>
        </div>
      </div>
    )
  }
  
  return (
    <div className="flex-1 overflow-auto p-3">
      {/* Select all for mobile multi-select */}
      {multiSelect && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
          <input
            type="checkbox"
            checked={data.length > 0 && data.every(r => selectedIds?.has(r.id))}
            onChange={onToggleAll}
            className="w-4 h-4 rounded border-border text-accent-primary cursor-pointer"
          />
          <span className="text-xs text-text-secondary">{rowClickOpens ? t('table.selectPage') : t('common.selectAll')}</span>
        </div>
      )}
      {/* Gradient dividers instead of flat lines */}
      <div className="space-y-px">
        {data.map((row, idx) => (
          <div key={row.id || idx} className="flex items-center">
            {multiSelect && (
              <div className="pl-3 pr-1 py-2">
                <input
                  type="checkbox"
                  checked={selectedIds?.has(row.id) || false}
                  onChange={() => onToggleRow(row.id)}
                  className="w-4 h-4 rounded border-border text-accent-primary cursor-pointer"
                />
              </div>
            )}
            <div className="flex-1 min-w-0">
              {idx > 0 && <div className="divider-gradient mx-3" />}
              <MobileCardRow
                row={row}
                primaryCol={primaryCol}
                secondaryCol={secondaryCol}
                tertiaryCol={tertiaryCol}
                isSelected={tapSelects ? selectedIds?.has(row.id) : selectedId === row.id}
                onClick={() => tapSelects ? onToggleRow(row.id) : onRowClick?.(row)}
                actions={rowActions?.(row)}
              />
            </div>
          </div>
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
        'px-3 py-2.5 transition-all duration-150',
        'active:bg-bg-tertiary active:scale-[0.99]',
        // Selected state - uses theme color via CSS
        isSelected && 'mobile-row-selected'
      )}
    >
      <div className="flex items-start gap-2">
        {/* Main content */}
        <div className="flex-1 min-w-0 space-y-0.5">
          {/* Primary */}
          {primaryCol && (
            <div className={cn(
              "font-medium transition-colors text-sm",
              isSelected ? "text-accent-primary" : "text-text-primary"
            )}>
              {primaryCol.mobileRender 
                ? primaryCol.mobileRender(row[primaryCol.key], row)
                : primaryCol.render 
                  ? primaryCol.render(row[primaryCol.key], row)
                  : row[primaryCol.key]
              }
            </div>
          )}
          
          {/* Secondary - uses mobileRender if available */}
          {secondaryCol && (
            <div className="text-text-secondary">
              {secondaryCol.mobileRender 
                ? secondaryCol.mobileRender(row[secondaryCol.key], row)
                : secondaryCol.render 
                  ? secondaryCol.render(row[secondaryCol.key], row)
                  : row[secondaryCol.key]
              }
            </div>
          )}
          
          {/* Tertiary (badge/status) - uses mobileRender if available */}
          {tertiaryCol && (
            <div className="mt-1" data-tertiary-key={tertiaryCol.key}>
              {tertiaryCol.mobileRender 
                ? tertiaryCol.mobileRender(row[tertiaryCol.key], row)
                : tertiaryCol.render 
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

function PageJump({ page, totalPages, onChange }) {
  const { t } = useTranslation()
  const [value, setValue] = useState(String(page))
  useEffect(() => { setValue(String(page)) }, [page])
  const go = (e) => {
    e.preventDefault()
    const n = Math.min(totalPages, Math.max(1, parseInt(value, 10) || page))
    setValue(String(n))
    if (n !== page) onChange(n)
  }
  return (
    <form className="lv-page-jump" onSubmit={go} noValidate>
      <label className="lv-page-jump">
        <span>{t('table.page')}</span>
        <input type="number" min={1} max={totalPages} value={value} inputMode="numeric"
          aria-label={t('table.pageNumber')} onChange={(e) => setValue(e.target.value)} />
      </label>
      <span>{t('table.pageOf', { total: totalPages })}</span>
      {/* Going to a page reads: the write guard leaves it enabled */}
      <button type="submit" className="lv-btn" data-write="false">{t('table.goToPage')}</button>
    </form>
  )
}

// `compact`: a phone footer, « page / pages » without the page number field
function PaginationBar({ page, total, perPage, onChange, onPerPageChange, pageSizes = PAGE_SIZES, perPageLabel, isMobile, flat = false, compact = false, range, busy = false }) {
  const { t } = useTranslation()
  const totalPages = Math.ceil(total / perPage)
  const start = (page - 1) * perPage + 1
  const end = Math.min(page * perPage, total)
  const sizes = pageSizes.includes(perPage) ? pageSizes : [...pageSizes, perPage].sort((a, b) => a - b)
  const perPageSelect = onPerPageChange && (
    <FilterSelect
      value={String(perPage)}
      onChange={(val) => onPerPageChange(Number(val))}
      options={sizes.map(n => ({ value: String(n), label: t('table.perPage', { size: n }) }))}
      placeholder={t('table.perPage', { size: perPage })}
      size="sm"
    />
  )

  // List template: the range in words, a native page size, the pages (a page number to jump to beyond 20 pages)
  if (flat) {
    const pages = Math.max(1, totalPages)
    return (
      <footer className="lv-footer" aria-busy={busy || undefined}>
        <span>{busy ? <span className="lv-sk" style={{ width: 120 }} /> : range({ start: total ? start : 0, end, total })}</span>
        <div className="lv-footer-controls">
          {onPerPageChange && (
            <select className="lv-page-size" value={String(perPage)} aria-label={perPageLabel || t('table.perPageLabel')}
              onChange={(e) => onPerPageChange(Number(e.target.value))}>
              {sizes.map((n) => <option key={n} value={String(n)}>{t('table.perPage', { size: n })}</option>)}
            </select>
          )}
          <button type="button" className="lv-page-arrow" aria-label={t('table.previousPage')}
            onClick={() => onChange(page - 1)} disabled={page <= 1}>
            <CaretLeft aria-hidden="true" />
          </button>
          {pages > PAGE_JUMP_ABOVE && !compact
            ? <PageJump page={page} totalPages={pages} onChange={onChange} />
            : <span>{page} / {pages}</span>}
          <button type="button" className="lv-page-arrow" aria-label={t('table.nextPage')}
            onClick={() => onChange(page + 1)} disabled={page >= pages}>
            <CaretRight aria-hidden="true" />
          </button>
        </div>
      </footer>
    )
  }

  return (
    <div className={cn(
      'shrink-0 border-t border-border bg-secondary-op30',
      'flex items-center justify-between',
      isMobile ? 'px-4 py-2' : 'px-4 py-1'
    )}>
      {/* Info */}
      <p className={cn(
        'text-text-secondary font-medium',
        isMobile ? 'text-sm' : 'text-xs'
      )}>
        {range({ start, end, total })}
      </p>
      
      {/* Controls */}
      <div className={cn(
        'flex items-center',
        isMobile ? 'gap-2' : 'gap-1.5'
      )}>
        {/* Per page selector (desktop only) */}
        {!isMobile && perPageSelect}
        
        {/* Prev button */}
        <button
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          aria-label={t('table.previousPage')}
          className={cn(
            'rounded-lg flex items-center justify-center',
            'border border-border bg-bg-primary',
            'transition-all duration-150',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'enabled:hover:bg-accent-primary-op5 enabled:hover:border-accent-primary-op50 enabled:hover:text-accent-primary',
            'enabled:active:scale-95',
            isMobile ? 'w-11 h-11' : 'w-8 h-8'
          )}
        >
          <CaretLeft size={isMobile ? 20 : 16} weight="bold" />
        </button>
        
        {/* Page indicator */}
        <span className={cn(
          'px-3 py-1 rounded-md bg-tertiary-op50 text-text-primary font-medium',
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
          aria-label={t('table.nextPage')}
          className={cn(
            'rounded-lg flex items-center justify-center',
            'border border-border bg-bg-primary',
            'transition-all duration-150',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'enabled:hover:bg-accent-primary-op5 enabled:hover:border-accent-primary-op50 enabled:hover:text-accent-primary',
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
