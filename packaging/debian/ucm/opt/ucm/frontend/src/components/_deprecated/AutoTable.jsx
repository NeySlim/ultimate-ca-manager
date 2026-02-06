/**
 * AutoTable Component
 * Table with automatic height adjustment and pagination
 */
import { useState, useEffect, useCallback } from 'react'
import { Table } from './Table'
import { useAutoPageSize } from '../hooks/useAutoPageSize'

export function AutoTable({
  columns,
  data,
  loading = false,
  onRowClick,
  sortable = true,
  selectable = false,
  onSelectionChange,
  emptyMessage,
  selectedId,
  idKey = 'id',
  // Pagination props
  total,
  page: externalPage,
  onPageChange,
  defaultPerPage = 20,
  autoHeight = true
}) {
  const [internalPage, setInternalPage] = useState(1)
  const page = externalPage ?? internalPage
  
  const {
    containerRef,
    perPage,
    autoMode,
    setMode,
    setPerPage
  } = useAutoPageSize({
    defaultPerPage,
    mode: autoHeight ? 'auto' : 'fixed'
  })

  // Reset to page 1 when perPage changes
  useEffect(() => {
    const handlePageChange = onPageChange ?? setInternalPage
    handlePageChange(1)
  }, [perPage])

  const handlePageChange = useCallback((newPage) => {
    if (onPageChange) {
      onPageChange(newPage)
    } else {
      setInternalPage(newPage)
    }
  }, [onPageChange])

  const handlePerPageChange = useCallback((value) => {
    if (value === 'auto') {
      setMode('auto')
    } else {
      setPerPage(value)
    }
  }, [setMode, setPerPage])

  // Client-side pagination if no total provided
  const actualTotal = total ?? data.length
  const paginatedData = total !== undefined 
    ? data // Server-side pagination, data already paginated
    : data.slice((page - 1) * perPage, page * perPage)

  return (
    <div ref={containerRef} className="flex flex-col h-full min-h-0">
      <Table
        columns={columns}
        data={paginatedData}
        loading={loading}
        onRowClick={onRowClick}
        sortable={sortable}
        selectable={selectable}
        onSelectionChange={onSelectionChange}
        emptyMessage={emptyMessage}
        selectedId={selectedId}
        idKey={idKey}
        pagination={{
          total: actualTotal,
          page,
          perPage,
          onChange: handlePageChange,
          onPerPageChange: handlePerPageChange,
          autoMode
        }}
      />
    </div>
  )
}
