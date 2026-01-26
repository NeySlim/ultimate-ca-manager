import React, { useState } from 'react';
import styles from './SettingsV3.module.css';
import { Card } from '../../design-system/components/primitives/Card';
import { Button } from '../../design-system/components/primitives/Button';
import { Input } from '../../design-system/components/primitives/Input';
import { Select } from '../../design-system/components/primitives/Select';
import { Switch } from '../../design-system/components/primitives/Switch';
import { Tabs } from '../../design-system/components/navigation/Tabs';
import { Alert } from '../../design-system/components/feedback/Alert';
import { Badge } from '../../design-system/components/primitives/Badge';
import { Stack } from '../../design-system/components/layout/Stack';
import { Grid } from '../../design-system/components/layout/Grid';
import { 
  Certificate, 
  Key, 
  GlobeHemisphereWest, 
  Database, 
  ShieldCheck,
  Clock,
  HardDrives,
  DownloadSimple,
  UploadSimple,
  Warning,
  CheckCircle
} from '@phosphor-icons/react';

const SettingsV3 = () => {
  const [activeTab, setActiveTab] = useState('acme');
  const [acmeEnabled, setAcmeEnabled] = useState(true);
  const [scepEnabled, setScepEnabled] = useState(false);
  const [crlEnabled, setCrlEnabled] = useState(true);
  const [autoBackup, setAutoBackup] = useState(true);

  // ACME Settings
  const [acmeDirectory, setAcmeDirectory] = useState('/var/lib/ucm/acme');
  const [acmePort, setAcmePort] = useState('8080');
  const [acmeProvider, setAcmeProvider] = useState('letsencrypt');

  // SCEP Settings
  const [scepUrl, setScepUrl] = useState('');
  const [scepChallenge, setScepChallenge] = useState('');

  // CRL Settings
  const [crlInterval, setCrlInterval] = useState('86400');
  const [crlDistPoint, setCrlDistPoint] = useState('');

  // Backup Settings
  const [backupPath, setBackupPath] = useState('/var/backups/ucm');
  const [backupRetention, setBackupRetention] = useState('7');

  const tabs = [
    { id: 'acme', label: 'ACME', icon: <Certificate size={16} /> },
    { id: 'scep', label: 'SCEP', icon: <Key size={16} /> },
    { id: 'crl', label: 'CRL', icon: <GlobeHemisphereWest size={16} /> },
    { id: 'backup', label: 'Backup & Restore', icon: <Database size={16} /> },
  ];

  const handleSaveACME = () => {
    console.log('Saving ACME settings...', { acmeEnabled, acmeDirectory, acmePort, acmeProvider });
  };

  const handleSaveSCEP = () => {
    console.log('Saving SCEP settings...', { scepEnabled, scepUrl, scepChallenge });
  };

  const handleSaveCRL = () => {
    console.log('Saving CRL settings...', { crlEnabled, crlInterval, crlDistPoint });
  };

  const handleBackupNow = () => {
    console.log('Creating backup...');
  };

  const handleRestore = () => {
    console.log('Restoring from backup...');
  };

  const handleSaveBackupSettings = () => {
    console.log('Saving backup settings...', { autoBackup, backupPath, backupRetention });
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Settings</h1>
          <p className={styles.subtitle}>Configure UCM system settings and integrations</p>
        </div>
      </div>

      <Card className={styles.tabsCard}>
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
      </Card>

      {/* ACME Tab */}
      {activeTab === 'acme' && (
        <Stack spacing="lg">
          <Alert variant="info" icon={<Certificate size={20} />}>
            ACME (Automatic Certificate Management Environment) allows automated certificate issuance via Let's Encrypt and other ACME providers.
          </Alert>

          <Card>
            <Stack spacing="lg">
              <div className={styles.settingHeader}>
                <div>
                  <h3 className={styles.settingTitle}>ACME Server</h3>
                  <p className={styles.settingDescription}>Enable and configure the built-in ACME server</p>
                </div>
                <Switch checked={acmeEnabled} onChange={setAcmeEnabled} />
              </div>

              {acmeEnabled && (
                <div className={styles.settingsGrid}>
                  <Grid columns={2} gap="lg">
                    <div>
                      <label className={styles.label}>Directory URL</label>
                      <Input 
                        value={acmeDirectory} 
                        onChange={(e) => setAcmeDirectory(e.target.value)}
                        placeholder="/var/lib/ucm/acme"
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Port</label>
                      <Input 
                        type="number"
                        value={acmePort} 
                        onChange={(e) => setAcmePort(e.target.value)}
                        placeholder="8080"
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Provider</label>
                      <Select 
                        value={acmeProvider}
                        onChange={(e) => setAcmeProvider(e.target.value)}
                        options={[
                          { value: 'letsencrypt', label: "Let's Encrypt" },
                          { value: 'letsencrypt-staging', label: "Let's Encrypt (Staging)" },
                          { value: 'zerossl', label: 'ZeroSSL' },
                          { value: 'buypass', label: 'Buypass' },
                        ]}
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Status</label>
                      <div className={styles.statusBadge}>
                        <Badge variant="success" icon={<CheckCircle size={14} />}>Active</Badge>
                      </div>
                    </div>
                  </Grid>
                </div>
              )}

              <div className={styles.actions}>
                <Button variant="primary" onClick={handleSaveACME}>
                  Save Changes
                </Button>
                <Button variant="ghost">
                  Reset to Defaults
                </Button>
              </div>
            </Stack>
          </Card>
        </Stack>
      )}

      {/* SCEP Tab */}
      {activeTab === 'scep' && (
        <Stack spacing="lg">
          <Alert variant="info" icon={<Key size={20} />}>
            SCEP (Simple Certificate Enrollment Protocol) enables automatic certificate enrollment for network devices and IoT systems.
          </Alert>

          <Card>
            <Stack spacing="lg">
              <div className={styles.settingHeader}>
                <div>
                  <h3 className={styles.settingTitle}>SCEP Server</h3>
                  <p className={styles.settingDescription}>Enable and configure SCEP enrollment</p>
                </div>
                <Switch checked={scepEnabled} onChange={setScepEnabled} />
              </div>

              {scepEnabled && (
                <div className={styles.settingsGrid}>
                  <Stack spacing="md">
                    <div>
                      <label className={styles.label}>SCEP URL</label>
                      <Input 
                        value={scepUrl} 
                        onChange={(e) => setScepUrl(e.target.value)}
                        placeholder="https://ucm.example.com/scep"
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Challenge Password</label>
                      <Input 
                        type="password"
                        value={scepChallenge} 
                        onChange={(e) => setScepChallenge(e.target.value)}
                        placeholder="Enter challenge password"
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Status</label>
                      <div className={styles.statusBadge}>
                        <Badge variant="warning" icon={<Warning size={14} />}>Inactive</Badge>
                      </div>
                    </div>
                  </Stack>
                </div>
              )}

              <div className={styles.actions}>
                <Button variant="primary" onClick={handleSaveSCEP}>
                  Save Changes
                </Button>
                <Button variant="ghost">
                  Test Connection
                </Button>
              </div>
            </Stack>
          </Card>
        </Stack>
      )}

      {/* CRL Tab */}
      {activeTab === 'crl' && (
        <Stack spacing="lg">
          <Alert variant="info" icon={<GlobeHemisphereWest size={20} />}>
            CRL (Certificate Revocation List) manages revoked certificates and distribution points for OCSP/CRL clients.
          </Alert>

          <Card>
            <Stack spacing="lg">
              <div className={styles.settingHeader}>
                <div>
                  <h3 className={styles.settingTitle}>CRL Generation</h3>
                  <p className={styles.settingDescription}>Configure automatic CRL generation and distribution</p>
                </div>
                <Switch checked={crlEnabled} onChange={setCrlEnabled} />
              </div>

              {crlEnabled && (
                <div className={styles.settingsGrid}>
                  <Grid columns={2} gap="lg">
                    <div>
                      <label className={styles.label}>Update Interval (seconds)</label>
                      <Input 
                        type="number"
                        value={crlInterval} 
                        onChange={(e) => setCrlInterval(e.target.value)}
                        placeholder="86400"
                      />
                      <p className={styles.hint}>Default: 86400 (24 hours)</p>
                    </div>

                    <div>
                      <label className={styles.label}>Distribution Point URL</label>
                      <Input 
                        value={crlDistPoint} 
                        onChange={(e) => setCrlDistPoint(e.target.value)}
                        placeholder="http://crl.example.com/ca.crl"
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Last Update</label>
                      <div className={styles.infoText}>
                        <Clock size={16} /> 2 hours ago
                      </div>
                    </div>

                    <div>
                      <label className={styles.label}>Next Update</label>
                      <div className={styles.infoText}>
                        <Clock size={16} /> In 22 hours
                      </div>
                    </div>
                  </Grid>
                </div>
              )}

              <div className={styles.actions}>
                <Button variant="primary" onClick={handleSaveCRL}>
                  Save Changes
                </Button>
                <Button variant="secondary">
                  Generate CRL Now
                </Button>
              </div>
            </Stack>
          </Card>
        </Stack>
      )}

      {/* Backup Tab */}
      {activeTab === 'backup' && (
        <Stack spacing="lg">
          <Alert variant="warning" icon={<HardDrives size={20} />}>
            Regular backups are essential for disaster recovery. Configure automatic backups or create manual backups on demand.
          </Alert>

          {/* Automatic Backup */}
          <Card>
            <Stack spacing="lg">
              <div className={styles.settingHeader}>
                <div>
                  <h3 className={styles.settingTitle}>Automatic Backup</h3>
                  <p className={styles.settingDescription}>Schedule automatic backups of certificates and configuration</p>
                </div>
                <Switch checked={autoBackup} onChange={setAutoBackup} />
              </div>

              {autoBackup && (
                <div className={styles.settingsGrid}>
                  <Grid columns={2} gap="lg">
                    <div>
                      <label className={styles.label}>Backup Path</label>
                      <Input 
                        value={backupPath} 
                        onChange={(e) => setBackupPath(e.target.value)}
                        placeholder="/var/backups/ucm"
                      />
                    </div>

                    <div>
                      <label className={styles.label}>Retention (days)</label>
                      <Input 
                        type="number"
                        value={backupRetention} 
                        onChange={(e) => setBackupRetention(e.target.value)}
                        placeholder="7"
                      />
                    </div>
                  </Grid>
                </div>
              )}

              <div className={styles.actions}>
                <Button variant="primary" onClick={handleSaveBackupSettings}>
                  Save Changes
                </Button>
              </div>
            </Stack>
          </Card>

          {/* Manual Backup */}
          <Card>
            <Stack spacing="lg">
              <div>
                <h3 className={styles.settingTitle}>Manual Backup</h3>
                <p className={styles.settingDescription}>Create or restore backups manually</p>
              </div>

              <Grid columns={2} gap="lg">
                <div className={styles.backupCard}>
                  <div className={styles.backupIcon}>
                    <DownloadSimple size={32} weight="duotone" />
                  </div>
                  <h4 className={styles.backupTitle}>Create Backup</h4>
                  <p className={styles.backupDescription}>
                    Export all certificates, private keys, and configuration to a backup file
                  </p>
                  <Button variant="secondary" onClick={handleBackupNow} fullWidth>
                    <DownloadSimple size={16} /> Backup Now
                  </Button>
                </div>

                <div className={styles.backupCard}>
                  <div className={styles.backupIcon}>
                    <UploadSimple size={32} weight="duotone" />
                  </div>
                  <h4 className={styles.backupTitle}>Restore Backup</h4>
                  <p className={styles.backupDescription}>
                    Import certificates and configuration from a previous backup file
                  </p>
                  <Button variant="secondary" onClick={handleRestore} fullWidth>
                    <UploadSimple size={16} /> Choose File
                  </Button>
                </div>
              </Grid>

              <Alert variant="warning" icon={<ShieldCheck size={20} />}>
                <strong>Security Notice:</strong> Backup files contain sensitive private keys. Store them securely and encrypt if possible.
              </Alert>
            </Stack>
          </Card>
        </Stack>
      )}
    </div>
  );
};

export default SettingsV3;
