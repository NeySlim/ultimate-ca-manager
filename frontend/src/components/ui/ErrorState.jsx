import React from 'react';
import { Button } from './Button';
import styles from './ErrorState.module.css';

const ErrorState = ({ 
  message = 'An error occurred', 
  error, 
  onRetry,
  shake = false 
}) => {
  const errorMessage = error?.message || message;

  return (
    <div className={`${styles.container} ${shake ? styles.shake : ''}`}>
      <div className={styles.icon}>
        <i className="ph ph-warning-circle"></i>
      </div>
      <h3 className={styles.title}>Error</h3>
      <p className={styles.message}>{errorMessage}</p>
      {onRetry && (
        <Button variant="primary" icon="ph ph-arrow-clockwise" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
};

export default ErrorState;
