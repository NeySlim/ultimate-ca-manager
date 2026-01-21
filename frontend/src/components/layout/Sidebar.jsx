import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  House, 
  TreeStructure, 
  Certificate, 
  FileText, 
  Files, 
  ListChecks, 
  Globe, 
  DeviceMobile, 
  Upload, 
  ShieldCheck, 
  Users, 
  ClockCounterClockwise, 
  Gear, 
  User,
  CaretDown,
  SignOut
} from '@phosphor-icons/react';
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
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const navigate = useNavigate();

  const navSections = [
    {
      title: 'Main',
      items: [
        { path: '/', icon: House, label: 'Dashboard' },
      ],
    },
    {
      title: 'Certificate Management',
      items: [
        { path: '/cas', icon: TreeStructure, label: 'Certificate Authorities' },
        { path: '/certificates', icon: Certificate, label: 'Certificates' },
        { path: '/csrs', icon: FileText, label: 'Certificate Requests' },
        { path: '/templates', icon: Files, label: 'Certificate Templates' },
        { path: '/crl', icon: ListChecks, label: 'CRL & OCSP' },
      ],
    },
    {
      title: 'Protocols',
      items: [
        { path: '/acme', icon: Globe, label: 'ACME Service' },
        { path: '/scep', icon: DeviceMobile, label: 'SCEP Service' },
      ],
    },
    {
      title: 'System',
      items: [
        { path: '/import', icon: Upload, label: 'Import' },
        { path: '/truststore', icon: ShieldCheck, label: 'Trust Store' },
        { path: '/users', icon: Users, label: 'Users' },
        { path: '/activity', icon: ClockCounterClockwise, label: 'Activity Log' },
        { path: '/settings', icon: Gear, label: 'Settings' },
      ],
    },
  ];

  const handleLogout = () => {
    // TODO: Implement logout
    console.log('Logout');
  };

  return (
    <div className={styles.sidebar}>
      {/* Logo Header */}
      <div className={styles.sidebarHeader}>
        <div className={styles.logo}>UCM</div>
        <div className={styles.logoSubtitle}>v2.1</div>
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
                    <item.icon 
                      size={18} 
                      weight={isActive ? "fill" : "regular"}
                      className={isActive ? 'icon-gradient' : ''} 
                    />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* User Card Footer with Dropdown */}
      <div className={styles.sidebarFooter}>
        <div 
          className={styles.userCard}
          onClick={() => setUserMenuOpen(!userMenuOpen)}
        >
          <div className={styles.userAvatar}>A</div>
          <div className={styles.userInfo}>
            <div className={styles.userName}>Admin</div>
            <div className={styles.userRole}>Administrator</div>
          </div>
          <CaretDown size={12} style={{ marginLeft: 'auto', color: 'var(--text-muted)' }} />
        </div>

        {/* User Dropdown Menu */}
        {userMenuOpen && (
          <div className={styles.userMenu}>
            <button 
              className={styles.userMenuItem}
              onClick={(e) => {
                e.stopPropagation();
                navigate('/profile');
                setUserMenuOpen(false);
              }}
            >
              <User size={16} />
              <span>Profile</span>
            </button>
            <button 
              className={styles.userMenuItem}
              onClick={(e) => {
                e.stopPropagation();
                navigate('/settings');
                setUserMenuOpen(false);
              }}
            >
              <Gear size={16} />
              <span>Settings</span>
            </button>
            <div className={styles.userMenuDivider} />
            <button 
              className={styles.userMenuItem}
              onClick={(e) => {
                e.stopPropagation();
                handleLogout();
                setUserMenuOpen(false);
              }}
            >
              <SignOut size={16} />
              <span>Logout</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default Sidebar;
