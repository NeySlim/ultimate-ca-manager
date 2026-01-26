import React from 'react';
import styles from './GlassCard.module.css';

export function GlassCard({ children, blur = 'md', className, ...props }) {
  return (
    <div className={`${styles.glass} ${styles[blur]} ${className || ''}`} {...props}>
      {children}
    </div>
  );
}
