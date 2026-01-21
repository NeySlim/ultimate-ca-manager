import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getCertificates } from '../../services/mockData';
import styles from './CertificateList.module.css';

/**
 * Certificates Page
 * 
 * Comprehensive certificate management with:
 * - Search and filters
 * - Sortable table with 8 columns
 * - Status badges
 * - Row click for details
 */
export function CertificateList() {
  const certificates = getCertificates();

  const columns = [
    {
      key: 'commonName',
      label: 'Common Name',
      sortable: true,
    },
    {
      key: 'ca',
      label: 'Issuing CA',
      sortable: true,
    },
    {
      key: 'validFrom',
      label: 'Valid From',
      sortable: true,
    },
    {
      key: 'validUntil',
      label: 'Valid Until',
      sortable: true,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('cert-status', row.status)}>
          {row.status}
        </Badge>
      ),
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
    {
      key: 'algorithm',
      label: 'Algorithm',
      sortable: true,
    },
    {
      key: 'serialNumber',
      label: 'Serial Number',
      render: (row) => (
        <code className={styles.serial}>{row.serialNumber}</code>
      ),
    },
  ];

  const filters = [
    {
      label: 'Status',
      options: ['All Statuses', 'Valid', 'Expiring', 'Expired', 'Revoked'],
    },
    {
      label: 'Issuing CA',
      options: ['All CAs', 'ACME Intermediate CA', 'Production Intermediate CA', 'Web Server CA'],
    },
    {
      label: 'Key Size',
      options: ['All Sizes', '2048', '4096'],
    },
    {
      label: 'Algorithm',
      options: ['All Algorithms', 'RSA', 'ECDSA'],
    },
  ];

  const actions = [
    { label: 'Issue Certificate', icon: 'ph ph-plus', variant: 'primary' },
    { label: 'Import Certificate', icon: 'ph ph-upload', variant: 'default' },
    { label: 'Export List', icon: 'ph ph-download-simple', variant: 'default' },
  ];

  return (
    <div className={styles.certificateList}>
      <SearchToolbar
        placeholder="Search by common name or SAN..."
        filters={filters}
        actions={actions}
        onSearch={(query) => console.log('Search:', query)}
        onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
      />
      
      <DataTable
        columns={columns}
        data={certificates}
        onRowClick={(row) => console.log('Certificate clicked:', row)}
      />
    </div>
  );
}

export default CertificateList;
