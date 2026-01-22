import { useState, useEffect } from 'react';
import GridLayout from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import { StatCard } from '../components/domain/StatCard';
import { ActivityFeed } from '../components/domain/ActivityFeed';
import { DataTable } from '../components/domain/DataTable';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Warning, Info, CheckCircle, Clock, ArrowCounterClockwise } from '@phosphor-icons/react';
import { getBadgeVariant } from '../utils/getBadgeVariant';
import { useDashboardStats, useDashboardOverview, useDashboardActivity, useDashboardExpiringCerts } from '../hooks/useDashboard';
import { loadLayout, saveLayout, resetLayout, DEFAULT_LAYOUT } from '../config/dashboardLayouts';
import { useDashboardLayout } from '../contexts/DashboardLayoutContext';
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
  // Edit mode state from context
  const { isEditMode } = useDashboardLayout();
  
  // Layout state
  const [layout, setLayout] = useState(loadLayout());
  
  // Fetch data with React Query
  const { data: stats, isLoading: statsLoading, error: statsError } = useDashboardStats();
  const { data: overview, isLoading: overviewLoading, error: overviewError } = useDashboardOverview();
  const { data: activity, isLoading: activityLoading } = useDashboardActivity(20);
  const { data: expiringCerts, isLoading: expiringLoading } = useDashboardExpiringCerts(10);

  // Save layout when it changes
  const handleLayoutChange = (newLayout) => {
    setLayout(newLayout);
    saveLayout(newLayout);
  };

  // Reset to default layout
  const handleResetLayout = () => {
    const defaultLayout = resetLayout();
    setLayout(defaultLayout);
  };

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

  // Loading state
  if (statsLoading || overviewLoading) {
    return (
      <div style={{ padding: 'var(--spacing-xl)', textAlign: 'center' }}>
        <div style={{ fontSize: '14px', color: 'var(--text-tertiary)' }}>Loading dashboard...</div>
      </div>
    );
  }

  // Error state
  if (statsError || overviewError) {
    return (
      <div style={{ padding: 'var(--spacing-xl)', textAlign: 'center' }}>
        <div style={{ fontSize: '14px', color: 'var(--status-danger)' }}>
          Error loading dashboard: {statsError?.message || overviewError?.message}
        </div>
      </div>
    );
  }

  // Use API data with fallbacks
  const statsData = stats || {
    activeCertificates: '0',
    expiringSoon: '0',
    pendingRequests: '0',
    acmeRenewals: '0',
  };
  const overviewData = overview || [];
  const activityData = activity || [];
  const expiringCertsData = expiringCerts || [];

  return (
    <div className={`${styles.dashboardContainer} ${isEditMode ? styles.editMode : ''}`}>
      {isEditMode && (
        <div className={styles.editModeBanner}>
          <span>✏️ Edit Mode Active - Drag and resize widgets</span>
          <Button variant="secondary" size="sm" onClick={handleResetLayout}>
            <ArrowCounterClockwise size={14} />
            Reset Layout
          </Button>
        </div>
      )}
      
      <GridLayout
        className={styles.dashboard}
        layout={layout}
        cols={24}
        rowHeight={30}
        width={1200}
        isDraggable={isEditMode}
        isResizable={isEditMode}
        compactType="vertical"
        preventCollision={false}
        onLayoutChange={handleLayoutChange}
        draggableHandle=".drag-handle"
        margin={[8, 8]}
      >
        {/* 1. Stats - 4 widgets */}
        <div key="stat-active" className={`${styles.widget} ${styles.widgetCard}`}>
          {isEditMode && <div className="drag-handle" />}
          <StatCard
            value={statsData.activeCertificates}
            label="Active Certificates"
            icon="certificate"
            trend={{ direction: 'up', text: '+12 this week', positive: true }}
            gradient
          />
        </div>
        
        <div key="stat-expiring" className={`${styles.widget} ${styles.widgetCard}`}>
          {isEditMode && <div className="drag-handle" />}
          <StatCard
            value={statsData.expiringSoon}
            label="Expiring Soon"
            sublabel="Within 30 days"
            icon="clock"
            trend={{ direction: 'down', text: '5 critical (7 days)', positive: false }}
            variant="warning"
          />
        </div>
        
        <div key="stat-requests" className={`${styles.widget} ${styles.widgetCard}`}>
          {isEditMode && <div className="drag-handle" />}
          <StatCard
            value={statsData.pendingRequests}
            label="Pending Requests"
            sublabel="CSRs awaiting approval"
            icon="file-text"
            gradient
          />
        </div>
        
        <div key="stat-acme" className={`${styles.widget} ${styles.widgetCard}`}>
          {isEditMode && <div className="drag-handle" />}
          <StatCard
            value={statsData.acmeRenewals}
            label="ACME Renewals"
            sublabel="Last 30 days"
            icon="globe"
            trend={{ direction: 'up', text: '100% success rate', positive: true }}
            gradient
          />
        </div>

        {/* 2. System Overview - span 6 */}
        <div key="overview" className={`${styles.widget} ${styles.widgetPanel}`}>
          {isEditMode && <div className="drag-handle" />}
          <h2 className={styles.sectionTitle}>System Overview</h2>
          <div className={styles.overviewGrid}>
            {overviewData.map(item => (
              <div key={item.label} className={styles.overviewCard}>
                <div className={styles.overviewLabel}>{item.label}</div>
                <div className={styles.overviewValue}>{item.value}</div>
                <div className={styles.overviewSubtext}>{item.subtext}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 3. Alerts - span 6 */}
        <div key="alerts" className={`${styles.widget} ${styles.widgetPanel}`}>
          {isEditMode && <div className="drag-handle" />}
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
        <div key="expiring-table" className={`${styles.widget} ${styles.widgetTable}`}>
          {isEditMode && <div className="drag-handle" />}
          <div style={{ padding: 'var(--spacing-lg)', paddingBottom: 'var(--spacing-sm)' }}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Certificates Expiring Soon</h2>
              <Button 
                variant="secondary"
                onClick={() => window.location.href = '/certificates?filter=expiring'}
              >
                View All ({statsData.expiringSoon})
              </Button>
            </div>
          </div>
          <DataTable
            columns={certColumns}
            data={expiringCertsData}
            onRowClick={(row) => console.log('Certificate clicked:', row)}
          />
        </div>

        {/* 5. Recent Activity - span 12 */}
        <div key="activity" className={`${styles.widget} ${styles.widgetPanel}`}>
          {isEditMode && <div className="drag-handle" />}
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Recent Activity</h2>
            <Button 
              variant="secondary"
              onClick={() => window.location.href = '/activity'}
            >
              View All
            </Button>
          </div>
          <ActivityFeed items={activityData} />
        </div>
      </GridLayout>
    </div>
  );
}

export default Dashboard;
