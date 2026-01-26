import { useState } from 'react';
import { PageTopBar, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { ViewCADetailsModal } from '../../components/modals/ViewCADetailsModal';
import { exportTableData } from '../../utils/export';
import toast from 'react-hot-toast';
import api from '../../services/api/api';
import styles from './CRLManagement.module.css';

export function CRLManagement() {
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [selectedCA, setSelectedCA] = useState(null);
  const [showCAModal, setShowCAModal] = useState(false);

  const handleDownloadCRL = (caId) => {
    window.open(`/api/v2/crl/download/${caId}`, '_blank');
    toast.success('CRL download started');
  };

  const handleRegenerateCRL = async (ca) => {
    if (!confirm(`Regenerate CRL for ${ca.name}? This may take a moment.`)) return;
    
    setIsRegenerating(true);
    try {
      await api.post(`/api/v2/crl/regenerate/${ca.id}`);
      toast.success('CRL regenerated successfully');
    } catch (error) {
      toast.error('Failed to regenerate CRL');
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleViewCA = (ca) => {
    setSelectedCA(ca);
    setShowCAModal(true);
  };

  const handleExportCRLs = () => {
    if (cas.length === 0) {
      toast.error('No CRL data to export');
      return;
    }
    exportTableData(cas, 'crls-export', {
      format: 'csv',
      columns: ['id', 'name', 'crlStatus', 'lastGenerated', 'nextUpdate', 'ocspStatus']
    });
    toast.success('CRLs exported successfully');
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
                disabled={isRegenerating}
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
              onClick={() => {
                // Redirect to Settings CRL section
                window.location.href = '/settings#crl';
                toast.info('Redirecting to CRL configuration...');
              }}
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
            <Button icon="ph ph-download-simple" onClick={handleExportCRLs}>Export CRLs</Button>
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
            onRowClick={handleViewCA}
            pageSize={10}
          />
        </Card.Body>
      </Card>

      <ViewCADetailsModal
        isOpen={showCAModal}
        onClose={() => setShowCAModal(false)}
        ca={selectedCA}
      />
    </div>
  );
}

export default CRLManagement;
