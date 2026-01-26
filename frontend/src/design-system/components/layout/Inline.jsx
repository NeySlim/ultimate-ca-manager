import React from 'react';
import styles from './Inline.module.css';

export function Inline({ children, spacing = 'md', align = 'center', className }) {
  return <div className={`${styles.inline} ${styles[spacing]} ${styles[align]} ${className || ''}`}>{children}</div>;
}
