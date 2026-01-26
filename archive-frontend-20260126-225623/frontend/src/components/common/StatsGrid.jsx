import styles from './StatsGrid.module.css';

/**
 * StatsGrid - Reusable stats grid container
 * Used in: CRL, TrustStore, SCEP, ACME
 */
export function StatsGrid({ children, columns = 3 }) {
  return (
    <div 
      className={styles.statsGrid} 
      style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}
    >
      {children}
    </div>
  );
}

export function StatCard({ value, label, icon, variant = 'default' }) {
  return (
    <div className={`${styles.statCard} ${styles[variant]}`}>
      {icon && <i className={icon}></i>}
      <div className={styles.statValue}>{value}</div>
      <div className={styles.statLabel}>{label}</div>
    </div>
  );
}
