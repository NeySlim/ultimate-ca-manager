import { useState } from 'react';
import toast from 'react-hot-toast';
import { PageTopBar, PillFilter, PillFilters, FiltersBar, FilterGroup } from '../../components/common';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import ErrorState from '../../components/ui/ErrorState';
import { useCertificates, useRevokeCertificate } from '../../hooks/useCertificates';
import { IssueCertificateModal } from '../../components/modals/IssueCertificateModal';
import { ImportCertificateModal } from '../../components/modals/ImportCertificateModal';
import { exportTableData } from '../../utils/export';
import styles from './CertificateList.module.css';

export function CertificateList() {
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('name');
  const [showIssueModal, setShowIssueModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);

  const { data: certsResponse, isLoading, error } = useCertificates();
  const { mutate: revokeCertificate } = useRevokeCertificate();

  const handleRevokeCertificate = (cert) => {
    if (window.confirm(`Revoke certificate ${cert.name}?`)) {
      revokeCertificate(
        { id: cert.id, reason: 'Revoked by administrator' },
        {
          onSuccess: () => toast.success(`Certificate ${cert.name} revoked successfully`),
          onError: (err) => toast.error(`Failed to revoke certificate: ${err.message}`),
        }
      );
    }
  };

  const handleExport = () => {
    const certs = certsResponse?.data || [];
    if (certs.length === 0) {
      toast.error('No data to export');
      return;
    }
    exportTableData(certs, 'certificates-export', {
      format: 'csv',
      columns: ['id', 'name', 'type', 'status', 'issuedBy', 'daysLeft', 'issued', 'expires']
    });
    toast.success('Certificates exported successfully');
  };

  const handleDownload = (cert) => {
    window.open(`/api/v2/certificates/${cert.id}/download`, '_blank');
  };

  const getDaysLeftBadgeClass = (days) => {
    if (days <= 7) return styles.badgeError;
    if (days <= 30) return styles.badgeWarning;
    return styles.badgeSuccess;
  };

  const getStatusBadgeClass = (status) => {
    if (status === 'CRITICAL') return styles.badgeError;
    if (status === 'EXPIRING SOON') return styles.badgeWarning;
    return styles.badgeSuccess;
  };

  const getTypeBadgeClass = (type) => {
    if (type === 'Server') return styles.badgeInfo;
    if (type === 'Client') return styles.badgeInfo;
    return styles.badgeNeutral;
  };

  if (isLoading) {
    return (
      <div className={styles.certificateList}>
        <PageTopBar
          icon="ph ph-certificate"
          title="Certificates"
          badge={<Badge variant="neutral">Loading...</Badge>}
        />
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} width="100%" height={60} style={{ marginBottom: '8px' }} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.certificateList}>
        <PageTopBar
          icon="ph ph-certificate"
          title="Certificates"
          badge={<Badge variant="danger">Error</Badge>}
        />
        <ErrorState error={error} shake />
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.certificateList}>
        <PageTopBar
          icon="ph ph-certificate"
          title="Certificates"
          badge={<Badge variant="danger">Error</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading certificates: {error.message}
        </div>
      </div>
    );
  }

  const certificates = certsResponse?.data || [];
  const activeCount = certificates.filter(cert => cert.status === 'ACTIVE').length;

  return (
    <div className={styles.certificateList}>
      {/* Page Header */}
      <PageTopBar
        icon="ph ph-certificate"
        title="Certificates"
        badge={<Badge variant="success">{activeCount} Active</Badge>}
        actions={
          <>
            <Button icon="ph ph-upload-simple" onClick={() => setShowImportModal(true)}>Import</Button>
            <Button icon="ph ph-download-simple" onClick={handleExport}>Export</Button>
            <Button 
              variant="primary" 
              icon="ph ph-file-plus"
              onClick={() => setShowIssueModal(true)}
            >
              Issue Certificate
            </Button>
          </>
        }
      />

      {/* Filters Section */}
      <FiltersBar>
        <FilterGroup label="TYPE">
          <PillFilters>
            <PillFilter active={typeFilter === 'all'} onClick={() => setTypeFilter('all')}>
              All <Badge variant="secondary">(247)</Badge>
            </PillFilter>
            <PillFilter active={typeFilter === 'server'} onClick={() => setTypeFilter('server')}>
              Server <Badge variant="secondary">(89)</Badge>
            </PillFilter>
            <PillFilter active={typeFilter === 'client'} onClick={() => setTypeFilter('client')}>
              Client <Badge variant="secondary">(158)</Badge>
            </PillFilter>
            <PillFilter active={typeFilter === 'acme'} onClick={() => setTypeFilter('acme')}>
              ACME <Badge variant="secondary">(34)</Badge>
            </PillFilter>
          </PillFilters>
        </FilterGroup>

        <FilterGroup label="STATUS">
          <PillFilters>
            <PillFilter active={statusFilter === 'all'} onClick={() => setStatusFilter('all')}>
              All <Badge variant="secondary">(247)</Badge>
            </PillFilter>
            <PillFilter active={statusFilter === 'active'} onClick={() => setStatusFilter('active')}>
              Active <Badge variant="secondary">(235)</Badge>
            </PillFilter>
            <PillFilter active={statusFilter === 'expiring'} onClick={() => setStatusFilter('expiring')}>
              Expiring <Badge variant="secondary">(12)</Badge>
            </PillFilter>
            <PillFilter active={statusFilter === 'expired'} onClick={() => setStatusFilter('expired')}>
              Expired <Badge variant="secondary">(0)</Badge>
            </PillFilter>
            <PillFilter active={statusFilter === 'revoked'} onClick={() => setStatusFilter('revoked')}>
              Revoked <Badge variant="secondary">(0)</Badge>
            </PillFilter>
          </PillFilters>
        </FilterGroup>

        <FilterGroup label="SORT">
          <select 
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="name">Name</option>
            <option value="issued">Issued</option>
            <option value="expires">Expires</option>
          </select>
        </FilterGroup>
      </FiltersBar>

      {/* Certificates Table */}
      <div className={styles.tableContainer}>
        <table>
          <thead>
            <tr>
              <th style={{ width: '40%' }}>CERTIFICATE</th>
              <th style={{ width: '10%' }}>TYPE</th>
              <th style={{ width: '15%' }}>ISSUER</th>
              <th style={{ width: '10%' }}>STATUS</th>
              <th style={{ width: '10%' }}>ISSUED</th>
              <th style={{ width: '10%' }}>EXPIRES</th>
              <th style={{ width: '5%' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {certificates.map((cert) => (
              <tr key={cert.id}>
                <td>
                  <div className={styles.certNameCell}>
                    <span className={styles.certName}>{cert.name}</span>
                    <span className={styles.certSerial}>Serial: {cert.serial}</span>
                  </div>
                </td>
                <td>
                  <span className={`${styles.badgeType} ${getTypeBadgeClass(cert.type)}`}>
                    {cert.type}
                  </span>
                </td>
                <td>{cert.issuer}</td>
                <td>
                  <span className={`${styles.badgeStatus} ${getStatusBadgeClass(cert.status)}`}>
                    {cert.status}
                  </span>
                </td>
                <td>{cert.issued}</td>
                <td>
                  <div className={styles.expiresCell}>
                    <span>{cert.expires}</span>
                    <span className={`${styles.badgeDays} ${getDaysLeftBadgeClass(cert.daysLeft)}`}>
                      {cert.daysLeft} DAYS
                    </span>
                  </div>
                </td>
                <td>
                  <div className={styles.actionsCell}>
                    <button 
                      className={styles.actionBtn} 
                      title="Download"
                      onClick={() => handleDownload(cert)}
                    >
                      <i className="ph ph-download-simple"></i>
                    </button>
                    <button 
                      className={styles.actionBtn} 
                      title="Revoke"
                      onClick={() => handleRevokeCertificate(cert)}
                    >
                      <i className="ph ph-x-circle"></i>
                    </button>
                    <button className={styles.actionBtn} title="More">
                      <i className="ph ph-dots-three-outline-vertical"></i>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Issue Certificate Modal */}
      <IssueCertificateModal 
        isOpen={showIssueModal}
        onClose={() => setShowIssueModal(false)}
      />
      
      {/* Import Certificate Modal */}
      <ImportCertificateModal 
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
      />
    </div>
  );
}

export default CertificateList;
