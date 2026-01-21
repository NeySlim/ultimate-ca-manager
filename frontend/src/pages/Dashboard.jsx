import { StatCard } from '../components/domain/StatCard';
import { ActivityFeed } from '../components/domain/ActivityFeed';
import { DataTable } from '../components/domain/DataTable';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Warning, Info, CheckCircle, Clock } from '@phosphor-icons/react';
import { getBadgeVariant } from '../utils/getBadgeVariant';
import { getDashboardStats, getRecentActivity, getExpiringCertificates, getSystemOverview } from '../services/mockData';
import styles from './Dashboard.module.css';

/**
 * Dashboard Page
 * 
 * Reference: prototype-dashboard.html lines 1082-1500
 * 
 * Layout (exact match to prototype):
 * - 4 StatCards: Active Certs, Expiring Soon, Pending Requests, ACME Renewals
 * - System Overview: 4 metrics (CAs, Users, ACME, SCEP)
 * - Alerts: 3 alert cards (Warning, Info, Success)
 * - Expiring Certificates Table (with colored type badges)
 * - Recent Activity Feed
 */
export function Dashboard() {
  const stats = getDashboardStats();
  const activity = getRecentActivity();
  const expiringCerts = getExpiringCertificates();
  const systemOverview = getSystemOverview();

  const certColumns = [
    {
      key: 'name',
      label: 'Certificate',
      sortable: true,
      render: (row) => (
        <div>
          <div style={{ fontSize: '13px', color: 'var(--text-primary)', marginBottom: '2px' }}>
            {row.name}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono, monospace' }}>
            {row.fingerprint}
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'Type',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('cert-type', row.type)}>
          {row.type}
        </Badge>
      ),
    },
    {
      key: 'issuer',
      label: 'Issuer',
      sortable: true,
    },
    {
      key: 'expiresIn',
      label: 'Expires In',
      sortable: true,
      render: (row) => {
        const variant = row.daysLeft <= 7 ? 'error' : 'warning';
        const icon = row.daysLeft <= 7 ? <Warning size={14} /> : <Clock size={14} />;
        return (
          <Badge variant={variant}>
            {icon}
            {row.expiresIn}
          </Badge>
        );
      },
    },
  ];

  return (
    <div className={styles.dashboard}>
      {/* 1. Stats - 4 widgets @ span 3 each (12-column grid) */}
      <div className={styles.widgetSpan3}>
        <StatCard
          value="247"
          label="Active Certificates"
          icon="certificate"
          trend={{ direction: 'up', text: '+12 this week', positive: true }}
          gradient
        />
      </div>
      <div className={styles.widgetSpan3}>
        <StatCard
          value="12"
          label="Expiring Soon"
          sublabel="Within 30 days"
          icon="clock"
          trend={{ direction: 'down', text: '5 critical (7 days)', positive: false }}
          variant="warning"
        />
      </div>
      <div className={styles.widgetSpan3}>
        <StatCard
          value="8"
          label="Pending Requests"
          sublabel="CSRs awaiting approval"
          icon="file-text"
          gradient
        />
      </div>
      <div className={styles.widgetSpan3}>
        <StatCard
          value="156"
          label="ACME Renewals"
          sublabel="Last 30 days"
          icon="globe"
          trend={{ direction: 'up', text: '100% success rate', positive: true }}
          gradient
        />
      </div>

      {/* 2. System Overview - span 6 */}
      <div className={`${styles.widget} ${styles.widgetSpan6}`}>
        <h2 className={styles.sectionTitle}>System Overview</h2>
        <div className={styles.overviewGrid}>
          {systemOverview.map(item => (
            <div key={item.label} className={styles.overviewCard}>
              <div className={styles.overviewLabel}>{item.label}</div>
              <div className={styles.overviewValue}>{item.value}</div>
              <div className={styles.overviewSubtext}>{item.subtext}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 3. Alerts - span 6 */}
      <div className={`${styles.widget} ${styles.widgetSpan6}`}>
        <div className={styles.alertsHeader}>
          <h2 className={styles.sectionTitle} style={{ marginBottom: 0 }}>Alerts</h2>
          <Badge variant="warning">3</Badge>
        </div>
        <div className={styles.alertsGrid}>
          <div className={styles.alertCard} data-variant="warning">
            <Warning size={18} className={styles.alertIcon} style={{ color: 'var(--status-warning)' }} />
            <div className={styles.alertText}>5 certs<br />expire soon</div>
          </div>
          <div className={styles.alertCard} data-variant="info">
            <Info size={18} className={styles.alertIcon} style={{ color: 'var(--status-info)' }} />
            <div className={styles.alertText}>8 CSRs<br />pending</div>
          </div>
          <div className={styles.alertCard} data-variant="success">
            <CheckCircle size={18} className={styles.alertIcon} style={{ color: 'var(--status-success)' }} />
            <div className={styles.alertText}>Backup<br />OK</div>
          </div>
        </div>
      </div>

      {/* 4. Expiring Certificates Table - span 12 */}
      <div className={`${styles.widget} ${styles.widgetSpan12}`} style={{ padding: 0 }}>
        <div style={{ padding: 'var(--spacing-lg)', paddingBottom: 'var(--spacing-sm)' }}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Certificates Expiring Soon</h2>
            <Button variant="secondary">View All (12)</Button>
          </div>
        </div>
        <DataTable
          columns={certColumns}
          data={expiringCerts}
          onRowClick={(row) => console.log('Certificate clicked:', row)}
        />
      </div>

      {/* 5. Recent Activity - span 12 */}
      <div className={`${styles.widget} ${styles.widgetSpan12}`}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Recent Activity</h2>
          <Button variant="secondary">View All</Button>
        </div>
        <ActivityFeed items={activity} />
      </div>
    </div>
  );
}

export default Dashboard;
