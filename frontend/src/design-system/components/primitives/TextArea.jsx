import React, { forwardRef } from 'react';
import styles from './TextArea.module.css';

export const TextArea = forwardRef(({ error, className, rows = 4, ...props }, ref) => (
  <textarea ref={ref} rows={rows} className={`${styles.textarea} ${error ? styles.error : ''} ${className || ''}`} {...props} />
));
TextArea.displayName = 'TextArea';
