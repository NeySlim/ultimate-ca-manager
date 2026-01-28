/**
 * Table Component - Ultra-compact table with sorting, pagination
 */
import { useState } from 'react'
import { CaretUp, CaretDown } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { LoadingSpinner } from './LoadingSpinner'
import { EmptyState } from './EmptyState'
import { Pagination } from './Pagination'

export function Table({ 
  columns, 
  data, 
  loading = false,
  onRowClick,
  sortable = true,
  selectable = false,
  onSelectionChange,
  pagination,
  emptyMessage = 'No data available',
  selectedId = null,
  idKey = 'id'
}) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [selectedRows, setSelectedRows] = useState(new Set())

  const handleSort = (key) => {
    if (!sortable) return
    
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedRows(new Set(data.map((_, idx) => idx)))
      onSelectionChange?.(data)
    } else {
      setSelectedRows(new Set())
      onSelectionChange?.([])
    }
  }

  const handleSelectRow = (index, checked) => {
    const newSelection = new Set(selectedRows)
    if (checked) {
      newSelection.add(index)
    } else {
      newSelection.delete(index)
    }
    setSelectedRows(newSelection)
    onSelectionChange?.(data.filter((_, idx) => newSelection.has(idx)))
  }

  const sortedData = sortConfig.key 
    ? [...data].sort((a, b) => {
        const aVal = a[sortConfig.key]
        const bVal = b[sortConfig.key]
        if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
        if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
        return 0
      })
    : data

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner />
      </div>
    )
  }

  if (!data || data.length === 0) {
    return <EmptyState title={emptyMessage} />
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-bg-secondary border-b border-border z-10">
            <tr>
              {selectable && (
                <th className="w-8 px-2 py-2">
                  <input
                    type="checkbox"
                    checked={selectedRows.size === data.length}
                    onChange={(e) => handleSelectAll(e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                </th>
              )}
              {columns.map(col => (
                <th
                  key={col.key}
                  className={cn(
                    "px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider",
                    sortable && col.sortable !== false && "cursor-pointer hover:text-text-primary transition-colors select-none"
                  )}
                  onClick={() => sortable && col.sortable !== false && handleSort(col.key)}
                >
                  <div className="flex items-center gap-2">
                    <span>{col.label}</span>
                    {sortable && col.sortable !== false && sortConfig.key === col.key && (
                      sortConfig.direction === 'asc' 
                        ? <CaretUp size={12} weight="bold" />
                        : <CaretDown size={12} weight="bold" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sortedData.map((row, index) => {
              const isSelected = selectedId !== null && row[idKey] === selectedId
              
              return (
                <tr
                  key={index}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    "transition-colors",
                    onRowClick && "cursor-pointer hover:bg-bg-tertiary",
                    selectedRows.has(index) && "bg-bg-tertiary/50",
                    isSelected && "bg-accent/10 border-l-2 border-l-accent"
                  )}
                >
                {selectable && (
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={selectedRows.has(index)}
                      onChange={(e) => {
                        e.stopPropagation()
                        handleSelectRow(index, e.target.checked)
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded border-border bg-bg-tertiary"
                    />
                  </td>
                )}
                {columns.map(col => (
                  <td key={col.key} className="px-3 py-2 text-sm text-text-primary whitespace-nowrap">
                    {col.render ? col.render(row[col.key], row) : row[col.key]}
                  </td>
                ))}
              </tr>
            )
            })}
          </tbody>
        </table>
      </div>

      {pagination && (
        <div className="border-t border-border mt-auto">
          <Pagination {...pagination} />
        </div>
      )}
    </div>
  )
}
