import React from 'react';
import styles from './Grid.module.css';

export function Grid({ children, cols = 2, gap = 'md', className }) {
  return <div className={`${styles.grid} ${styles['cols' + cols]} ${styles['gap' + gap]} ${className || ''}`}>{children}</div>;
}
