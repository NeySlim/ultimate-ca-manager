import { useState } from 'react';
import { classNames } from '../../utils/classNames';
import { Icon } from '../ui/Icon';
import styles from './DataTable.module.css';

/**
 * DataTable Component
 * 
 * Generic table with:
 * - Sortable columns (click header)
 * - Row hover states
 * - Empty state
 * - Loading state
 * 
 * Design reference: prototype-dashboard.html table styles
 * 
 * Usage:
 *   <DataTable
 *     columns={[
 *       { key: 'name', label: 'Name', sortable: true },
 *       { key: 'status', label: 'Status', render: (row) => <Badge>...</Badge> }
 *     ]}
 *     data={rows}
 *     onRowClick={(row) => ...}
 *   />
 */
export function DataTable({
  columns = [],
  data = [],
  onRowClick,
  loading = false,
  emptyText = 'No data available',
  className,
  itemsPerPage = 10,
}) {
  const [sortColumn, setSortColumn] = useState(null);
  const [sortDirection, setSortDirection] = useState('asc');
  const [currentPage, setCurrentPage] = useState(1);

  const handleSort = (column) => {
    if (!column.sortable) return;

    if (sortColumn === column.key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column.key);
      setSortDirection('asc');
    }
  };

  const sortedData = [...data].sort((a, b) => {
    if (!sortColumn) return 0;

    const aVal = a[sortColumn];
    const bVal = b[sortColumn];

    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  // Pagination
  const totalPages = Math.ceil(sortedData.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedData = sortedData.slice(startIndex, endIndex);

  const handlePrevPage = () => {
    if (currentPage > 1) setCurrentPage(currentPage - 1);
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) setCurrentPage(currentPage + 1);
  };

  if (loading) {
    return (
      <div className={styles.loadingState}>
        <Icon name="circle-notch" size={32} className={styles.spinner} />
        <div className={styles.loadingText}>Loading...</div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Icon name="database" size={48} color="tertiary" />
        <div className={styles.emptyText}>{emptyText}</div>
      </div>
    );
  }

  return (
    <div className={classNames(styles.tableWrapper, className)}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                onClick={() => handleSort(column)}
                className={classNames(
                  column.sortable && styles.sortable,
                  sortColumn === column.key && styles.sorted
                )}
              >
                <div className={styles.headerContent}>
                  <span>{column.label}</span>
                  {column.sortable && (
                    <Icon
                      name={
                        sortColumn === column.key
                          ? sortDirection === 'asc'
                            ? 'caret-up'
                            : 'caret-down'
                          : 'caret-up-down'
                      }
                      size={12}
                      className={styles.sortIcon}
                    />
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {paginatedData.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              onClick={() => onRowClick && onRowClick(row)}
              className={onRowClick && styles.clickable}
            >
              {columns.map((column) => (
                <td key={column.key}>
                  {column.render
                    ? column.render(row)
                    : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      
      {/* Pagination */}
      {totalPages > 1 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>
            <span>Showing {startIndex + 1}-{Math.min(endIndex, sortedData.length)} of {sortedData.length}</span>
          </div>
          <div className={styles.paginationControls}>
            <button 
              className={styles.paginationBtn} 
              onClick={handlePrevPage}
              disabled={currentPage === 1}
            >
              <Icon name="caret-left" size={14} />
            </button>
            <button 
              className={styles.paginationBtn}
              onClick={handleNextPage}
              disabled={currentPage === totalPages}
            >
              <Icon name="caret-right" size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default DataTable;
