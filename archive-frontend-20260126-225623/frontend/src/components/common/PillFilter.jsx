import styles from './PillFilter.module.css';

/**
 * PillFilter - Reusable pill-shaped filter button
 * Used in: Certificates, Users
 */
export function PillFilter({ active, onClick, children }) {
  return (
    <button
      className={`${styles.filterPill} ${active ? styles.active : ''}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function PillFilters({ children, className }) {
  return (
    <div className={`${styles.filterPills} ${className || ''}`}>
      {children}
    </div>
  );
}
