import React from 'react';
import './Button.css';

/**
 * Button component - Pure CSS, no Mantine
 * Uses design-system.html button classes
 */
export const Button = ({ 
  children, 
  variant = 'default', 
  size = 'md',
  className = '', 
  disabled = false,
  type = 'button',
  onClick,
  ...props 
}) => {
  const baseClass = 'btn';
  const variantClass = variant !== 'default' ? `btn-${variant}` : '';
  const sizeClass = size !== 'md' ? `btn-${size}` : '';
  
  const classes = [
    baseClass,
    variantClass,
    sizeClass,
    disabled && 'btn-disabled',
    className
  ].filter(Boolean).join(' ');

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
};
