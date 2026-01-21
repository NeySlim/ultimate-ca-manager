import { PageTopBar, StatsGrid, StatCard } from '../../components/common';
import { DataTable } from '../../components/domain/DataTable';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import styles from './TrustStore.module.css';

export function TrustStore() {
  const trustedCAs = [
    {
      id: 1,
      name: 'DigiCert Global Root CA',
      subject: 'CN=DigiCert Global Root CA',
      fingerprint: 'A8:98:5D:3A:65:E5:...',
      validUntil: '2031-11-10',
      usage: ['TLS Server', 'TLS Client'],
      autoTrusted: true,
    },
    {
      id: 2,
      name: "Let's Encrypt Root CA X1",
      subject: 'CN=ISRG Root X1',
      fingerprint: '96:BC:EC:06:26:49:...',
      validUntil: '2035-06-04',
      usage: ['TLS Server'],
      autoTrusted: true,
    },
    {
      id: 3,
      name: 'Corporate Root CA',
      subject: 'CN=Corp Root CA, O=Example Corp',
      fingerprint: '4F:3A:B2:C8:9D:E1:...',
      validUntil: '2034-01-15',
      usage: ['TLS Server', 'TLS Client', 'Email'],
      autoTrusted: false,
    },
    {
      id: 4,
      name: 'Internal Development CA',
      subject: 'CN=Dev CA, O=Example Corp',
      fingerprint: '7B:2F:8A:D3:E6:4C:...',
      validUntil: '2026-08-20',
      usage: ['TLS Server', 'Code Signing'],
      autoTrusted: false,
    },
    {
      id: 5,
      name: 'GlobalSign Root CA',
      subject: 'CN=GlobalSign',
      fingerprint: 'EB:D4:10:40:E4:BB:...',
      validUntil: '2028-01-28',
      usage: ['TLS Server', 'TLS Client'],
      autoTrusted: true,
    },
  ];

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
          <Button variant="default" size="sm" icon="ph ph-eye" onClick={() => console.log('View:', row)} />
          <Button variant="default" size="sm" icon="ph ph-trash" onClick={() => console.log('Remove:', row)} />
        </div>
      ),
    },
  ];

  return (
    <div className={styles.trustStore}>
      <PageTopBar
        icon="ph ph-shield-check"
        title="Trust Store"
        badge={<Badge variant="success">12 Trusted CAs</Badge>}
        actions={
          <>
            <Button icon="ph ph-arrows-clockwise">Sync Trust Store</Button>
            <Button variant="primary" icon="ph ph-plus">Add CA</Button>
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
            onRowClick={(row) => console.log('CA clicked:', row)}
            pageSize={10}
          />
        </Card.Body>
      </Card>
    </div>
  );
}

export default TrustStore;
