import { useState } from 'react';
import { PageTopBar, SectionTabs, Tab, StatsGrid, StatCard } from '../../components/common';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { useSCEPSettings, useSCEPStats } from '../../hooks/useSCEP';
import styles from './SCEPDashboard.module.css';

/**
 * SCEP Dashboard Page
 * 
 * Two tabs:
 * - Configuration (SCEP server settings)
 * - Enrollments (device enrollment requests)
 */
export function SCEPDashboard() {
  const [activeTab, setActiveTab] = useState('config');
  const { data: settings, isLoading: settingsLoading } = useSCEPSettings();
  const { data: stats, isLoading: statsLoading } = useSCEPStats();
  
  const isLoading = settingsLoading || statsLoading;
  
  const scepData = {
    config: settings || {},
    stats: stats || {},
    enrollments: [] // TODO: Add enrollments hook when available
  };

  const enrollmentColumns = [
    {
      key: 'deviceId',
      label: 'Device ID',
      sortable: true,
    },
    {
      key: 'commonName',
      label: 'Common Name',
      sortable: true,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('scep-status', row.status)}>
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'requestedAt',
      label: 'Requested At',
      sortable: true,
    },
    {
      key: 'approvedAt',
      label: 'Approved At',
      render: (row) => row.approvedAt || <span style={{ color: 'var(--text-tertiary)' }}>—</span>,
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => {
        if (row.status === 'pending') {
          return (
            <div className={styles.actions}>
              <Button variant="success" icon="ph ph-check" onClick={() => console.log('Approve:', row)}>
                Approve
              </Button>
              <Button variant="danger" icon="ph ph-x" onClick={() => console.log('Reject:', row)}>
                Reject
              </Button>
            </div>
          );
        }
        return null;
      },
    },
  ];

  const filters = [
    {
      label: 'Status',
      options: ['All Statuses', 'Pending', 'Completed', 'Rejected'],
    },
  ];

  const actions = [
    { label: 'Export List', icon: 'ph ph-download-simple', variant: 'default' },
  ];

  if (isLoading) {
    return (
      <div className={styles.scepDashboard}>
        <PageTopBar
          icon="ph ph-device-mobile"
          title="SCEP"
          badge={<Badge variant="secondary">Loading...</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-tertiary)' }}>
          Loading SCEP data...
        </div>
      </div>
    );
  }
  
  return (
    <div className={styles.scepDashboard}>
      <PageTopBar
        icon="ph ph-device-mobile"
        title="SCEP"
        badge={<Badge variant={scepData.config.enabled ? 'success' : 'secondary'}>{scepData.config.enabled ? 'Enabled' : 'Disabled'}</Badge>}
        actions={
          <>
            <Button icon="ph ph-arrows-clockwise">Refresh</Button>
            <Button variant="primary" icon="ph ph-gear">Configure</Button>
          </>
        }
      />

      <StatsGrid columns={4}>
        <StatCard
          value={scepData.stats.totalEnrollments}
          label="Total Enrollments"
          icon="ph ph-certificate"
        />
        <StatCard
          value={scepData.stats.pendingApprovals}
          label="Pending Approvals"
          icon="ph ph-clock"
        />
        <StatCard
          value={scepData.stats.completedToday}
          label="Completed Today"
          icon="ph ph-check-circle"
        />
        <StatCard
          value={scepData.stats.rejectedToday}
          label="Rejected Today"
          icon="ph ph-x-circle"
        />
      </StatsGrid>

      <SectionTabs>
        <Tab active={activeTab === 'config'} onClick={() => setActiveTab('config')}>
          Configuration
        </Tab>
        <Tab active={activeTab === 'enrollments'} onClick={() => setActiveTab('enrollments')}>
          Enrollments
        </Tab>
      </SectionTabs>

      {activeTab === 'config' && (
        <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>SCEP Server Configuration</h3>
                  <div className={styles.statusBadge}>
                    <span className={styles.statusDot} data-status={scepData.config.enabled ? 'enabled' : 'disabled'} />
                    <span>{scepData.config.enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input
                      label="SCEP URL"
                      value={scepData.config.url}
                      readOnly
                    />
                    <Input
                      label="CA Identifier"
                      value={scepData.config.caIdentifier}
                      readOnly
                    />
                    <Input
                      label="Challenge Password"
                      type="password"
                      value={scepData.config.challengePassword}
                      readOnly
                    />
                    <Input
                      label="Certificate Validity (days)"
                      value={scepData.config.certificateValidity}
                      readOnly
                    />
                    
                    <div className={styles.checkboxGroup}>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={scepData.config.allowRenewal} readOnly />
                        <span>Allow Certificate Renewal</span>
                      </label>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={scepData.config.autoApprove} readOnly />
                        <span>Auto-Approve Enrollments</span>
                      </label>
                    </div>

                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-floppy-disk">Save Configuration</Button>
                      <Button variant="default" icon="ph ph-arrow-clockwise">Reset</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>

              <Card className={styles.infoBox}>
                <Card.Body>
                  <div className={styles.infoContent}>
                    <div className={styles.infoIcon}>
                      <i className="ph ph-info" />
                    </div>
                    <div>
                      <div className={styles.infoTitle}>SCEP Enrollment</div>
                      <div className={styles.infoText}>
                        SCEP (Simple Certificate Enrollment Protocol) allows devices to automatically request and receive certificates.
                        Common use cases include mobile devices (iOS, Android) and network equipment.
                      </div>
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </div>
      )}

      {activeTab === 'enrollments' && (
        <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search enrollments..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <DataTable
                columns={enrollmentColumns}
                data={scepData.enrollments}
                onRowClick={(row) => console.log('Enrollment clicked:', row)}
              />
            </div>
      )}
    </div>
  );
}

export default SCEPDashboard;
