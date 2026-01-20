import React from 'react';

/**
 * Badge component - Replaces Mantine Badge
 * Uses design-system.html badge classes
 */
export const Badge = ({ 
  children,
  variant = 'filled',
  color = 'default',
  size = 'md',
  className = '',
  ...props
}) => {
  const baseClass = 'badge';
  
  // Color mapping to design-system.html badge classes
  const colorMap = {
    default: '',
    success: 'badge-success',
    active: 'badge-active',
    warning: 'badge-warning',
    error: 'badge-error',
    info: 'badge-info',
    green: 'badge-success',
    blue: 'badge-info',
    red: 'badge-error',
    yellow: 'badge-warning'
  };

  const sizeMap = {
    xs: 'badge-xs',
    sm: 'badge-sm',
    md: '',
    lg: 'badge-lg'
  };

  const variantClass = variant === 'outline' ? 'badge-outline' : '';

  const classes = [
    baseClass,
    colorMap[color],
    sizeMap[size],
    variantClass,
    className
  ].filter(Boolean).join(' ');

  return <span className={classes} {...props}>{children}</span>;
};
