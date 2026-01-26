import React from 'react';
import styles from './Divider.module.css';

export function Divider({ vertical, className }) {
  return <div className={`${styles.divider} ${vertical ? styles.vertical : ''} ${className || ''}`} />;
}
