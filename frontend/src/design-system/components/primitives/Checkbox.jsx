import React, { forwardRef } from 'react';
import styles from './Checkbox.module.css';

export const Checkbox = forwardRef(({ children, className, ...props }, ref) => (
  <label className={`${styles.checkbox} ${className || ''}`}>
    <input ref={ref} type="checkbox" className={styles.input} {...props} />
    <span className={styles.box}><svg className={styles.check} viewBox="0 0 12 10"><polyline points="1.5 6 4.5 9 10.5 1" /></svg></span>
    {children && <span className={styles.label}>{children}</span>}
  </label>
));
Checkbox.displayName = 'Checkbox';
