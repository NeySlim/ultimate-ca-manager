import React from 'react';
import { Badge } from './Badge';
import styles from './LoadingState.module.css';

const LoadingState = ({ message = 'Loading...', variant = 'neutral' }) => {
  return (
    <div className={styles.container}>
      <Badge variant={variant}>Loading</Badge>
      <p className={styles.message}>{message}</p>
      <div className={styles.spinner}>
        <i className="ph ph-spinner"></i>
      </div>
    </div>
  );
};

export default LoadingState;
