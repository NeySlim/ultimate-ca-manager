import React from 'react';
import styles from './Alert.module.css';

export function Alert({ children, variant = 'info', onDismiss, className }) {
  return (
    <div className={`${styles.alert} ${styles[variant]} ${className || ''}`}>
      <div className={styles.content}>{children}</div>
      {onDismiss && <button className={styles.dismiss} onClick={onDismiss}>×</button>}
    </div>
  );
}
