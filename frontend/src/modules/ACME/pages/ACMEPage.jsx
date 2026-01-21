import React, { useState, useEffect } from 'react';
import { Globe, GearSix } from '@phosphor-icons/react';
import { Button, Card, Text, Loader, Stack, Group, CodeBlock, CopyButton, StatusBadge } from '../../../components/ui';
import { acmeService } from '../services/acme.service';
import '../../../styles/common-page.css';

const ACMEPage = () => {
  const [stats, setStats] = useState({});
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadACME();
  }, []);

  const loadACME = async () => {
    try {
      setLoading(true);
      const [statsData, settingsData] = await Promise.all([
        acmeService.getStats(),
        acmeService.getSettings()
      ]);
      setStats(statsData || {});
      setSettings(settingsData || {});
    } catch (error) {
      console.error('Failed to load ACME:', error);
    } finally {
      setLoading(false);
    }
  };

  const directoryUrl = `https://${window.location.hostname}:8443/acme/directory`;

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <Globe size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">ACME Protocol</h1>
            <Text className="page-subtitle">Automated Certificate Management</Text>
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
              <h3 className="card-title">Directory URL</h3>
              <CopyButton value={directoryUrl} size="sm" />
            </div>
            <CodeBlock code={directoryUrl} language="url" maxHeight="100px" />
            <Text className="page-subtitle" style={{ marginTop: 'var(--spacing-md)' }}>
              Use this URL with Certbot or other ACME clients
            </Text>
          </Card>

          <Card className="dashboard-card">
            <div className="card-header-custom">
              <h3 className="card-title">Statistics</h3>
            </div>
            <Stack>
              <div className="status-item">
                <Text>Total Accounts</Text>
                <Text className="stat-value">{stats.accounts_count || 0}</Text>
              </div>
              <div className="status-item">
                <Text>Total Orders</Text>
                <Text className="stat-value">{stats.orders_count || 0}</Text>
              </div>
              <div className="status-item">
                <Text>Service Status</Text>
                <StatusBadge status={settings.enabled ? 'active' : 'disabled'} />
              </div>
            </Stack>
          </Card>
        </div>
      )}
    </div>
  );
};

export default ACMEPage;
