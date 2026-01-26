import React from 'react';
import './Tooltip.css';

/**
 * Tooltip - Simple title attribute wrapper
 * Replaces Mantine Tooltip (simplified)
 */
export const Tooltip = ({ label, children }) => {
  return (
    <span title={label} className="tooltip-wrapper">
      {children}
    </span>
  );
};
