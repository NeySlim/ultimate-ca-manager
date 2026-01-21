import { StatCard } from '../components/domain/StatCard';
import { ActivityFeed } from '../components/domain/ActivityFeed';
import { DataTable } from '../components/domain/DataTable';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { getBadgeVariant } from '../utils/getBadgeVariant';
import { getDashboardStats, getRecentActivity, getExpiringCertificates } from '../services/mockData';
import styles from './Dashboard.module.css';

/**
 * Dashboard Page
 * 
 * Reference: prototype-dashboard.html
 * 
 * Layout:
 * - 4 StatCards (grid)
 * - Recent Activity (ActivityFeed)
 * - Expiring Certificates (DataTable)
 */
export function Dashboard() {
  const stats = getDashboardStats();
  const activity = getRecentActivity();
  const expiringCerts = getExpiringCertificates();

  const certColumns = [
    {
      key: 'name',
      label: 'Certificate Name',
      sortable: true,
    },
    {
      key: 'ca',
      label: 'Issuing CA',
      sortable: true,
    },
    {
      key: 'expires',
      label: 'Expires',
      sortable: true,
    },
    {
      key: 'daysLeft',
      label: 'Days Left',
      sortable: true,
      render: (row) => (
        <span style={{ color: 'var(--text-tertiary)' }}>
          {row.daysLeft} days
        </span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      render: (row) => (
        <Badge variant={getBadgeVariant('cert-status', row.status)}>
          {row.status}
        </Badge>
      ),
    },
  ];

  return (
    <div className={styles.dashboard}>
      {/* Stats Grid */}
      <div className={styles.statsGrid}>
        <StatCard
          value={stats.cas.value}
          label={stats.cas.label}
          icon={stats.cas.icon}
          trend={stats.cas.trend}
          gradient
        />
        <StatCard
          value={stats.certificates.value}
          label={stats.certificates.label}
          icon={stats.certificates.icon}
          trend={stats.certificates.trend}
          gradient
        />
        <StatCard
          value={stats.acmeOrders.value}
          label={stats.acmeOrders.label}
          icon={stats.acmeOrders.icon}
          trend={stats.acmeOrders.trend}
          gradient
        />
        <StatCard
          value={stats.users.value}
          label={stats.users.label}
          icon={stats.users.icon}
          trend={stats.users.trend}
          gradient
        />
      </div>

      {/* Two Column Layout */}
      <div className={styles.overviewGrid}>
        {/* Recent Activity */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Recent Activity</h2>
          </div>
          <ActivityFeed items={activity} />
        </div>

        {/* Expiring Certificates */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Expiring Certificates</h2>
            <Button variant="primary" icon="ph ph-plus">
              Renew All
            </Button>
          </div>
          <DataTable
            columns={certColumns}
            data={expiringCerts}
            onRowClick={(row) => console.log('Certificate clicked:', row)}
          />
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
