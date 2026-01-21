import { useState } from 'react';
import { PageTopBar, SectionTabs, Tab, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getACMEData } from '../../services/mockData';
import styles from './ACMEDashboard.module.css';

/**
 * ACME Dashboard Page
 * 
 * Two tabs:
 * - Internal ACME (UCM's own ACME server)
 * - Let's Encrypt (external ACME provider)
 */
export function ACMEDashboard() {
  const [activeTab, setActiveTab] = useState('internal');
  const acmeData = getACMEData();

  const accountColumns = [
    {
      key: 'email',
      label: 'Email',
      sortable: true,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('acme-status', row.status)}>
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'createdAt',
      label: 'Created At',
      sortable: true,
    },
    {
      key: 'orders',
      label: 'Orders',
      sortable: true,
      render: (row) => (
        <span style={{ color: 'var(--text-tertiary)' }}>{row.orders}</span>
      ),
    },
  ];

  const orderColumns = [
    {
      key: 'domain',
      label: 'Domain',
      sortable: true,
    },
    {
      key: 'account',
      label: 'Account',
      sortable: true,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('acme-status', row.status)}>
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'createdAt',
      label: 'Created',
      sortable: true,
    },
    {
      key: 'expiresAt',
      label: 'Expires',
      sortable: true,
    },
  ];

  const filters = [
    {
      label: 'Status',
      options: ['All Statuses', 'Valid', 'Pending', 'Invalid'],
    },
  ];

  const actions = [
    { label: 'New Account', icon: 'ph ph-plus', variant: 'primary' },
    { label: 'New Order', icon: 'ph ph-certificate', variant: 'default' },
  ];

  const renderTab = (data, title) => (
    <div className={styles.tabContent}>
      {/* Stats */}
      <StatsGrid columns={4}>
        <StatCard
          value={data.stats.accounts}
          label="Accounts"
          icon="ph ph-user"
        />
        <StatCard
          value={data.stats.activeOrders}
          label="Active Orders"
          icon="ph ph-clock"
        />
        <StatCard
          value={data.stats.completedOrders}
          label="Completed Orders"
          icon="ph ph-check-circle"
        />
        <StatCard
          value={data.stats.domains}
          label="Domains"
          icon="ph ph-globe"
        />
      </StatsGrid>

      {/* Accounts */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Accounts</h3>
        <SearchToolbar
          placeholder="Search accounts..."
          filters={filters}
          actions={actions}
          onSearch={(query) => console.log('Search:', query)}
          onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
        />
        <DataTable
          columns={accountColumns}
          data={data.accounts}
          onRowClick={(row) => console.log('Account clicked:', row)}
        />
      </div>

      {/* Recent Orders */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Recent Orders</h3>
        <DataTable
          columns={orderColumns}
          data={data.orders}
          onRowClick={(row) => console.log('Order clicked:', row)}
        />
      </div>
    </div>
  );

  return (
    <div className={styles.acmeDashboard}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>Internal ACME</Tabs.Tab>
          <Tabs.Tab>Let's Encrypt</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          <Tabs.Panel>{renderTab(acmeData.internal, 'Internal ACME')}</Tabs.Panel>
          <Tabs.Panel>{renderTab(acmeData.letsencrypt, 'Let\'s Encrypt')}</Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default ACMEDashboard;
