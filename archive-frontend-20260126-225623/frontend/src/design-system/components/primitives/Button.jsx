import React, { forwardRef } from 'react';
import styles from './Button.module.css';

export const Button = forwardRef(({ 
  children, variant = 'primary', size = 'md', loading, disabled, className, ...props 
}, ref) => {
  const classes = [
    styles.button,
    styles[variant],
    styles[size],
    loading && styles.loading,
    className
  ].filter(Boolean).join(' ');

  return (
    <button ref={ref} className={classes} disabled={disabled || loading} {...props}>
      {loading ? <span className={styles.spinner} /> : children}
    </button>
  );
});

Button.displayName = 'Button';
