import React, { forwardRef } from 'react';
import styles from './Radio.module.css';

export const Radio = forwardRef(({ children, className, ...props }, ref) => (
  <label className={`${styles.radio} ${className || ''}`}>
    <input ref={ref} type="radio" className={styles.input} {...props} />
    <span className={styles.circle}><span className={styles.dot} /></span>
    {children && <span className={styles.label}>{children}</span>}
  </label>
));
Radio.displayName = 'Radio';
