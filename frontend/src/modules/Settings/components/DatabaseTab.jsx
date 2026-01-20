import React, { useState, useEffect } from 'react';
import { Card, Text, Group, Badge, Button, Stack, Loader, Grid, SimpleGrid, ThemeIcon, Alert } from '@mantine/core';
import { Database, HardDrives, Trash, Download, Upload, CheckCircle, Warning, ArrowsClockwise } from '@phosphor-icons/react';
import { api } from '../../../core/api/client';

const StatCard = ({ label, value, subtext }) => (
    <Card withBorder padding="sm" radius="md">
        <Text size="xs" color="dimmed" transform="uppercase" weight={700}>{label}</Text>
        <Text size="xl" weight={700} mt={4}>{value}</Text>
        {subtext && <Text size="xs" color="dimmed">{subtext}</Text>}
    </Card>
);

const DatabaseTab = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
      try {
          const res = await api.get('/system/db/stats');
          setStats(res.data);
      } catch (err) {
          console.error("Failed to load db stats", err);
      } finally {
          setLoading(false);
      }
  };

  const handleAction = async (action, endpoint) => {
      if (!window.confirm(`Are you sure you want to run: ${action}?`)) return;
      
      setProcessing(true);
      try {
          const res = await api.post(endpoint);
          alert(res.message || "Operation successful");
          loadStats(); // Refresh stats
      } catch (err) {
          alert("Operation failed: " + err.message);
      } finally {
          setProcessing(false);
      }
  };

  if (loading) return <Loader />;

  return (
    <Stack spacing="lg">
      {/* Statistics */}
      <Card withBorder padding="lg" radius="md">
          <Group mb="md">
            <Database size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">Database Statistics</Text>
          </Group>
          
          <SimpleGrid cols={4} breakpoints={[{ maxWidth: 'sm', cols: 2 }]}>
              <StatCard label="Size" value={`${stats?.size_mb} MB`} />
              <StatCard label="Fragmentation" value={`${stats?.fragmentation_percent}%`} />
              <StatCard label="Certificates" value={stats?.counts?.certificates} />
              <StatCard label="Revocations (CRL)" value={stats?.counts?.crls} />
          </SimpleGrid>
      </Card>

      {/* Maintenance */}
      <Card withBorder padding="lg" radius="md">
          <Group mb="md">
            <ArrowsClockwise size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">Maintenance Operations</Text>
          </Group>
          
          <Stack spacing="md">
              <Group position="apart" noWrap>
                  <div>
                      <Text weight={500}>Optimize Database</Text>
                      <Text size="sm" color="dimmed">Run VACUUM and ANALYZE to reclaim space and improve performance.</Text>
                  </div>
                  <Button variant="light" onClick={() => handleAction('Optimize', '/system/db/optimize')} disabled={processing}>
                      Optimize
                  </Button>
              </Group>
              
              <Group position="apart" noWrap>
                  <div>
                      <Text weight={500}>Integrity Check</Text>
                      <Text size="sm" color="dimmed">Verify database integrity and detect corruption.</Text>
                  </div>
                  <Button variant="light" onClick={() => handleAction('Integrity Check', '/system/db/integrity-check')} disabled={processing}>
                      Check
                  </Button>
              </Group>

              <Group position="apart" noWrap>
                  <div>
                      <Text weight={500}>Export SQL Dump</Text>
                      <Text size="sm" color="dimmed">Download a complete SQL dump of the database.</Text>
                  </div>
                  <Button variant="light" leftSection={<Download size={16} />} disabled={processing} onClick={() => window.open('/api/v2/system/db/export')}>
                      Export
                  </Button>
              </Group>
          </Stack>
      </Card>

       {/* Backup & Restore */}
       <Card withBorder padding="lg" radius="md">
          <Group mb="md">
            <HardDrives size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">Backup & Restore</Text>
          </Group>

          <Stack spacing="md">
            <Alert icon={<Warning size={16} />} color="blue" variant="light">
                Backups are encrypted with AES-256-GCM. Keep your password safe.
            </Alert>
            
            <Group>
                <div style={{ flex: 1 }}>
                    <Button 
                        leftSection={<Download size={16} />} 
                        color="blue"
                        mb={4}
                        onClick={() => handleAction('Create Backup', '/system/backup/create')}
                    >
                        Full PKI Backup
                    </Button>
                    <Text size="xs" color="dimmed" style={{ lineHeight: 1.4 }}>
                        Generates a single linear JSON file containing everything: CAs, Certificates, Users, Configuration, ACME Accounts.
                        <br/>• Encrypted with AES-256-GCM (PBKDF2)
                        <br/>• Private keys are individually encrypted
                    </Text>
                </div>
                <Button variant="default" leftSection={<Upload size={16} />} onClick={() => handleAction('Restore Backup', '/system/backup/restore')}>Restore from Backup</Button>
            </Group>
          </Stack>
       </Card>

       {/* Danger Zone */}
       <Card withBorder padding="lg" radius="md" style={{ borderColor: 'var(--mantine-color-red-6)' }}>
          <Group mb="md">
            <Warning size={24} color="red" />
            <Text weight={600} size="lg" color="red">Danger Zone</Text>
          </Group>

          <Group position="apart">
             <div>
                <Text weight={500}>Reset PKI Database</Text>
                <Text size="sm" color="dimmed">This action cannot be undone. All CAs and certificates will be deleted.</Text>
             </div>
             <Button color="red" variant="outline" onClick={() => handleAction('Reset PKI', '/system/db/reset')}>Reset PKI</Button>
          </Group>
       </Card>
    </Stack>
  );
};

export default DatabaseTab;
