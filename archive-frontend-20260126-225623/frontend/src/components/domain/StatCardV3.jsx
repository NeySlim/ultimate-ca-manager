import React from 'react';
import { Stack, Badge } from '../../design-system';
import styles from './StatCardV3.module.css';

export function StatCardV3({ value, label, sublabel, icon, trend, variant = 'default', gradient }) {
  return (
    <div className={`${styles.card} ${gradient ? styles.gradient : ''} ${styles[variant]}`}>
      <Stack spacing="sm">
        <div className={styles.header}>
          <span className={styles.icon}>{icon}</span>
          {trend && (
            <Badge variant={trend.positive ? 'success' : 'warning'} size="sm">
              {trend.direction === 'up' ? '↑' : '↓'} {trend.text}
            </Badge>
          )}
        </div>
        
        <div className={styles.value}>{value}</div>
        
        <div className={styles.labels}>
          <div className={styles.label}>{label}</div>
          {sublabel && <div className={styles.sublabel}>{sublabel}</div>}
        </div>
      </Stack>
    </div>
  );
}
