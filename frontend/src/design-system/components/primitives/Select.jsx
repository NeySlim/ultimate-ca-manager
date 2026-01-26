import React, { forwardRef } from 'react';
import styles from './Select.module.css';

export const Select = forwardRef(({ children, className, ...props }, ref) => (
  <select ref={ref} className={`${styles.select} ${className || ''}`} {...props}>{children}</select>
));
Select.displayName = 'Select';
