import React from 'react';
import './ActionIcon.css';

/**
 * ActionIcon - Icon button
 * Replaces Mantine ActionIcon
 */
export const ActionIcon = ({ children, onClick, size = 'md', variant = 'default', className = '', ...props }) => {
  const sizeMap = {
    xs: 'action-icon-xs',
    sm: 'action-icon-sm',
    md: 'action-icon-md',
    lg: 'action-icon-lg'
  };

  return (
    <button
      className={`action-icon ${sizeMap[size]} action-icon-${variant} ${className}`}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
};
