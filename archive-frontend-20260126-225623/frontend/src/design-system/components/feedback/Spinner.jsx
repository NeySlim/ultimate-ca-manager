import React from 'react';
import styles from './Spinner.module.css';

export function Spinner({ size = 'md' }) {
  return <div className={`${styles.spinner} ${styles[size]}`} />;
}
