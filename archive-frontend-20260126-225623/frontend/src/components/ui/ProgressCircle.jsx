import React from 'react';
import styles from './ProgressCircle.module.css';

export const ProgressCircle = ({ 
  value = 0, // 0-100
  size = 120,
  strokeWidth = 8,
  label,
  showValue = true,
  color = 'var(--accent-primary)',
  className = ''
}) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (value / 100) * circumference;

  return (
    <div className={`${styles.container} ${className}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} className={styles.svg}>
        {/* Background circle */}
        <circle
          className={styles.circleBackground}
          stroke="var(--border-secondary)"
          fill="none"
          strokeWidth={strokeWidth}
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        
        {/* Progress circle */}
        <circle
          className={styles.circleProgress}
          stroke={color}
          fill="none"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          style={{
            strokeDasharray: circumference,
            strokeDashoffset: offset,
          }}
        />
      </svg>
      
      <div className={styles.content}>
        {showValue && (
          <div className={styles.value} style={{ color }}>
            {Math.round(value)}%
          </div>
        )}
        {label && <div className={styles.label}>{label}</div>}
      </div>
    </div>
  );
};

export default ProgressCircle;
