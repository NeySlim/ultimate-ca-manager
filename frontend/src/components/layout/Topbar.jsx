import { useLocation } from 'react-router-dom';
import { ThemePicker } from './ThemePicker';
import { classNames } from '../../utils/classNames';
import styles from './Topbar.module.css';

/**
 * Topbar Component
 * 
 * Layout:
 * - Left: Breadcrumb
 * - Center: (empty for now, could add global search)
 * - Right: ThemePicker + User menu
 * 
 * Height: 60px (dashboard reference)
 */

// Route to title mapping
const routeTitles = {
  '/': 'Dashboard',
  '/cas': 'Certificate Authorities',
  '/certificates': 'Certificates',
  '/csrs': 'Certificate Requests',
  '/templates': 'Certificate Templates',
  '/crl': 'CRL & OCSP',
  '/acme': 'ACME Service',
  '/scep': 'SCEP Service',
  '/import': 'Import',
  '/truststore': 'Trust Store',
  '/users': 'Users',
  '/activity': 'Activity Log',
  '/settings': 'Settings',
  '/profile': 'Profile',
};

export function Topbar() {
  const location = useLocation();
  const pageTitle = routeTitles[location.pathname] || 'UCM';

  return (
    <div className={styles.topbar}>
      <div className={styles.topbarLeft}>
        <h1 className={styles.pageTitle}>{pageTitle}</h1>
      </div>

      <div className={styles.topbarRight}>
        <ThemePicker />
        
        <button className={styles.userButton}>
          <i className="ph ph-user-circle" />
        </button>
      </div>
    </div>
  );
}

export default Topbar;
