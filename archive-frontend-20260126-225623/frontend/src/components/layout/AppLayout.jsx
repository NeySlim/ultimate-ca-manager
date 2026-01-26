import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar/Sidebar';
import Topbar from './TopBar/TopBar';
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
 * Auth is handled by router loader (no flash)
 * Design reference: prototype-dashboard.html
 */
export function AppLayout() {
  return (
    <div className={styles.appLayout}>
      <Sidebar />
      
      <div className={styles.mainContent}>
        <Topbar />
        
        <div className={styles.pageContent}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}

export default AppLayout;
