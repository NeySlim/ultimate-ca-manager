import { useState } from 'react';
import { PageTopBar, SectionTabs, Tab, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { useACMESettings, useACMEStats, useACMEAccounts, useACMEOrders, useUpdateACMESettings } from '../../hooks/useACME';
import { useCAs } from '../../hooks/useCAs';
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
  const { data: casResponse, isLoading: loadingCAs } = useCAs();
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

  // stats is already transformed by acmeApi.getStats()
  const acmeData = {
    stats: stats || { accounts: 0, activeOrders: 0, completedOrders: 0, domains: 0 },
    accounts: accountsResponse?.data || [],
    orders: ordersResponse?.data || [],
  };

  // Prepare CAs options for select
  const casOptions = [
    { value: '', label: 'Select issuing CA...' },
    ...(casResponse?.data || []).map(ca => ({
      value: ca._raw?.refid || ca.id,
      label: ca.name || ca._raw?.common_name || 'Unnamed CA'
    }))
  ];

  const handleUpdateIssuingCA = (caId) => {
    updateACME.mutate(
      { issuing_ca_id: caId },
      {
        onSuccess: () => toast.success('Issuing CA updated'),
        onError: () => toast.error('Failed to update issuing CA')
      }
    );
  };

  const renderInternalTab = () => (
    <div className={styles.tabContent}>
      {/* Internal ACME Settings */}
      <div className={styles.settingsCard}>
        <h3 className={styles.settingsTitle}>
          <i className="ph ph-gear" style={{ marginRight: '0.5rem' }}></i>
          Internal ACME Server Configuration
        </h3>
        <div className={styles.settingsContent}>
          <div className={styles.settingRow}>
            <label className={styles.settingLabel}>Directory URL:</label>
            <code className={styles.urlCode}>{window.location.origin}/acme/directory</code>
          </div>
          <div className={styles.settingRow}>
            <label className={styles.settingLabel}>Issuing CA:</label>
            <div style={{ flex: 1 }}>
              <Select
                value={settings?.issuing_ca_id || ''}
                onChange={handleUpdateIssuingCA}
                options={casOptions}
                disabled={loadingCAs}
                placeholder="Select issuing CA..."
              />
              {settings?.issuing_ca_name && (
                <div className={styles.caSelectedInfo}>
                  <i className="ph ph-check-circle" style={{ color: 'var(--color-success)', marginRight: '0.5rem' }}></i>
                  Currently using: <strong>{settings.issuing_ca_name}</strong>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <StatsGrid columns={4}>
        <StatCard
          value={acmeData.stats.accounts}
          label="Accounts"
          icon="ph ph-user"
        />
        <StatCard
          value={acmeData.stats.activeOrders}
          label="Active Orders"
          icon="ph ph-clock"
        />
        <StatCard
          value={acmeData.stats.completedOrders}
          label="Completed Orders"
          icon="ph ph-check-circle"
        />
        <StatCard
          value={acmeData.stats.domains}
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
          onSearch={(query) => console.log('Search:', query)}
          onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
        />
        <DataTable
          columns={accountColumns}
          data={acmeData.accounts}
          onRowClick={(row) => console.log('Account clicked:', row)}
        />
      </div>

      {/* Recent Orders */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Recent Orders</h3>
        <DataTable
          columns={orderColumns}
          data={acmeData.orders}
          onRowClick={(row) => console.log('Order clicked:', row)}
        />
      </div>
    </div>
  );

  const renderLetsEncryptTab = () => (
    <div className={styles.tabContent}>
      {/* Let's Encrypt Proxy Settings */}
      <div className={styles.settingsCard}>
        <h3 className={styles.settingsTitle}>
          <i className="ph ph-link" style={{ marginRight: '0.5rem' }}></i>
          Let's Encrypt Proxy Configuration
        </h3>
        <div className={styles.settingsContent}>
          <div className={styles.settingRow}>
            <label className={styles.settingLabel}>Proxy Directory URL:</label>
            <code className={styles.urlCode}>{window.location.origin}/acme/proxy/directory</code>
          </div>
          <div className={styles.settingHint}>
            This proxy allows you to use Let's Encrypt through UCM while maintaining audit trails and control.
          </div>
        </div>
      </div>

      {/* Stats */}
      <StatsGrid columns={4}>
        <StatCard
          value={acmeData.stats.accounts}
          label="Accounts"
          icon="ph ph-user"
        />
        <StatCard
          value={acmeData.stats.activeOrders}
          label="Active Orders"
          icon="ph ph-clock"
        />
        <StatCard
          value={acmeData.stats.completedOrders}
          label="Completed Orders"
          icon="ph ph-check-circle"
        />
        <StatCard
          value={acmeData.stats.domains}
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
          onSearch={(query) => console.log('Search:', query)}
          onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
        />
        <DataTable
          columns={accountColumns}
          data={acmeData.accounts}
          onRowClick={(row) => console.log('Account clicked:', row)}
        />
      </div>

      {/* Recent Orders */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Recent Orders</h3>
        <DataTable
          columns={orderColumns}
          data={acmeData.orders}
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
          <>
            <Button onClick={() => setShowAccountModal(true)} icon="ph ph-plus">
              New Account
            </Button>
            <Button onClick={() => setShowOrderModal(true)} icon="ph ph-certificate">
              New Order
            </Button>
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
          </>
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
        {activeTab === 'internal' ? renderInternalTab() : renderLetsEncryptTab()}
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
