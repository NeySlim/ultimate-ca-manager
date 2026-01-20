import React from 'react';
import './Grid.css';

/**
 * Grid Component (Global Layout System)
 * 
 * Standard 12-column grid for all pages.
 * Supports "Grafana-style" layout with resizable/draggable potential.
 */
const Grid = ({ children, editMode = false, gap = '16px', className = '' }) => {
  return (
    <div 
      className={`ui-grid ${editMode ? 'edit-mode' : ''} ${className}`}
      style={{
        '--grid-gap': gap
      }}
    >
      {children}
    </div>
  );
};

export default Grid;
