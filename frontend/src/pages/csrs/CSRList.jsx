import { Tabs } from '../../components/ui/Tabs';
import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getCSRs } from '../../services/mockData';
import styles from './CSRList.module.css';

/**
 * CSRs Page
 * 
 * Three tabs for CSR workflow:
 * - Pending (awaiting approval)
 * - Approved (ready to issue)
 * - Rejected (declined requests)
 */
export function CSRList() {
  const csrs = getCSRs();

  const baseColumns = [
    {
      key: 'commonName',
      label: 'Common Name',
      sortable: true,
    },
    {
      key: 'requestedBy',
      label: 'Requested By',
      sortable: true,
    },
    {
      key: 'requestedAt',
      label: 'Requested At',
      sortable: true,
    },
    {
      key: 'keySize',
      label: 'Key Size',
      sortable: true,
      render: (row) => (
        <span style={{ color: 'var(--text-tertiary)' }}>
          {row.keySize} bits
        </span>
      ),
    },
  ];

  const pendingColumns = [
    ...baseColumns,
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div className={styles.actions}>
          <Button variant="success" icon="ph ph-check" onClick={() => console.log('Approve:', row)}>
            Approve
          </Button>
          <Button variant="danger" icon="ph ph-x" onClick={() => console.log('Reject:', row)}>
            Reject
          </Button>
        </div>
      ),
    },
  ];

  const approvedColumns = [
    ...baseColumns,
    {
      key: 'approvedBy',
      label: 'Approved By',
      sortable: true,
    },
    {
      key: 'approvedAt',
      label: 'Approved At',
      sortable: true,
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <Button variant="primary" icon="ph ph-certificate" onClick={() => console.log('Issue:', row)}>
          Issue Certificate
        </Button>
      ),
    },
  ];

  const rejectedColumns = [
    ...baseColumns,
    {
      key: 'rejectedBy',
      label: 'Rejected By',
      sortable: true,
    },
    {
      key: 'reason',
      label: 'Reason',
      render: (row) => (
        <span style={{ color: 'var(--text-tertiary)' }}>
          {row.reason}
        </span>
      ),
    },
  ];

  const filters = [
    {
      label: 'Requested By',
      options: ['All Users', 'admin', 'operator', 'developer'],
    },
    {
      label: 'Key Size',
      options: ['All Sizes', '2048', '4096'],
    },
  ];

  const actions = [
    { label: 'Create CSR', icon: 'ph ph-plus', variant: 'primary' },
    { label: 'Export List', icon: 'ph ph-download-simple', variant: 'default' },
  ];

  return (
    <div className={styles.csrList}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>
            Pending
            <Badge variant="warning" className={styles.countBadge}>
              {csrs.pending.length}
            </Badge>
          </Tabs.Tab>
          <Tabs.Tab>
            Approved
            <Badge variant="success" className={styles.countBadge}>
              {csrs.approved.length}
            </Badge>
          </Tabs.Tab>
          <Tabs.Tab>
            Rejected
            <Badge variant="danger" className={styles.countBadge}>
              {csrs.rejected.length}
            </Badge>
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* Pending Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search pending CSRs..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <DataTable
                columns={pendingColumns}
                data={csrs.pending}
                onRowClick={(row) => console.log('CSR clicked:', row)}
              />
            </div>
          </Tabs.Panel>

          {/* Approved Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search approved CSRs..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <DataTable
                columns={approvedColumns}
                data={csrs.approved}
                onRowClick={(row) => console.log('CSR clicked:', row)}
              />
            </div>
          </Tabs.Panel>

          {/* Rejected Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search rejected CSRs..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <DataTable
                columns={rejectedColumns}
                data={csrs.rejected}
                onRowClick={(row) => console.log('CSR clicked:', row)}
              />
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default CSRList;
