import React from 'react';
import styles from './GradientBadge.module.css';

export function GradientBadge({ children, variant = 'blue', size = 'md', glow, className }) {
  return (
    <span className={`${styles.badge} ${styles[variant]} ${styles[size]} ${glow ? styles.glow : ''} ${className || ''}`}>
      {children}
    </span>
  );
}
