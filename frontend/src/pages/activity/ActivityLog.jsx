import { useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
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

  const appLogs = [
    { type: 'success', icon: 'ph-sign-in', text: 'User <strong>john.doe</strong> logged in successfully', time: '2 minutes ago' },
    { type: 'info', icon: 'ph-gear', text: '<strong>admin</strong> regenerated HTTPS certificate for web interface', time: '15 minutes ago' },
    { type: 'success', icon: 'ph-user-plus', text: 'New user <strong>jane.smith</strong> created by <strong>admin</strong>', time: '32 minutes ago' },
    { type: 'warning', icon: 'ph-warning', text: 'Failed login attempt for user <strong>admin</strong> from IP 192.168.1.45', time: '1 hour ago' },
    { type: 'info', icon: 'ph-shield-check', text: '<strong>admin</strong> enabled mTLS authentication for API endpoints', time: '1 hour ago' },
    { type: 'success', icon: 'ph-sign-in', text: 'User <strong>admin</strong> logged in successfully', time: '2 hours ago' },
    { type: 'info', icon: 'ph-key', text: '<strong>john.doe</strong> rotated API key for integration service', time: '3 hours ago' },
    { type: 'info', icon: 'ph-user-gear', text: 'Role changed for user <strong>jane.smith</strong> from Operator to Admin', time: '3 hours ago' },
    { type: 'success', icon: 'ph-database', text: 'Database optimization completed successfully', time: '4 hours ago' },
    { type: 'info', icon: 'ph-lock', text: '<strong>admin</strong> updated password policy settings', time: '5 hours ago' },
  ];

  const pkiOps = [
    { type: 'gradient', icon: 'ph-certificate', text: 'Server certificate <strong>web-server-01.acme.com</strong> issued by Production CA', time: '5 minutes ago' },
    { type: 'gradient', icon: 'ph-certificate', text: 'Client certificate <strong>user-john.doe@acme.com</strong> issued by User CA', time: '12 minutes ago' },
    { type: 'gradient', icon: 'ph-tree-structure', text: 'Intermediate CA <strong>Production Issuing CA 2024</strong> created under Root CA', time: '25 minutes ago' },
    { type: 'error', icon: 'ph-prohibition', text: 'Certificate <strong>old-api.acme.com</strong> revoked (reason: superseded)', time: '45 minutes ago' },
    { type: 'gradient', icon: 'ph-file-text', text: 'CSR <strong>api-gateway.acme.com</strong> approved and certificate issued', time: '1 hour ago' },
    { type: 'gradient', icon: 'ph-list-checks', text: 'CRL generated for <strong>Production CA</strong> (3 revoked certificates)', time: '2 hours ago' },
    { type: 'gradient', icon: 'ph-certificate', text: 'ACME certificate <strong>*.acme.com</strong> auto-renewed successfully', time: '2 hours ago' },
    { type: 'gradient', icon: 'ph-broadcast', text: 'OCSP responder updated with latest certificate status', time: '3 hours ago' },
    { type: 'gradient', icon: 'ph-files', text: 'Template <strong>Web Server - 2 Year</strong> applied to new certificate', time: '3 hours ago' },
    { type: 'gradient', icon: 'ph-certificate', text: 'Certificate <strong>vpn-gateway.acme.com</strong> issued via SCEP enrollment', time: '4 hours ago' },
  ];

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
      <div className={styles.topbar}>
        <div className={styles.topbarTitle}>
          <i className="ph ph-clock-clockwise"></i>
          Activity
          <Badge variant="info">Real-time</Badge>
        </div>
        <div className={styles.topbarActions}>
          <Button variant="default" icon="ph ph-download-simple">Export Logs</Button>
        </div>
      </div>

      <div className={styles.filtersBar}>
        <div className={styles.filterGroupDate}>
          <div>
            <label>From</label>
            <input type="date" defaultValue="2024-01-01" />
          </div>
          <div>
            <label>To</label>
            <input type="date" defaultValue="2024-01-15" />
          </div>
        </div>
        <div className={styles.filterGroup}>
          <label>User</label>
          <select>
            <option>All Users</option>
            <option>john.doe</option>
            <option>admin</option>
            <option>jane.smith</option>
          </select>
        </div>
        <div className={styles.filterGroup}>
          <label>Action Type</label>
          <select>
            <option>All Actions</option>
            <option>Login</option>
            <option>Configuration</option>
            <option>User Management</option>
          </select>
        </div>
        <div className={styles.filterGroup}>
          <label>Search</label>
          <input type="text" placeholder="Search activities..." />
        </div>
      </div>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'app-logs' ? styles.active : ''}`}
          onClick={() => setActiveTab('app-logs')}
        >
          Application Logs
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'pki-ops' ? styles.active : ''}`}
          onClick={() => setActiveTab('pki-ops')}
        >
          PKI Operations
        </button>
      </div>

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
