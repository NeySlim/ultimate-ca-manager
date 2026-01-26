import React, { useState, useEffect } from 'react';
import { Sliders, Database, ShieldCheck, Bell, Envelope, Webhook } from '@phosphor-icons/react';
import { Card, Text, Button, Loader, Stack, Tabs, StatusBadge } from '../../../components/ui';
import { settingsService } from '../services/settings.service';
import '../../../styles/common-page.css';

const SettingsPage = () => {
  const [loading, setLoading] = useState(false);
  const [dbStats, setDbStats] = useState({});

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const stats = await settingsService.getDbStats();
      setDbStats(stats || {});
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <Sliders size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">Settings</h1>
            <Text className="page-subtitle">System Configuration & Maintenance</Text>
          </div>
        </div>
      </div>

      <Tabs defaultValue="general">
        <Tabs.List>
          <Tabs.Tab value="general">General</Tabs.Tab>
          <Tabs.Tab value="database">Database</Tabs.Tab>
          <Tabs.Tab value="security">Security</Tabs.Tab>
          <Tabs.Tab value="notifications">Notifications</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="general">
          <Card style={{ marginTop: 'var(--spacing-md)', padding: 'var(--spacing-lg)' }}>
            <h3 className="card-title">General Settings</h3>
            <Text className="page-subtitle">Application name, FQDN, and other general settings</Text>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="database">
          <Card style={{ marginTop: 'var(--spacing-md)', padding: 'var(--spacing-lg)' }}>
            <div className="card-header-custom">
              <h3 className="card-title">Database Management</h3>
              <Button size="sm" onClick={loadSettings}>Refresh</Button>
            </div>
            
            {loading ? (
              <div className="loading-center"><Loader /></div>
            ) : (
              <Stack>
                <div className="status-item">
                  <Text>Database Size</Text>
                  <Text className="stat-value">{dbStats.size || '0 MB'}</Text>
                </div>
                <div className="status-item">
                  <Text>Total Records</Text>
                  <Text className="stat-value">{dbStats.total_records || 0}</Text>
                </div>
                <div className="status-item">
                  <Text>Last Optimized</Text>
                  <Text className="stat-value">{dbStats.last_optimized || 'Never'}</Text>
                </div>
              </Stack>
            )}

            <div style={{ marginTop: 'var(--spacing-lg)', display: 'flex', gap: 'var(--spacing-sm)' }}>
              <Button variant="primary" onClick={() => settingsService.optimizeDb()}>
                Optimize Database
              </Button>
              <Button onClick={() => settingsService.integrityCheck()}>
                Integrity Check
              </Button>
            </div>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="security">
          <Card style={{ marginTop: 'var(--spacing-md)', padding: 'var(--spacing-lg)' }}>
            <h3 className="card-title">Security Settings</h3>
            <Text className="page-subtitle">HTTPS, mTLS, and authentication settings</Text>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="notifications">
          <Card style={{ marginTop: 'var(--spacing-md)', padding: 'var(--spacing-lg)' }}>
            <h3 className="card-title">Notification Settings</h3>
            <Text className="page-subtitle">Email and webhook notifications</Text>
          </Card>
        </Tabs.Panel>
      </Tabs>
    </div>
  );
};

export default SettingsPage;
