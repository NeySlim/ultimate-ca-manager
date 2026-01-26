import React from 'react';
import styles from './Skeleton.module.css';

export function Skeleton({ width, height = 20, className }) {
  return <div className={`${styles.skeleton} ${className || ''}`} style={{ width, height }} />;
}
