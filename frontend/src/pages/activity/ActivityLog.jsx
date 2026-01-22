import { useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { PageTopBar, FiltersBar, FilterGroup, SectionTabs, Tab } from '../../components/common';
import { useAccountActivity } from '../../hooks/useAccount';
import { exportTableData } from '../../utils/export';
import toast from 'react-hot-toast';
import styles from './ActivityLog.module.css';

/**
 * Activity Log Page
 * 
 * Reference: prototype-activity.html
 * - TopBar with title badge + export button
 * - Filter bar (date range, user, action type, search)
 * - Two tabs: Application Logs / PKI Operations
 * - Activity list with icon badges (success, error, warning, info, gradient)
 */
export function ActivityLog() {
  const [activeTab, setActiveTab] = useState('app-logs');

  const { data: activityResponse, isLoading, error } = useAccountActivity();

  const handleExport = () => {
    const allActivity = activityResponse?.data || [];
    if (allActivity.length === 0) {
      toast.error('No activity data to export');
      return;
    }
    exportTableData(allActivity, 'activity-logs-export', {
      format: 'csv',
      columns: ['timestamp', 'user', 'action', 'details', 'status', 'ip']
    });
    toast.success('Activity logs exported successfully');
  };

  if (isLoading) {
    return (
      <div className={styles.activityLog}>
        <PageTopBar
          icon="ph ph-clock-clockwise"
          title="Activity"
          badge={<Badge variant="neutral">Loading...</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading activity...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.activityLog}>
        <PageTopBar
          icon="ph ph-clock-clockwise"
          title="Activity"
          badge={<Badge variant="danger">Error</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading activity: {error.message}
        </div>
      </div>
    );
  }

  const allActivity = activityResponse?.data || [];
  const appLogs = allActivity.filter(log => log.category === 'app' || !log.category);
  const pkiOps = allActivity.filter(log => log.category === 'pki');

  const currentLogs = activeTab === 'app-logs' ? appLogs : pkiOps;

  const getIconClass = (type) => {
    switch (type) {
      case 'success': return styles.iconSuccess;
      case 'error': return styles.iconError;
      case 'warning': return styles.iconWarning;
      case 'info': return styles.iconInfo;
      case 'gradient': return styles.iconGradient;
      default: return styles.iconInfo;
    }
  };

  return (
    <div className={styles.activityLog}>
      <PageTopBar
        icon="ph ph-clock-clockwise"
        title="Activity"
        badge={<Badge variant="info">Real-time</Badge>}
        actions={<Button variant="default" icon="ph ph-download-simple" onClick={handleExport}>Export Logs</Button>}
      />

      <FiltersBar>
        <div className={styles.filterGroupDate}>
          <FilterGroup label="From">
            <input type="date" defaultValue="2024-01-01" />
          </FilterGroup>
          <FilterGroup label="To">
            <input type="date" defaultValue="2024-01-15" />
          </FilterGroup>
        </div>
        <FilterGroup label="User">
          <select>
            <option>All Users</option>
            <option>john.doe</option>
            <option>admin</option>
            <option>jane.smith</option>
          </select>
        </FilterGroup>
        <FilterGroup label="Action Type">
          <select>
            <option>All Actions</option>
            <option>Login</option>
            <option>Configuration</option>
            <option>User Management</option>
          </select>
        </FilterGroup>
        <FilterGroup label="Search">
          <input type="text" placeholder="Search activities..." />
        </FilterGroup>
      </FiltersBar>

      <SectionTabs>
        <Tab active={activeTab === 'app-logs'} onClick={() => setActiveTab('app-logs')}>
          Application Logs
        </Tab>
        <Tab active={activeTab === 'pki-ops'} onClick={() => setActiveTab('pki-ops')}>
          PKI Operations
        </Tab>
      </SectionTabs>

      <div className={styles.activityList}>
        {currentLogs.map((log, idx) => (
          <div key={idx} className={styles.activityItem}>
            <div className={`${styles.activityIcon} ${getIconClass(log.type)}`}>
              <i className={`ph ${log.icon}`}></i>
            </div>
            <div className={styles.activityContent}>
              <div className={styles.activityText} dangerouslySetInnerHTML={{ __html: log.text }} />
              <div className={styles.activityTime}>{log.time}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ActivityLog;
