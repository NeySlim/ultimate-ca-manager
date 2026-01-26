import React from 'react';
import styles from './Container.module.css';

export function Container({ children, size = 'xl', className }) {
  return <div className={`${styles.container} ${styles[size]} ${className || ''}`}>{children}</div>;
}
