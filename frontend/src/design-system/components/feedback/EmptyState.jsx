import React from 'react';
import styles from './EmptyState.module.css';

export function EmptyState({ icon, title, description, action, className }) {
  return (
    <div className={`${styles.empty} ${className || ''}`}>
      {icon && <div className={styles.icon}>{icon}</div>}
      {title && <h3 className={styles.title}>{title}</h3>}
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
