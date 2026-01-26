import React from 'react';
import styles from './Card.module.css';

export function Card({ children, hover = true, gradient, className, ...props }) {
  return (
    <div 
      className={`${styles.card} ${hover ? styles.hover : ''} ${gradient ? styles.gradient : ''} ${className || ''}`}
      {...props}
    >
      {children}
    </div>
  );
}
