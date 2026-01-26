import styles from './FiltersBar.module.css';

/**
 * FiltersBar - Reusable filters bar with select groups
 * Used in: CAs, Certificates, Activity
 */
export function FiltersBar({ children, className }) {
  return (
    <div className={`${styles.filtersBar} ${className || ''}`}>
      {children}
    </div>
  );
}

export function FilterGroup({ label, children, className }) {
  return (
    <div className={`${styles.filterGroup} ${className || ''}`}>
      {label && <label>{label}</label>}
      {children}
    </div>
  );
}
