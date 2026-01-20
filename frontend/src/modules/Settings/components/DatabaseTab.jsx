import React, { useState, useEffect } from 'react';
import { Card, Text, Group, Badge, Button, Stack, Loader, Grid, SimpleGrid, ThemeIcon, Alert, Table, Modal, PasswordInput } from '@mantine/core';
import { Database, HardDrives, Trash, Download, Upload, CheckCircle, Warning, ArrowsClockwise, FileArchive } from '@phosphor-icons/react';
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
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [backupModalOpen, setBackupModalOpen] = useState(false);
  const [backupPassword, setBackupPassword] = useState('');
  const [selectedBackup, setSelectedBackup] = useState(null);
  const fileInputRef = React.useRef(null);

  useEffect(() => {
    loadStats();
    loadBackups();
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

  const loadBackups = async () => {
      try {
          const res = await api.get('/system/backup/list');
          setBackups(res.data || []);
      } catch (err) {
          console.error("Failed to load backups", err);
      }
  };

  const handleCreateBackup = async () => {
      if (!backupPassword || backupPassword.length < 12) {
          alert("Password must be at least 12 characters");
          return;
      }
      
      setProcessing(true);
      try {
          await api.post('/system/backup/create', { password: backupPassword });
          setBackupModalOpen(false);
          setBackupPassword('');
          loadBackups();
          alert("Backup created successfully");
      } catch (err) {
          alert("Backup failed: " + err.message);
      } finally {
          setProcessing(false);
      }
  };

  const handleRestoreFromFile = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (!window.confirm(`Are you sure you want to restore from file: ${file.name}? Current data will be overwritten.`)) {
        event.target.value = null;
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setProcessing(true);
    try {
        const res = await api.post('/system/backup/restore', formData);
        alert(res.message || "Restore successful. System restarting...");
        loadStats();
    } catch (err) {
        alert("Restore failed: " + err.message);
    } finally {
        setProcessing(false);
        event.target.value = null;
    }
  };

  const handleRestoreSelected = async () => {
    if (!selectedBackup) return;
    
    if (!window.confirm(`Are you sure you want to restore from server backup: ${selectedBackup}? Current data will be overwritten.`)) return;

    setProcessing(true);
    try {
        const res = await api.post('/system/backup/restore', { filename: selectedBackup });
        alert(res.message || "Restore successful. System restarting...");
        loadStats();
    } catch (err) {
        alert("Restore failed: " + err.message);
    } finally {
        setProcessing(false);
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

  if (loading) return <div className="spinner" />;

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
            
            <input 
                type="file" 
                ref={fileInputRef} 
                style={{ display: 'none' }} 
                accept=".ucmbkp,.json.enc"
                onChange={handleRestoreFromFile}
            />

            <SimpleGrid cols={3}>
                <Button 
                    leftSection={<Download size={16} />} 
                    color="blue"
                    onClick={() => setBackupModalOpen(true)}
                    fullWidth
                >
                    Create Full PKI Backup
                </Button>
                <Button 
                    variant="default" 
                    leftSection={<Upload size={16} />} 
                    onClick={() => fileInputRef.current?.click()}
                    fullWidth
                    loading={processing}
                >
                    Restore from File
                </Button>
                <Button 
                    variant="light" 
                    color="orange"
                    leftSection={<ArrowsClockwise size={16} />} 
                    onClick={handleRestoreSelected}
                    disabled={!selectedBackup || processing}
                    fullWidth
                >
                    Restore Selected Backup
                </Button>
            </SimpleGrid>
            
            <Text size="xs" color="dimmed" align="center">
                Generates a single linear JSON file containing everything: CAs, Certificates, Users, Configuration, ACME Accounts.
            </Text>

            <Text weight={600} size="sm" mt="md">Available Backups</Text>
            {backups.length === 0 ? (
                <Text size="sm" color="dimmed" fs="italic">No backups found.</Text>
            ) : (
                <Table striped highlightOnHover withBorder>
                    <thead>
                        <tr>
                            <th>Filename</th>
                            <th>Date</th>
                            <th>Size</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {backups.map((b) => (
                            <tr 
                                key={b.filename} 
                                onClick={() => setSelectedBackup(b.filename)}
                                style={{ 
                                    cursor: 'pointer',
                                    backgroundColor: selectedBackup === b.filename ? 'var(--mantine-color-blue-light)' : undefined
                                }}
                            >
                                <td style={{ fontFamily: 'var(--font-mono)' }}>
                                    <Group spacing="xs">
                                        {selectedBackup === b.filename && <CheckCircle size={14} color="var(--mantine-color-blue-6)" />}
                                        {b.filename}
                                    </Group>
                                </td>
                                <td>{new Date(b.created_at).toLocaleString()}</td>
                                <td>{(b.size / 1024).toFixed(2)} KB</td>
                                <td>
                                    <Button 
                                        component="a" 
                                        href={b.download_url} 
                                        variant="subtle" 
                                        size="xs" 
                                        leftSection={<Download size={14}/>}
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        Download
                                    </Button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </Table>
            )}
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

       <Modal opened={backupModalOpen} onClose={() => setBackupModalOpen(false)} title="Create Encrypted Backup">
           <Stack>
               <Text size="sm">Enter a strong password to encrypt this backup archive.</Text>
               <PasswordInput 
                    label="Encryption Password" 
                    placeholder="Min 12 characters" 
                    value={backupPassword}
                    onChange={(e) => setBackupPassword(e.target.value)}
                    required
               />
               <Group position="right" mt="md">
                   <Button variant="default" onClick={() => setBackupModalOpen(false)}>Cancel</Button>
                   <Button onClick={handleCreateBackup} loading={processing}>Create Backup</Button>
               </Group>
           </Stack>
       </Modal>
    </Stack>
  );
};

export default DatabaseTab;
