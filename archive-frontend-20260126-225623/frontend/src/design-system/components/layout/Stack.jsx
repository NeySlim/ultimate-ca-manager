import React from 'react';
import styles from './Stack.module.css';

export function Stack({ children, spacing = 'md', className }) {
  return <div className={`${styles.stack} ${styles[spacing]} ${className || ''}`}>{children}</div>;
}
