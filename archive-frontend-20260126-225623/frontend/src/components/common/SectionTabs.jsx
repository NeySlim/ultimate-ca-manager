import styles from './SectionTabs.module.css';

/**
 * SectionTabs - Reusable tabs component
 * Used in: CSRs, Activity, ACME, Import, Settings, Profile
 */
export function SectionTabs({ children }) {
  return <div className={styles.tabs}>{children}</div>;
}

export function Tab({ active, onClick, icon, children }) {
  return (
    <button
      className={`${styles.tab} ${active ? styles.active : ''}`}
      onClick={onClick}
    >
      {icon && <i className={icon}></i>}
      {children}
    </button>
  );
}
