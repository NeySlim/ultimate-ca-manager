import React, { forwardRef } from 'react';
import styles from './Input.module.css';

export const Input = forwardRef(({ error, className, ...props }, ref) => (
  <input ref={ref} className={`${styles.input} ${error ? styles.error : ''} ${className || ''}`} {...props} />
));
Input.displayName = 'Input';
