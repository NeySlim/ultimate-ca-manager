import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Certificate,
  Plus,
  MagnifyingGlass,
  Download,
  X,
  Key,
  FileText,
  ShieldCheck,
  Clock,
  Warning,
  CheckCircle,
  Prohibit
} from '@phosphor-icons/react';

// Design System V3
import { Table } from '../../design-system/components/primitives/Table';
import { Button } from '../../design-system/components/primitives/Button';
import { Input } from '../../design-system/components/primitives/Input';
import { Select } from '../../design-system/components/primitives/Select';
import { Badge } from '../../design-system/components/primitives/Badge';
import { GradientBadge } from '../../design-system/components/primitives/GradientBadge';
import { GlassCard } from '../../design-system/components/primitives/GlassCard';
import { Stack } from '../../design-system/components/layout/Stack';
import { Inline } from '../../design-system/components/layout/Inline';
import { Modal } from '../../design-system/components/overlays/Modal';
import { Tabs } from '../../design-system/components/navigation/Tabs';
import { Skeleton } from '../../design-system/components/feedback/Skeleton';

import { useCertificates } from '../../hooks/useCertificates';
import styles from './CertificateListV3.module.css';

// Certificate Details Modal
function CertificateDetailsModal({ certificate, isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('info');

  if (!certificate) return null;

  const tabs = [
    { id: 'info', label: 'Information', icon: <FileText size={16} /> },
    { id: 'chain', label: 'Certificate Chain', icon: <ShieldCheck size={16} /> },
    { id: 'extensions', label: 'Extensions', icon: <Key size={16} /> },
    { id: 'raw', label: 'Raw Data', icon: <Certificate size={16} /> },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title={certificate.common_name || 'Certificate Details'}
    >
      <Stack gap="lg">
        <Tabs
          tabs={tabs}
          activeTab={activeTab}
          onChange={setActiveTab}
        />

        {activeTab === 'info' && (
          <Stack gap="md">
            <div className={styles.detailSection}>
              <h3 className={styles.detailSectionTitle}>Subject</h3>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Common Name</span>
                  <span className={styles.detailValue}>{certificate.common_name}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Organization</span>
                  <span className={styles.detailValue}>{certificate.organization || 'N/A'}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Organizational Unit</span>
                  <span className={styles.detailValue}>{certificate.organizational_unit || 'N/A'}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Country</span>
                  <span className={styles.detailValue}>{certificate.country || 'N/A'}</span>
                </div>
              </div>
            </div>

            <div className={styles.detailSection}>
              <h3 className={styles.detailSectionTitle}>Issuer</h3>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Issuer CN</span>
                  <span className={styles.detailValue}>{certificate.issuer_cn}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Issuer Organization</span>
                  <span className={styles.detailValue}>{certificate.issuer_org || 'N/A'}</span>
                </div>
              </div>
            </div>

            <div className={styles.detailSection}>
              <h3 className={styles.detailSectionTitle}>Validity</h3>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Valid From</span>
                  <span className={styles.detailValue}>{certificate.valid_from}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Valid Until</span>
                  <span className={styles.detailValue}>{certificate.valid_until}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Expires In</span>
                  <span className={styles.detailValue}>
                    <Badge variant={certificate.days_left < 30 ? 'warning' : 'success'}>
                      {certificate.expires_in}
                    </Badge>
                  </span>
                </div>
              </div>
            </div>

            <div className={styles.detailSection}>
              <h3 className={styles.detailSectionTitle}>Identifiers</h3>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>Serial Number</span>
                  <span className={styles.detailValueMono}>{certificate.serial_number}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>SHA-256 Fingerprint</span>
                  <span className={styles.detailValueMono}>{certificate.fingerprint_sha256}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>SHA-1 Fingerprint</span>
                  <span className={styles.detailValueMono}>{certificate.fingerprint_sha1}</span>
                </div>
              </div>
            </div>
          </Stack>
        )}

        {activeTab === 'chain' && (
          <Stack gap="sm">
            {certificate.chain?.map((cert, idx) => (
              <GlassCard key={idx} blur="sm">
                <Inline gap="md" align="center">
                  <ShieldCheck size={24} weight="duotone" />
                  <div style={{ flex: 1 }}>
                    <div className={styles.chainCertName}>{cert.common_name}</div>
                    <div className={styles.chainCertMeta}>{cert.type} • {cert.organization}</div>
                  </div>
                  <Badge variant={cert.valid ? 'success' : 'danger'}>
                    {cert.valid ? 'Valid' : 'Invalid'}
                  </Badge>
                </Inline>
              </GlassCard>
            )) || <p style={{ color: 'var(--color-text-secondary)' }}>No chain information available</p>}
          </Stack>
        )}

        {activeTab === 'extensions' && (
          <Stack gap="sm">
            {certificate.extensions?.map((ext, idx) => (
              <div key={idx} className={styles.extensionItem}>
                <div className={styles.extensionName}>{ext.name}</div>
                <div className={styles.extensionValue}>{ext.value}</div>
                {ext.critical && <Badge variant="warning" size="sm">Critical</Badge>}
              </div>
            )) || <p style={{ color: 'var(--color-text-secondary)' }}>No extensions</p>}
          </Stack>
        )}

        {activeTab === 'raw' && (
          <div className={styles.rawData}>
            <pre>{certificate.pem || 'No PEM data available'}</pre>
          </div>
        )}

        <Inline gap="sm" justify="end">
          <Button variant="secondary" leftIcon={<Download size={18} />}>
            Download PEM
          </Button>
          <Button variant="secondary" leftIcon={<Download size={18} />}>
            Download DER
          </Button>
          <Button variant="danger" leftIcon={<Prohibit size={18} />}>
            Revoke
          </Button>
        </Inline>
      </Stack>
    </Modal>
  );
}

export function CertificateListV3() {
  const navigate = useNavigate();
  const { data: certificates, isLoading } = useCertificates();

  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedCert, setSelectedCert] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const handleClearFilters = () => {
    setSearchQuery('');
    setTypeFilter('all');
    setStatusFilter('all');
  };

  const handleRowClick = (cert) => {
    setSelectedCert(cert);
    setDetailsOpen(true);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'valid': return <CheckCircle size={14} weight="fill" />;
      case 'expiring': return <Warning size={14} weight="fill" />;
      case 'expired': return <Clock size={14} weight="fill" />;
      case 'revoked': return <Prohibit size={14} weight="fill" />;
      default: return null;
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'valid': return 'success';
      case 'expiring': return 'warning';
      case 'expired': return 'danger';
      case 'revoked': return 'danger';
      default: return 'default';
    }
  };

  const getTypeVariant = (type) => {
    switch (type) {
      case 'server': return 'blue';
      case 'client': return 'green';
      case 'email': return 'purple';
      case 'code-signing': return 'orange';
      default: return 'blue';
    }
  };

  // Filter certificates
  const filteredCertificates = certificates?.filter(cert => {
    if (searchQuery && !cert.common_name?.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    if (typeFilter !== 'all' && cert.type !== typeFilter) {
      return false;
    }
    if (statusFilter !== 'all' && cert.status !== statusFilter) {
      return false;
    }
    return true;
  });

  const columns = [
    {
      key: 'common_name',
      label: 'Common Name',
      sortable: true,
      width: '25%',
      render: (cert) => (
        <div>
          <div className={styles.certName}>{cert.common_name}</div>
          <div className={styles.certSerial}>{cert.serial_number?.substring(0, 24)}...</div>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'Type',
      sortable: true,
      width: '12%',
      render: (cert) => (
        <GradientBadge variant={getTypeVariant(cert.type)} size="sm">
          {cert.type}
        </GradientBadge>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      width: '12%',
      render: (cert) => (
        <Badge variant={getStatusVariant(cert.status)}>
          <Inline gap="xs" align="center">
            {getStatusIcon(cert.status)}
            <span>{cert.status}</span>
          </Inline>
        </Badge>
      ),
    },
    {
      key: 'issuer_cn',
      label: 'Issuer',
      sortable: true,
      width: '20%',
      render: (cert) => (
        <div className={styles.issuer}>{cert.issuer_cn}</div>
      ),
    },
    {
      key: 'valid_until',
      label: 'Expires',
      sortable: true,
      width: '18%',
      render: (cert) => (
        <div>
          <div className={styles.expiryDate}>{cert.valid_until}</div>
          <Badge 
            variant={cert.days_left < 7 ? 'danger' : cert.days_left < 30 ? 'warning' : 'default'}
            size="sm"
          >
            <Clock size={12} weight="bold" />
            {cert.expires_in}
          </Badge>
        </div>
      ),
    },
  ];

  const hasFilters = searchQuery || typeFilter !== 'all' || statusFilter !== 'all';

  return (
    <div className={styles.container}>
      <Stack gap="xl">
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Certificates</h1>
            <p className={styles.subtitle}>
              {filteredCertificates?.length || 0} certificate{filteredCertificates?.length !== 1 ? 's' : ''}
            </p>
          </div>
          <Button 
            variant="primary" 
            leftIcon={<Plus size={20} weight="bold" />}
            onClick={() => navigate('/certificates/new')}
          >
            Issue Certificate
          </Button>
        </div>

        {/* Filters Bar */}
        <GlassCard blur="md">
          <div className={styles.filtersBar}>
            <Input
              placeholder="Search certificates..."
              leftIcon={<MagnifyingGlass size={18} />}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: '300px' }}
            />
            
            <Select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              style={{ width: '180px' }}
            >
              <option value="all">All Types</option>
              <option value="server">Server Auth</option>
              <option value="client">Client Auth</option>
              <option value="email">Email</option>
              <option value="code-signing">Code Signing</option>
            </Select>

            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ width: '160px' }}
            >
              <option value="all">All Status</option>
              <option value="valid">Valid</option>
              <option value="expiring">Expiring Soon</option>
              <option value="expired">Expired</option>
              <option value="revoked">Revoked</option>
            </Select>

            {hasFilters && (
              <Button 
                variant="ghost" 
                size="sm" 
                leftIcon={<X size={16} />}
                onClick={handleClearFilters}
              >
                Clear
              </Button>
            )}
          </div>
        </GlassCard>

        {/* Table */}
        <Table
          columns={columns}
          data={filteredCertificates || []}
          isLoading={isLoading}
          selectable={true}
          striped={true}
          hoverable={true}
          onRowClick={handleRowClick}
          emptyMessage={hasFilters ? "No certificates match your filters" : "No certificates found"}
          emptyIcon={<Certificate size={64} />}
        />
      </Stack>

      {/* Details Modal */}
      <CertificateDetailsModal
        certificate={selectedCert}
        isOpen={detailsOpen}
        onClose={() => setDetailsOpen(false)}
      />
    </div>
  );
}

export default CertificateListV3;
