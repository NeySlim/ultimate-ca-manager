import { NavLink } from 'react-router-dom';
import { classNames } from '../../utils/classNames';
import styles from './Sidebar.module.css';

/**
 * Sidebar Component
 * 
 * Navigation avec 4 sections:
 * 1. Main - Dashboard
 * 2. Certificate Management - CAs, Certs, CSRs, Templates, CRL
 * 3. Protocols - ACME, SCEP
 * 4. System - Import, Trust Store, Users, Activity, Settings, Profile
 * 
 * Active state: bg-tertiary + border + gradient icon
 * Design reference: prototype-dashboard.html
 */
export function Sidebar() {
  const navSections = [
    {
      title: 'Main',
      items: [
        { path: '/', icon: 'ph-house', label: 'Dashboard' },
      ],
    },
    {
      title: 'Certificate Management',
      items: [
        { path: '/cas', icon: 'ph-tree-structure', label: 'Certificate Authorities' },
        { path: '/certificates', icon: 'ph-certificate', label: 'Certificates' },
        { path: '/csrs', icon: 'ph-file-text', label: 'Certificate Requests' },
        { path: '/templates', icon: 'ph-files', label: 'Certificate Templates' },
        { path: '/crl', icon: 'ph-list-checks', label: 'CRL & OCSP' },
      ],
    },
    {
      title: 'Protocols',
      items: [
        { path: '/acme', icon: 'ph-globe', label: 'ACME Service' },
        { path: '/scep', icon: 'ph-device-mobile', label: 'SCEP Service' },
      ],
    },
    {
      title: 'System',
      items: [
        { path: '/import', icon: 'ph-upload', label: 'Import' },
        { path: '/truststore', icon: 'ph-shield-check', label: 'Trust Store' },
        { path: '/users', icon: 'ph-users', label: 'Users' },
        { path: '/activity', icon: 'ph-clock-counter-clockwise', label: 'Activity Log' },
        { path: '/settings', icon: 'ph-gear', label: 'Settings' },
        { path: '/profile', icon: 'ph-user', label: 'Profile' },
      ],
    },
  ];

  return (
    <div className={styles.sidebar}>
      {/* Logo Header */}
      <div className={styles.sidebarHeader}>
        <div className={styles.logo}>UCM</div>
        <div className={styles.logoSubtitle}>Certificate Manager</div>
      </div>

      {/* Navigation */}
      <nav className={styles.sidebarNav}>
        {navSections.map((section) => (
          <div key={section.title} className={styles.navSection}>
            <div className={styles.navSectionTitle}>{section.title}</div>
            
            {section.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  classNames(
                    styles.navItem,
                    isActive && styles.active
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <i className={classNames('ph', item.icon, isActive && 'icon-gradient')} />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* User Card Footer */}
      <div className={styles.sidebarFooter}>
        <div className={styles.userCard}>
          <div className={styles.userAvatar}>A</div>
          <div className={styles.userInfo}>
            <div className={styles.userName}>Admin</div>
            <div className={styles.userRole}>Administrator</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Sidebar;
