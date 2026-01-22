import { useState } from 'react';
import { PageTopBar, SectionTabs, Tab, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { useACMESettings, useACMEStats, useACMEAccounts, useACMEOrders, useUpdateACMESettings } from '../../hooks/useACME';
import { CreateACMEAccountModal } from '../../components/modals/CreateACMEAccountModal';
import { CreateACMEOrderModal } from '../../components/modals/CreateACMEOrderModal';
import toast from 'react-hot-toast';
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
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [showOrderModal, setShowOrderModal] = useState(false);
  
  const { data: settings, isLoading: loadingSettings, error: errorSettings } = useACMESettings();
  const { data: stats, isLoading: loadingStats, error: errorStats } = useACMEStats();
  const { data: accountsResponse, isLoading: loadingAccounts, error: errorAccounts } = useACMEAccounts();
  const { data: ordersResponse, isLoading: loadingOrders, error: errorOrders } = useACMEOrders();
  const updateACME = useUpdateACMESettings();

  const isLoading = loadingSettings || loadingStats || loadingAccounts || loadingOrders;
  const error = errorSettings || errorStats || errorAccounts || errorOrders;

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
    { label: 'New Account', icon: 'ph ph-plus', variant: 'primary', onClick: () => setShowAccountModal(true) },
    { label: 'New Order', icon: 'ph ph-certificate', variant: 'default', onClick: () => setShowOrderModal(true) },
  ];

  if (isLoading) {
    return (
      <div className={styles.acmeDashboard}>
        <PageTopBar
          icon="ph ph-globe"
          title="ACME"
          badge={<Badge variant="neutral">Loading...</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading ACME data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.acmeDashboard}>
        <PageTopBar
          icon="ph ph-globe"
          title="ACME"
          badge={<Badge variant="danger">Error</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading ACME data: {error.message}
        </div>
      </div>
    );
  }

  const acmeData = {
    stats: stats || { accounts: 0, activeOrders: 0, completedOrders: 0, domains: 0 },
    accounts: accountsResponse?.data || [],
    orders: ordersResponse?.data || [],
  };

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
      <PageTopBar
        icon="ph ph-globe"
        title="ACME"
        badge={<Badge variant={settings?.enabled ? 'success' : 'secondary'}>{settings?.enabled ? 'Enabled' : 'Disabled'}</Badge>}
        actions={
          <Button 
            variant={settings?.enabled ? 'secondary' : 'primary'}
            onClick={() => {
              updateACME.mutate({ enabled: !settings?.enabled }, {
                onSuccess: () => toast.success(settings?.enabled ? 'ACME disabled' : 'ACME enabled'),
                onError: () => toast.error('Failed to update ACME')
              });
            }}
          >
            {settings?.enabled ? 'Disable' : 'Enable'} ACME
          </Button>
        }
      />
      
      <SectionTabs>
        <Tab active={activeTab === 'internal'} onClick={() => setActiveTab('internal')}>
          Internal ACME
        </Tab>
        <Tab active={activeTab === 'letsencrypt'} onClick={() => setActiveTab('letsencrypt')}>
          Let's Encrypt
        </Tab>
      </SectionTabs>

      <div className={styles.tabContent}>
        {renderTab()}
      </div>
      
      <CreateACMEAccountModal 
        isOpen={showAccountModal} 
        onClose={() => setShowAccountModal(false)} 
      />
      
      <CreateACMEOrderModal 
        isOpen={showOrderModal} 
        onClose={() => setShowOrderModal(false)} 
      />
    </div>
  );
}

export default ACMEDashboard;
