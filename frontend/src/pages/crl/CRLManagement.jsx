import { Tabs } from '../../components/ui/Tabs';
import { StatCard } from '../../components/domain/StatCard';
import { DataTable } from '../../components/domain/DataTable';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { getCRLStats, getOCSPStats } from '../../services/mockData';
import styles from './CRLManagement.module.css';

/**
 * CRL/OCSP Management Page
 * 
 * Two tabs:
 * - CRL Management (generation, stats)
 * - OCSP Configuration (responder config, stats)
 */
export function CRLManagement() {
  const crlStats = getCRLStats();
  const ocspStats = getOCSPStats();

  const crlColumns = [
    {
      key: 'name',
      label: 'CA Name',
      sortable: true,
    },
    {
      key: 'crlSize',
      label: 'CRL Size',
      sortable: true,
    },
    {
      key: 'revocations',
      label: 'Revocations',
      sortable: true,
      render: (row) => (
        <span style={{ color: 'var(--text-tertiary)' }}>
          {row.revocations}
        </span>
      ),
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
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div className={styles.actions}>
          <Button variant="primary" icon="ph ph-arrow-clockwise" onClick={() => console.log('Regenerate:', row)}>
            Regenerate
          </Button>
          <Button variant="default" icon="ph ph-download-simple" onClick={() => console.log('Download:', row)}>
            Download
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.crlManagement}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>CRL Management</Tabs.Tab>
          <Tabs.Tab>OCSP Configuration</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* CRL Management Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              {/* Stats */}
              <div className={styles.statsGrid}>
                <StatCard
                  value={crlStats.totalCRLs}
                  label="Total CRLs"
                  icon="list-checks"
                  gradient
                />
                <StatCard
                  value={crlStats.totalRevocations}
                  label="Total Revocations"
                  icon="x-circle"
                  gradient
                />
              </div>

              {/* CRL Table */}
              <Card>
                <Card.Header>
                  <h3>CRL Status by CA</h3>
                  <Button variant="primary" icon="ph ph-arrow-clockwise">
                    Regenerate All
                  </Button>
                </Card.Header>
                <Card.Body>
                  <DataTable
                    columns={crlColumns}
                    data={crlStats.cas}
                    onRowClick={(row) => console.log('CA clicked:', row)}
                  />
                </Card.Body>
              </Card>

              {/* Info Box */}
              <Card className={styles.infoBox}>
                <Card.Body>
                  <div className={styles.infoContent}>
                    <div className={styles.infoIcon}>
                      <i className="ph ph-info" />
                    </div>
                    <div>
                      <div className={styles.infoTitle}>Automatic CRL Generation</div>
                      <div className={styles.infoText}>
                        CRLs are automatically regenerated every 24 hours. You can manually regenerate a CRL at any time.
                        Last automatic generation: {crlStats.lastGenerated}
                      </div>
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* OCSP Configuration Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              {/* Stats */}
              <div className={styles.statsGrid}>
                <StatCard
                  value={ocspStats.requests24h}
                  label="Requests (24h)"
                  icon="activity"
                  gradient
                />
                <StatCard
                  value={ocspStats.avgResponseTime}
                  label="Avg Response Time"
                  icon="clock"
                  gradient
                />
                <StatCard
                  value={ocspStats.cacheHitRate}
                  label="Cache Hit Rate"
                  icon="database"
                  gradient
                />
              </div>

              {/* OCSP Configuration */}
              <Card>
                <Card.Header>
                  <h3>OCSP Responder Configuration</h3>
                  <div className={styles.statusBadge}>
                    <span className={styles.statusDot} data-status={ocspStats.responderStatus} />
                    <span>{ocspStats.responderStatus}</span>
                  </div>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input
                      label="OCSP Responder URL"
                      value={ocspStats.responderUrl}
                      readOnly
                    />
                    <Input
                      label="Total Requests"
                      value={ocspStats.requestsTotal.toLocaleString()}
                      readOnly
                    />
                    <Input
                      label="Last Restart"
                      value={ocspStats.lastRestart}
                      readOnly
                    />
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-play">
                        Restart Responder
                      </Button>
                      <Button variant="default" icon="ph ph-check-circle">
                        Test OCSP
                      </Button>
                      <Button variant="default" icon="ph ph-gear">
                        Configure
                      </Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>

              {/* Info Box */}
              <Card className={styles.infoBox}>
                <Card.Body>
                  <div className={styles.infoContent}>
                    <div className={styles.infoIcon}>
                      <i className="ph ph-info" />
                    </div>
                    <div>
                      <div className={styles.infoTitle}>About OCSP</div>
                      <div className={styles.infoText}>
                        The OCSP responder provides real-time certificate status information to clients.
                        It uses a cache to improve performance and reduce database load.
                      </div>
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default CRLManagement;
