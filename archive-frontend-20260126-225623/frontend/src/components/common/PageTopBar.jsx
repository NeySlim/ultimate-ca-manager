import styles from './PageTopBar.module.css';

/**
 * PageTopBar - Reusable page header component
 * Used across multiple pages (CAs, Certificates, CSRs, Templates, Users, Activity, ACME, SCEP)
 */
export function PageTopBar({ icon, title, badge, actions, children }) {
  return (
    <div className={styles.topbar}>
      <div className={styles.topbarTitle}>
        {icon && <i className={icon}></i>}
        {title}
        {badge}
      </div>
      {actions && <div className={styles.topbarActions}>{actions}</div>}
      {children}
    </div>
  );
}
