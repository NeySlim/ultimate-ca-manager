import React from 'react';
import { Skeleton } from './Skeleton';
import styles from './LoadingState.module.css';

const LoadingState = ({ 
  variant = 'spinner', // spinner, skeleton, card, table
  message = 'Loading...', 
  rows = 5 
}) => {
  if (variant === 'skeleton') {
    return <Skeleton />;
  }

  if (variant === 'card') {
    return <Skeleton variant="rectangular" width="100%" height={200} />;
  }

  if (variant === 'table') {
    return (
      <div>
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} width="100%" height={48} style={{ marginBottom: '8px' }} />
        ))}
      </div>
    );
  }

  // Default spinner variant
  return (
    <div className={styles.container}>
      <div className={styles.spinner}>
        <i className="ph ph-spinner"></i>
      </div>
      {message && <p className={styles.message}>{message}</p>}
    </div>
  );
};

export default LoadingState;
