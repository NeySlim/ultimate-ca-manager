import { Tabs } from '../../components/ui/Tabs';
import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Button } from '../../components/ui/Button';
import { getTrustStoreCertificates } from '../../services/mockData';
import styles from './TrustStore.module.css';

/**
 * Trust Store Page
 * 
 * Two tabs:
 * - System Trust Store (Mozilla CA bundle)
 * - Custom Trust Store (user-added CAs)
 */
export function TrustStore() {
  const trustCerts = getTrustStoreCertificates();

  const columns = [
    {
      key: 'name',
      label: 'Certificate Name',
      sortable: true,
    },
    {
      key: 'issuer',
      label: 'Issuer',
      sortable: true,
    },
    {
      key: 'expires',
      label: 'Expires',
      sortable: true,
    },
    {
      key: 'type',
      label: 'Type',
      sortable: true,
    },
    {
      key: 'fingerprint',
      label: 'Fingerprint (SHA1)',
      render: (row) => (
        <code className={styles.fingerprint}>{row.fingerprint}</code>
      ),
    },
  ];

  const customColumns = [
    ...columns,
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <Button variant="danger" icon="ph ph-trash" onClick={() => console.log('Delete:', row)}>
          Remove
        </Button>
      ),
    },
  ];

  const filters = [
    {
      label: 'Type',
      options: ['All Types', 'Root CA', 'Intermediate CA', 'Bundle'],
    },
  ];

  const actions = [
    { label: 'Add Certificate', icon: 'ph ph-plus', variant: 'primary' },
    { label: 'Sync Mozilla Bundle', icon: 'ph ph-arrow-clockwise', variant: 'default' },
  ];

  return (
    <div className={styles.trustStore}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>System Trust Store</Tabs.Tab>
          <Tabs.Tab>Custom Trust Store</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* System Trust Store Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search system trust store..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <DataTable
                columns={columns}
                data={trustCerts.system}
                onRowClick={(row) => console.log('Certificate clicked:', row)}
              />
            </div>
          </Tabs.Panel>

          {/* Custom Trust Store Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search custom trust store..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <DataTable
                columns={customColumns}
                data={trustCerts.custom}
                onRowClick={(row) => console.log('Certificate clicked:', row)}
              />
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default TrustStore;
