import { useState } from 'react';
import { PageTopBar, PillFilter, PillFilters, FiltersBar, FilterGroup } from '../../components/common';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import styles from './CertificateList.module.css';

// Mock Certificates Data
const MOCK_CERTIFICATES = [
  {
    id: 1,
    name: 'mail.example.com',
    serial: '3d2f5a1e8b4c...',
    type: 'Server',
    issuer: 'Server CA',
    status: 'CRITICAL',
    issued: '2023-10-15',
    expires: '2024-10-15',
    daysLeft: 7,
  },
  {
    id: 2,
    name: 'vpn.internal.net',
    serial: '7c9e1a4b2f6d...',
    type: 'Server',
    issuer: 'Server CA',
    status: 'EXPIRING SOON',
    issued: '2023-09-20',
    expires: '2024-09-20',
    daysLeft: 12,
  },
  {
    id: 3,
    name: 'api.service.com',
    serial: '4a8d1f5c3b9e...',
    type: 'ACME',
    issuer: 'ACME CA',
    status: 'ACTIVE',
    issued: '2024-01-10',
    expires: '2025-01-10',
    daysLeft: 234,
  },
  {
    id: 4,
    name: 'john.doe@acme.com',
    serial: '9b2a7d5e1c4f...',
    type: 'Client',
    issuer: 'Client CA',
    status: 'ACTIVE',
    issued: '2023-12-05',
    expires: '2026-12-05',
    daysLeft: 710,
  },
  {
    id: 5,
    name: 'ldap.corp.local',
    serial: '5f3b8a1d7c2e...',
    type: 'Server',
    issuer: 'Server CA',
    status: 'EXPIRING SOON',
    issued: '2023-09-05',
    expires: '2024-09-05',
    daysLeft: 15,
  },
  {
    id: 6,
    name: '*.dev.local',
    serial: '1e4a6f9b3c5d...',
    type: 'Server',
    issuer: 'Dev CA',
    status: 'ACTIVE',
    issued: '2024-02-01',
    expires: '2025-02-01',
    daysLeft: 210,
  },
  {
    id: 7,
    name: 'admin@acme.com',
    serial: '8d2c7f4a1b6e...',
    type: 'Client',
    issuer: 'Client CA',
    status: 'ACTIVE',
    issued: '2023-11-20',
    expires: '2026-11-20',
    daysLeft: 725,
  },
  {
    id: 8,
    name: 'netsuit.lan.pew.pet',
    serial: '1c0f1c7e8b2d...',
    type: 'Server',
    issuer: 'Enterprise Root CA',
    status: 'ACTIVE',
    issued: '2020-03-15',
    expires: '2030-03-15',
    daysLeft: 2034,
  },
  {
    id: 9,
    name: 'api.internal.net',
    serial: '2b5e0a3d1f7c...',
    type: 'Server',
    issuer: 'Server CA',
    status: 'ACTIVE',
    issued: '2024-01-25',
    expires: '2025-01-25',
    daysLeft: 219,
  },
  {
    id: 10,
    name: 'mobile-device-001',
    serial: '6c1e4e8b3f8d...',
    type: 'Client',
    issuer: 'Mobile Device CA',
    status: 'ACTIVE',
    issued: '2024-03-10',
    expires: '2027-03-10',
    daysLeft: 1095,
  },
];

export function CertificateList() {
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('name');

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

  return (
    <div className={styles.certificateList}>
      {/* Page Header */}
      <PageTopBar
        icon="ph ph-certificate"
        title="Certificates"
        badge={<Badge variant="success">247 Active</Badge>}
        actions={
          <>
            <Button icon="ph ph-upload-simple">Import</Button>
            <Button icon="ph ph-download-simple">Export</Button>
            <Button variant="primary" icon="ph ph-file-plus">Issue Certificate</Button>
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
            {MOCK_CERTIFICATES.map((cert) => (
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
                    <button className={styles.actionBtn} title="Download">
                      <i className="ph ph-download-simple"></i>
                    </button>
                    <button className={styles.actionBtn} title="Renew">
                      <i className="ph ph-arrow-clockwise"></i>
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
    </div>
  );
}

export default CertificateList;
