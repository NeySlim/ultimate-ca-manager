import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ResizableTable.css';

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
      <div className="rt-header">
        {columns.map((col) => (
          <div 
            key={col.key} 
            className="rt-th" 
            style={{ width: colWidths[col.key], minWidth: col.minWidth || 50 }}
          >
            <div className="rt-th-content">
              {col.label}
              {col.sortable && <span className="rt-sort-icon">↕</span>}
            </div>
            {/* Resize Handle */}
            <div 
              className={`rt-resize-handle ${resizing?.colKey === col.key ? 'active' : ''}`}
              onMouseDown={(e) => startResize(e, col)}
            />
          </div>
        ))}
      </div>

      {/* Table Body */}
      <div className="rt-body">
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
                  style={{ width: colWidths[col.key], minWidth: col.minWidth || 50 }}
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
