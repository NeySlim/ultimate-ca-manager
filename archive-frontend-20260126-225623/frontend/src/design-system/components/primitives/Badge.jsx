import React from 'react';
import styles from './Badge.module.css';

export function Badge({ children, variant = 'default', size = 'md', className }) {
  return <span className={`${styles.badge} ${styles[variant]} ${styles[size]} ${className || ''}`}>{children}</span>;
}
