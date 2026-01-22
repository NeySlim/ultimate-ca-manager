import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar/Sidebar';
import Topbar from './TopBar/TopBar';
import { DashboardLayoutProvider } from '../../contexts/DashboardLayoutContext';
import styles from './AppLayout.module.css';

/**
 * AppLayout Component
 * 
 * Main application layout:
 * - Sidebar (240px fixed, left)
 * - Main content (flex-1, right)
 *   - Topbar (60px height)
 *   - Page content (scrollable)
 * 
 * Design reference: prototype-dashboard.html
 */
export function AppLayout() {
  return (
    <DashboardLayoutProvider>
      <div className={styles.appLayout}>
        <Sidebar />
        
        <div className={styles.mainContent}>
          <Topbar />
          
          <div className={styles.pageContent}>
            <Outlet />
          </div>
        </div>
      </div>
    </DashboardLayoutProvider>
  );
}

export default AppLayout;
