import { useState } from 'react';
import { PageTopBar, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { useTrustStore, useRemoveTrustedCert, useSyncTrustStore } from '../../hooks/useTrustStore';
import { ViewCertificateModal } from '../../components/modals/ViewCertificateModal';
import { AddCAToTrustStoreModal } from '../../components/modals/AddCAToTrustStoreModal';
import toast from 'react-hot-toast';
import styles from './TrustStore.module.css';

export function TrustStore() {
  const [selectedCert, setSelectedCert] = useState(null);
  const [showViewModal, setShowViewModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  // Fetch trusted certificates from backend
  const { data, isLoading, error } = useTrustStore();
  const removeCert = useRemoveTrustedCert();
  const syncTrustStore = useSyncTrustStore();

  // Transform backend data to frontend format
  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toISOString().split('T')[0];
  };

  // Handle both {data: [...]} and [...] formats
  const rawCerts = Array.isArray(data) ? data : (data?.data || []);

  const trustedCAs = rawCerts.map(cert => ({
    id: cert.id,
    name: cert.subject?.split(',')[0]?.replace('CN=', '') || 'Unknown',
    subject: cert.subject || 'N/A',
    fingerprint: cert.fingerprint_sha256?.substring(0, 20) + '...' || 'N/A',
    validUntil: formatDate(cert.valid_until),
    usage: [cert.purpose || 'General'],
    autoTrusted: false, // Backend doesn't track this yet
  }));

  const handleRemove = (cert) => {
    if (confirm(`Remove "${cert.name}" from trust store?`)) {
      removeCert.mutate(cert.id);
    }
  };

  const handleView = (cert) => {
    setSelectedCert(cert);
    setShowViewModal(true);
  };

  const handleSync = () => {
    if (confirm('Synchronize trust store with system CA bundle?')) {
      syncTrustStore.mutate();
    }
  };

  if (error) {
    return (
      <div className={styles.trustStore}>
        <PageTopBar icon="ph ph-shield-check" title="Trust Store" badge={<Badge variant="danger">Error</Badge>} />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading trust store: {error.message}
        </div>
      </div>
    );
  }

  const columns = [
    {
      key: 'name',
      label: 'Name',
      render: (row) => (
        <div>
          <div style={{ fontSize: '13px', color: 'var(--text-primary)', marginBottom: '2px' }}>
            {row.name}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
            {row.subject}
          </div>
        </div>
      ),
    },
    {
      key: 'fingerprint',
      label: 'Fingerprint',
      render: (row) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)' }}>
          {row.fingerprint}
        </span>
      ),
    },
    {
      key: 'validUntil',
      label: 'Valid Until',
    },
    {
      key: 'usage',
      label: 'Usage',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.usage.map((u, idx) => (
            <Badge key={idx} variant="info">{u}</Badge>
          ))}
        </div>
      ),
    },
    {
      key: 'autoTrusted',
      label: 'Auto-Trusted',
      render: (row) =>
        row.autoTrusted ? (
          <Badge variant="success">
            <i className="ph ph-check" style={{ marginRight: '4px' }} />
            Yes
          </Badge>
        ) : (
          <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>No</span>
        ),
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
          <Button variant="default" size="sm" icon="ph ph-eye" onClick={(e) => { e.stopPropagation(); handleView(row); }} />
          <Button variant="default" size="sm" icon="ph ph-trash" onClick={(e) => { e.stopPropagation(); handleRemove(row); }} />
        </div>
      ),
    },
  ];

  return (
    <div className={styles.trustStore}>
      <PageTopBar
        icon="ph ph-shield-check"
        title="Trust Store"
        badge={<Badge variant="success">{trustedCAs.length} Trusted CAs</Badge>}
        actions={
          <>
            <Button icon="ph ph-arrows-clockwise" onClick={handleSync} disabled={syncTrustStore.isPending}>
              {syncTrustStore.isPending ? 'Syncing...' : 'Sync Trust Store'}
            </Button>
            <Button variant="primary" icon="ph ph-plus" onClick={() => setShowAddModal(true)}>
              Add CA
            </Button>
          </>
        }
      />

      <StatsGrid columns={4}>
        <StatCard
          value="12"
          label="Trusted CAs"
          icon="ph ph-certificate"
        />
        <StatCard
          value="45"
          label="System Trust Store"
          icon="ph ph-package"
        />
        <StatCard
          value="2 days ago"
          label="Last Updated"
          icon="ph ph-clock"
        />
        <StatCard
          value={
            <Badge variant="success">
              <i className="ph ph-check-circle" style={{ marginRight: '4px' }} />
              Enabled
            </Badge>
          }
          label="Auto-Sync Status"
          icon="ph ph-arrows-clockwise"
        />
      </StatsGrid>

      <Card>
        <Card.Header>
          <h3>Trusted Certificate Authorities</h3>
          <Button variant="default" icon="ph ph-funnel">
            Filter
          </Button>
        </Card.Header>
        <Card.Body>
          <DataTable
            columns={columns}
            data={trustedCAs}
            loading={isLoading}
            onRowClick={(row) => console.log('CA clicked:', row)}
            pageSize={10}
          />
        </Card.Body>
      </Card>

      {/* Modals */}
      <ViewCertificateModal 
        isOpen={showViewModal} 
        onClose={() => setShowViewModal(false)} 
        certificate={selectedCert}
      />
      <AddCAToTrustStoreModal 
        isOpen={showAddModal} 
        onClose={() => setShowAddModal(false)}
      />
    </div>
  );
}

export default TrustStore;
