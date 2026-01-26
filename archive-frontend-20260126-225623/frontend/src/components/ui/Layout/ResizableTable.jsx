import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ResizableTable.css';

import { CaretUp, CaretDown, CaretUpDown } from '@phosphor-icons/react';

/**
 * ResizableTable Component
 * 
 * Implements the "File Manager" style table from ca-tree-demo.html
 * - Div-based structure (flex/grid)
 * - Resizable columns with handles
 * - Custom scrolling
 * - Sticky header
 */
const ResizableTable = ({ 
  columns, 
  data, 
  onRowClick, 
  onSort,
  sortConfig = { key: null, direction: 'asc' },
  rowClassName,
  emptyMessage = "No items found" 
}) => {
  // Initialize column widths from props
  const [colWidths, setColWidths] = useState(() => {
    const widths = {};
    columns.forEach(col => {
      widths[col.key] = col.width || 150; // Default 150px
    });
    return widths;
  });

  const [resizing, setResizing] = useState(null); // { colKey, startX, startWidth }
  const tableRef = useRef(null);
  const headerRef = useRef(null);
  const bodyRef = useRef(null);

  // Sync Scroll
  useEffect(() => {
    const body = bodyRef.current;
    const header = headerRef.current;
    if (!body || !header) return;

    const handleScroll = () => {
      header.scrollLeft = body.scrollLeft;
    };

    body.addEventListener('scroll', handleScroll);
    return () => body.removeEventListener('scroll', handleScroll);
  }, []);

  // Mouse Move Handler (Global)
  const handleMouseMove = useCallback((e) => {
    if (!resizing) return;

    const diff = e.pageX - resizing.startX;
    const newWidth = Math.max(resizing.minWidth || 50, resizing.startWidth + diff);

    setColWidths(prev => ({
      ...prev,
      [resizing.colKey]: newWidth
    }));
  }, [resizing]);

  // Mouse Up Handler (Global)
  const handleMouseUp = useCallback(() => {
    if (resizing) {
      setResizing(null);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  }, [resizing]);

  useEffect(() => {
    if (resizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [resizing, handleMouseMove, handleMouseUp]);

  const startResize = (e, col) => {
    e.preventDefault();
    e.stopPropagation();
    setResizing({
      colKey: col.key,
      startX: e.pageX,
      startWidth: colWidths[col.key],
      minWidth: col.minWidth
    });
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <div className="resizable-table-container" ref={tableRef}>
      {/* Table Header */}
      <div className="rt-header" ref={headerRef}>
        {columns.map((col) => (
          <div 
            key={col.key} 
            className="rt-th" 
            style={{ 
              width: col.flex ? '100%' : colWidths[col.key], 
              minWidth: col.minWidth || 50, 
              flex: col.flex ? '1 1 auto' : `0 0 ${colWidths[col.key]}px`,
              maxWidth: col.flex ? 'none' : `${colWidths[col.key]}px`
            }}
          >
            <div 
              className="rt-th-content" 
              onClick={() => col.sortable && onSort && onSort(col.key)}
              style={{ cursor: col.sortable ? 'pointer' : 'default', userSelect: 'none' }}
            >
              {col.label}
              {col.sortable && (
                <span className="rt-sort-icon" style={{ marginLeft: 6, display: 'inline-flex', verticalAlign: 'middle' }}>
                   {sortConfig?.key === col.key ? (
                      sortConfig.direction === 'asc' ? <CaretUp size={12} weight="fill" /> : <CaretDown size={12} weight="fill" />
                   ) : (
                      <CaretUpDown size={12} color="var(--mantine-color-dimmed)" />
                   )}
                </span>
              )}
            </div>
            {/* Resize Handle - Only for non-flex columns */}
            {!col.flex && (
              <div 
                className={`rt-resize-handle ${resizing?.colKey === col.key ? 'active' : ''}`}
                onMouseDown={(e) => startResize(e, col)}
              />
            )}
          </div>
        ))}
      </div>

      {/* Table Body */}
      <div className="rt-body" ref={bodyRef}>
        {data.length === 0 ? (
          <div className="rt-empty">{emptyMessage}</div>
        ) : (
          data.map((row, rowIndex) => (
            <div 
              key={row.id || rowIndex} 
              className={`rt-row ${rowClassName ? rowClassName(row) : ''}`}
              onClick={() => onRowClick && onRowClick(row)}
            >
              {columns.map((col) => (
                <div 
                  key={`${row.id || rowIndex}-${col.key}`} 
                  className="rt-td"
                  style={{ 
                    width: col.flex ? '100%' : colWidths[col.key], 
                    minWidth: col.minWidth || 50, 
                    flex: col.flex ? '1 1 auto' : `0 0 ${colWidths[col.key]}px`,
                    maxWidth: col.flex ? 'none' : `${colWidths[col.key]}px`
                  }}
                >
                  {col.render ? col.render(row) : row[col.key]}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ResizableTable;
