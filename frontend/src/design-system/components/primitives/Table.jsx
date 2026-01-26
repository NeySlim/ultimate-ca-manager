import { useState, useMemo } from 'react';
import { 
  CaretUp, 
  CaretDown, 
  CaretUpDown,
  MagnifyingGlass,
  Download,
  Funnel
} from '@phosphor-icons/react';
import { Button } from '../primitives/Button';
import { Badge } from '../primitives/Badge';
import { Checkbox } from '../primitives/Checkbox';
import { EmptyState } from '../feedback/EmptyState';
import { Skeleton } from '../feedback/Skeleton';
import styles from './Table.module.css';

/**
 * Premium Table Component (Phase 5: Data Viz & Tables)
 * 
 * Features:
 * - Sortable columns
 * - Row selection with checkboxes
 * - Hover highlight smooth
 * - Striped rows
 * - Loading skeletons
 * - Empty state
 * - Bulk actions
 * - Export functionality
 */

export function Table({
  columns = [],
  data = [],
  isLoading = false,
  selectable = false,
  striped = true,
  hoverable = true,
  onRowClick,
  emptyMessage = 'No data available',
  emptyIcon,
}) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: null });
  const [selectedRows, setSelectedRows] = useState(new Set());

  // Sorting logic
  const sortedData = useMemo(() => {
    if (!sortConfig.key) return data;
    
    const sorted = [...data].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
    
    return sorted;
  }, [data, sortConfig]);

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedRows(new Set(data.map((_, idx) => idx)));
    } else {
      setSelectedRows(new Set());
    }
  };

  const handleSelectRow = (idx, checked) => {
    const newSelected = new Set(selectedRows);
    if (checked) {
      newSelected.add(idx);
    } else {
      newSelected.delete(idx);
    }
    setSelectedRows(newSelected);
  };

  const allSelected = data.length > 0 && selectedRows.size === data.length;
  const someSelected = selectedRows.size > 0 && selectedRows.size < data.length;

  // Loading state
  if (isLoading) {
    return (
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              {selectable && <th style={{ width: '40px' }}></th>}
              {columns.map((col, idx) => (
                <th key={idx}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...Array(5)].map((_, idx) => (
              <tr key={idx}>
                {selectable && <td><Skeleton width="16px" height="16px" /></td>}
                {columns.map((_, colIdx) => (
                  <td key={colIdx}><Skeleton height="20px" /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // Empty state
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={emptyIcon || <MagnifyingGlass size={48} />}
        title="No results"
        description={emptyMessage}
      />
    );
  }

  return (
    <div className={styles.tableContainer}>
      <table 
        className={styles.table}
        data-striped={striped}
        data-hoverable={hoverable}
      >
        <thead className={styles.thead}>
          <tr>
            {selectable && (
              <th className={styles.checkboxCell}>
                <Checkbox
                  checked={allSelected}
                  indeterminate={someSelected}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                />
              </th>
            )}
            {columns.map((col, idx) => (
              <th
                key={idx}
                className={col.sortable ? styles.sortableHeader : ''}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
                style={{ width: col.width }}
              >
                <div className={styles.headerContent}>
                  <span>{col.label}</span>
                  {col.sortable && (
                    <span className={styles.sortIcon}>
                      {sortConfig.key === col.key ? (
                        sortConfig.direction === 'asc' ? (
                          <CaretUp size={14} weight="bold" />
                        ) : (
                          <CaretDown size={14} weight="bold" />
                        )
                      ) : (
                        <CaretUpDown size={14} weight="bold" />
                      )}
                    </span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedData.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className={selectedRows.has(rowIdx) ? styles.selectedRow : ''}
              onClick={() => onRowClick?.(row, rowIdx)}
              style={{ cursor: onRowClick ? 'pointer' : 'default' }}
            >
              {selectable && (
                <td className={styles.checkboxCell}>
                  <Checkbox
                    checked={selectedRows.has(rowIdx)}
                    onChange={(e) => {
                      e.stopPropagation();
                      handleSelectRow(rowIdx, e.target.checked);
                    }}
                  />
                </td>
              )}
              {columns.map((col, colIdx) => (
                <td key={colIdx}>
                  {col.render ? col.render(row, rowIdx) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      
      {/* Bulk Actions Bar */}
      {selectable && selectedRows.size > 0 && (
        <div className={styles.bulkActions}>
          <div className={styles.bulkActionsContent}>
            <Badge variant="primary">{selectedRows.size} selected</Badge>
            <div className={styles.bulkActionsButtons}>
              <Button variant="secondary" size="sm" leftIcon={<Download size={16} />}>
                Export Selected
              </Button>
              <Button variant="danger" size="sm">
                Delete Selected
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Table;
