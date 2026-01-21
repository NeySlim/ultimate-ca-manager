import { useLocation } from 'react-router-dom';
import { Bell, MagnifyingGlass, Moon, Sun, UserCircle } from '@phosphor-icons/react';
import { ThemePicker } from './ThemePicker';
import { classNames } from '../../utils/classNames';
import styles from './Topbar.module.css';

/**
 * Topbar Component
 * 
 * Layout:
 * - Left: Breadcrumb/Page title
 * - Center: Command palette (search)
 * - Right: Theme toggle, Notifications, User menu
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

      {/* Center: Command Palette */}
      <div className={styles.topbarCenter}>
        <div className={styles.commandPalette}>
          <MagnifyingGlass size={14} />
          <input 
            type="text" 
            placeholder="Search resources..." 
            className={styles.commandInput}
          />
          <span className={styles.commandShortcut}>Ctrl+K</span>
        </div>
      </div>

      <div className={styles.topbarRight}>
        <ThemePicker />
        
        <button className={styles.actionButton} title="Notifications">
          <Bell size={18} />
        </button>
        
        <button className={styles.actionButton} title="User Menu">
          <UserCircle size={18} />
        </button>
      </div>
    </div>
  );
}

export default Topbar;
