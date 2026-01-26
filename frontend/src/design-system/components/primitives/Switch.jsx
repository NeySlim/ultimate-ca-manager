import React, { forwardRef } from 'react';
import styles from './Switch.module.css';

export const Switch = forwardRef(({ children, className, ...props }, ref) => (
  <label className={`${styles.switch} ${className || ''}`}>
    <input ref={ref} type="checkbox" className={styles.input} {...props} />
    <span className={styles.track}><span className={styles.thumb} /></span>
    {children && <span className={styles.label}>{children}</span>}
  </label>
));
Switch.displayName = 'Switch';
