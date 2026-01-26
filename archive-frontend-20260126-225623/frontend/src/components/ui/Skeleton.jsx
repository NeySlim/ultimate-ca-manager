import React from 'react';
import styles from './Skeleton.module.css';

export const Skeleton = ({ 
  variant = 'text', // text, circular, rectangular
  width,
  height,
  className = '',
  ...props 
}) => {
  const style = {
    width: width || (variant === 'text' ? '100%' : undefined),
    height: height || (variant === 'text' ? '1em' : undefined),
  };

  const variantClass = styles[variant] || styles.text;

  return (
    <div 
      className={`${styles.skeleton} ${variantClass} ${className}`}
      style={style}
      {...props}
    />
  );
};

export const SkeletonCard = () => (
  <div className={styles.card}>
    <div className={styles.header}>
      <Skeleton variant="circular" width={40} height={40} />
      <div className={styles.headerText}>
        <Skeleton width="60%" height={16} />
        <Skeleton width="40%" height={12} />
      </div>
    </div>
    <div className={styles.body}>
      <Skeleton width="100%" height={12} />
      <Skeleton width="90%" height={12} />
      <Skeleton width="95%" height={12} />
    </div>
  </div>
);

export const SkeletonTable = ({ rows = 5 }) => (
  <div className={styles.table}>
    <div className={styles.tableHeader}>
      <Skeleton width="100%" height={32} />
    </div>
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className={styles.tableRow}>
        <Skeleton width="25%" height={16} />
        <Skeleton width="30%" height={16} />
        <Skeleton width="20%" height={16} />
        <Skeleton width="25%" height={16} />
      </div>
    ))}
  </div>
);

export const SkeletonDashboard = () => (
  <div className={styles.dashboard}>
    <div className={styles.stats}>
      {[1, 2, 3, 4].map(i => (
        <div key={i} className={styles.statCard}>
          <Skeleton width="40%" height={12} />
          <Skeleton width="60%" height={24} />
        </div>
      ))}
    </div>
    <SkeletonCard />
    <SkeletonCard />
  </div>
);
