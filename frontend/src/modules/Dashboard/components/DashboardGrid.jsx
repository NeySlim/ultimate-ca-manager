import React from 'react';
import './DashboardGrid.css';

/**
 * DashboardGrid Component
 * 
 * A responsive CSS Grid container for dashboard widgets.
 * Supports Grafana-style grid layout with resizable cells.
 * 
 * Props:
 *   - children: React elements (widgets) to display
 *   - editMode: boolean - if true, shows edit visual cues
 *   - gap: string - spacing between grid items (default: '16px')
 */
const DashboardGrid = ({ children, editMode = false, gap = '16px' }) => {
  return (
    <div 
      className={`dashboard-grid ${editMode ? 'edit-mode' : ''}`}
      style={{
        '--grid-gap': gap
      }}
    >
      {children}
    </div>
  );
};

export default DashboardGrid;
