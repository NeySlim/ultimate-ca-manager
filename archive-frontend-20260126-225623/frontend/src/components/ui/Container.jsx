import React from 'react';

/**
 * Container - Simple max-width wrapper
 * Replaces Mantine Container
 */
export const Container = ({ children, size = 'lg', className = '', ...props }) => {
  const sizeMap = {
    xs: '540px',
    sm: '720px',
    md: '960px',
    lg: '1140px',
    xl: '1320px'
  };

  return (
    <div
      className={`container ${className}`}
      style={{
        maxWidth: sizeMap[size],
        marginLeft: 'auto',
        marginRight: 'auto',
        padding: '0 var(--spacing-lg)',
        ...props.style
      }}
      {...props}
    >
      {children}
    </div>
  );
};
