import React, { useState, useEffect } from 'react';
import { Devices, GearSix } from '@phosphor-icons/react';
import { Button, Card, Text, Loader, Stack, CodeBlock, CopyButton, StatusBadge } from '../../../components/ui';
import { scepService } from '../services/scep.service';
import '../../../styles/common-page.css';

const SCEPPage = () => {
  const [stats, setStats] = useState({});
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSCEP();
  }, []);

  const loadSCEP = async () => {
    try {
      setLoading(true);
      const [statsData, configData] = await Promise.all([
        scepService.getStats(),
        scepService.getConfig()
      ]);
      setStats(statsData || {});
      setConfig(configData || {});
    } catch (error) {
      console.error('Failed to load SCEP:', error);
    } finally {
      setLoading(false);
    }
  };

  const scepUrl = `https://${window.location.hostname}:8443/scep/pkiclient.exe`;

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <Devices size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">SCEP Server</h1>
            <Text className="page-subtitle">Simple Certificate Enrollment Protocol</Text>
          </div>
        </div>
        <Button variant="primary">
          <GearSix size={16} />
          Configure
        </Button>
      </div>

      {loading ? (
        <div className="loading-center"><Loader /></div>
      ) : (
        <div className="dashboard-grid">
          <Card className="dashboard-card">
            <div className="card-header-custom">
              <h3 className="card-title">Endpoint URL</h3>
              <CopyButton value={scepUrl} size="sm" />
            </div>
            <CodeBlock code={scepUrl} language="url" maxHeight="100px" />
            <Text className="page-subtitle" style={{ marginTop: 'var(--spacing-md)' }}>
              Use this URL to configure SCEP clients
            </Text>
          </Card>

          <Card className="dashboard-card">
            <div className="card-header-custom">
              <h3 className="card-title">Statistics</h3>
            </div>
            <Stack>
              <div className="status-item">
                <Text>Total Requests</Text>
                <Text className="stat-value">{stats.requests_count || 0}</Text>
              </div>
              <div className="status-item">
                <Text>Pending</Text>
                <Text className="stat-value">{stats.pending_count || 0}</Text>
              </div>
              <div className="status-item">
                <Text>Service Status</Text>
                <StatusBadge status={config.enabled ? 'active' : 'disabled'} />
              </div>
            </Stack>
          </Card>
        </div>
      )}
    </div>
  );
};

export default SCEPPage;
