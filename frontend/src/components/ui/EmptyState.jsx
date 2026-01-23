import React from 'react';
import { Button } from './Button';
import styles from './EmptyState.module.css';

export const EmptyState = ({
  icon = 'ph-folder-open',
  title = 'No data',
  message = 'Get started by adding your first item',
  action,
  actionLabel = 'Add Item',
  onAction,
  illustration,
  className = ''
}) => {
  return (
    <div className={`${styles.container} ${className}`}>
      {illustration || (
        <div className={styles.iconContainer}>
          <i className={`ph ${icon} ${styles.icon}`}></i>
        </div>
      )}
      
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.message}>{message}</p>
      
      {onAction && (
        <Button variant="primary" icon="ph ph-plus" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
      
      {action}
    </div>
  );
};

export default EmptyState;
