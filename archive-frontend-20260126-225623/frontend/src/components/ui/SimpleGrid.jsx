import React from 'react';
import './SimpleGrid.css';

/**
 * SimpleGrid - CSS Grid layout
 * Replaces Mantine SimpleGrid
 */
export const SimpleGrid = ({ children, cols = 2, spacing = 'md', className = '', ...props }) => {
  const spacingMap = {
    xs: 'var(--spacing-xs, 4px)',
    sm: 'var(--spacing-sm, 8px)',
    md: 'var(--spacing-md, 12px)',
    lg: 'var(--spacing-lg, 16px)',
    xl: 'var(--spacing-xl, 20px)'
  };

  return (
    <div
      className={`simple-grid ${className}`}
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gap: spacingMap[spacing] || spacing,
        ...props.style
      }}
      {...props}
    >
      {children}
    </div>
  );
};
