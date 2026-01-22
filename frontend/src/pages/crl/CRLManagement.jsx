import { PageTopBar, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import toast from 'react-hot-toast';
import styles from './CRLManagement.module.css';

export function CRLManagement() {
  const handleDownloadCRL = (caId) => {
    window.open(`/api/v2/crl/download/${caId}`, '_blank');
    toast.success('CRL download started');
  };

  const handleRegenerateCRL = (ca) => {
    toast.success(`Regenerating CRL for ${ca.name}...`);
    // TODO: Connect to backend mutation when available
  };

  const cas = [
    {
      id: 1,
      name: 'Internal Root CA',
      crlStatus: 'active',
      lastGenerated: '2 hours ago',
      nextUpdate: 'In 22 hours',
      ocspStatus: 'enabled',
      revokedCerts: 3,
    },
    {
      id: 2,
      name: 'Production Intermediate CA',
      crlStatus: 'active',
      lastGenerated: '3 hours ago',
      nextUpdate: 'In 21 hours',
      ocspStatus: 'enabled',
      revokedCerts: 12,
    },
    {
      id: 3,
      name: 'Development Intermediate CA',
      crlStatus: 'active',
      lastGenerated: '1 hour ago',
      nextUpdate: 'In 23 hours',
      ocspStatus: 'enabled',
      revokedCerts: 8,
    },
    {
      id: 4,
      name: 'ECDSA Root CA',
      crlStatus: 'stale',
      lastGenerated: '3 days ago',
      nextUpdate: 'Overdue',
      ocspStatus: 'enabled',
      revokedCerts: 1,
    },
    {
      id: 5,
      name: 'Testing Root CA',
      crlStatus: 'disabled',
      lastGenerated: '-',
      nextUpdate: '-',
      ocspStatus: 'disabled',
      revokedCerts: 0,
    },
  ];

  const columns = [
    {
      key: 'name',
      label: 'CA Name',
      sortable: true,
      render: (row) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
          {row.name}
        </span>
      ),
    },
    {
      key: 'crlStatus',
      label: 'CRL Status',
      sortable: true,
      render: (row) => {
        const statusMap = {
          active: 'success',
          stale: 'warning',
          disabled: 'info',
        };
        const labelMap = {
          active: 'Active',
          stale: 'Stale',
          disabled: 'Disabled',
        };
        return <Badge variant={statusMap[row.crlStatus]}>{labelMap[row.crlStatus]}</Badge>;
      },
    },
    {
      key: 'lastGenerated',
      label: 'Last Generated',
      sortable: true,
    },
    {
      key: 'nextUpdate',
      label: 'Next Update',
      sortable: true,
    },
    {
      key: 'ocspStatus',
      label: 'OCSP',
      sortable: true,
      render: (row) => {
        const statusMap = {
          enabled: 'success',
          disabled: 'info',
        };
        const labelMap = {
          enabled: 'Enabled',
          disabled: 'Disabled',
        };
        return <Badge variant={statusMap[row.ocspStatus]}>{labelMap[row.ocspStatus]}</Badge>;
      },
    },
    {
      key: 'revokedCerts',
      label: 'Revoked Certs',
      sortable: true,
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div style={{ display: 'flex', gap: '8px' }}>
          {row.crlStatus !== 'disabled' && (
            <>
              <Button
                variant="default"
                size="sm"
                icon="ph ph-arrows-clockwise"
                onClick={() => handleRegenerateCRL(row)}
              />
              <Button
                variant="default"
                size="sm"
                icon="ph ph-download-simple"
                onClick={() => handleDownloadCRL(row.id)}
              />
            </>
          )}
          {row.crlStatus === 'disabled' && (
            <Button
              variant="default"
              size="sm"
              icon="ph ph-gear"
              onClick={() => console.log('Configure:', row)}
            />
          )}
        </div>
      ),
    },
  ];

  return (
    <div className={styles.crlManagement}>
      <PageTopBar
        icon="ph ph-list-checks"
        title="CRL Management"
        badge={<Badge variant="success">5 Active CAs</Badge>}
        actions={
          <>
            <Button icon="ph ph-arrows-clockwise">Regenerate All</Button>
            <Button icon="ph ph-download-simple">Export CRLs</Button>
          </>
        }
      />

      <StatsGrid columns={4}>
        <StatCard
          value="23"
          label="CRLs Generated"
          icon="ph ph-file-text"
        />
        <StatCard
          value="14,523"
          label="OCSP Requests (24h)"
          icon="ph ph-chart-line"
        />
        <StatCard
          value="5"
          label="Active CAs"
          icon="ph ph-certificate"
        />
        <StatCard
          value="12ms"
          label="Avg Response Time"
          icon="ph ph-timer"
        />
      </StatsGrid>

      <Card>
        <Card.Header>
          <h3>Certificate Authorities</h3>
          <Button variant="default" icon="ph ph-funnel">
            Filter
          </Button>
        </Card.Header>
        <Card.Body>
          <DataTable
            columns={columns}
            data={cas}
            onRowClick={(row) => console.log('CA clicked:', row)}
            pageSize={10}
          />
        </Card.Body>
      </Card>
    </div>
  );
}

export default CRLManagement;
