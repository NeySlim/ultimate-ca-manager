import React from 'react';
import styles from './Progress.module.css';

export function Progress({ value = 0, max = 100, variant = 'primary', size = 'md', showLabel, className }) {
  const percentage = Math.round((value / max) * 100);
  
  return (
    <div className={`${styles.wrapper} ${className || ''}`}>
      <div className={`${styles.progress} ${styles[size]}`}>
        <div className={`${styles.bar} ${styles[variant]}`} style={{ width: `${percentage}%` }} />
      </div>
      {showLabel && <span className={styles.label}>{percentage}%</span>}
    </div>
  );
}
