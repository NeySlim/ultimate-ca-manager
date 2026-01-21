import { Tabs } from '../../components/ui/Tabs';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { getSystemSettings } from '../../services/mockData';
import styles from './Settings.module.css';

/**
 * Settings Page
 * 
 * Four tabs:
 * - General (system settings)
 * - Email (SMTP configuration)
 * - Security (password policy, MFA)
 * - Backup (automated backup configuration)
 */
export function Settings() {
  const settings = getSystemSettings();

  return (
    <div className={styles.settings}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>General</Tabs.Tab>
          <Tabs.Tab>Email</Tabs.Tab>
          <Tabs.Tab>Security</Tabs.Tab>
          <Tabs.Tab>Backup</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* General Settings Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>General Settings</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="System Name" value={settings.general.systemName} />
                    <Input label="Timezone" value={settings.general.timezone} />
                    <Input label="Language" value={settings.general.language} />
                    <Input label="Session Timeout (seconds)" value={settings.general.sessionTimeout} />
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-floppy-disk">Save Changes</Button>
                      <Button variant="default">Reset</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Email Settings Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Email Configuration</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="SMTP Host" value={settings.email.smtpHost} />
                    <Input label="SMTP Port" value={settings.email.smtpPort} />
                    <Input label="SMTP Username" value={settings.email.smtpUsername} />
                    <Input label="SMTP Security" value={settings.email.smtpSecurity} />
                    <Input label="From Address" value={settings.email.fromAddress} />
                    <Input label="From Name" value={settings.email.fromName} />
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-floppy-disk">Save Changes</Button>
                      <Button variant="default" icon="ph ph-envelope">Send Test Email</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Security Settings Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Security Settings</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="Minimum Password Length" value={settings.security.passwordMinLength} />
                    <Input label="Session Expiration (seconds)" value={settings.security.sessionExpiration} />
                    <Input label="Max Login Attempts" value={settings.security.maxLoginAttempts} />
                    <Input label="MFA Requirement" value={settings.security.mfa} />
                    
                    <div className={styles.checkboxGroup}>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={settings.security.passwordRequireUppercase} readOnly />
                        <span>Require Uppercase Letters</span>
                      </label>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={settings.security.passwordRequireLowercase} readOnly />
                        <span>Require Lowercase Letters</span>
                      </label>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={settings.security.passwordRequireNumbers} readOnly />
                        <span>Require Numbers</span>
                      </label>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={settings.security.passwordRequireSpecial} readOnly />
                        <span>Require Special Characters</span>
                      </label>
                    </div>
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-floppy-disk">Save Changes</Button>
                      <Button variant="default">Reset</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Backup Settings Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Backup Configuration</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <div className={styles.checkboxGroup}>
                      <label className={styles.checkbox}>
                        <input type="checkbox" checked={settings.backup.enabled} readOnly />
                        <span>Enable Automated Backups</span>
                      </label>
                    </div>

                    <Input label="Schedule" value={settings.backup.schedule} />
                    <Input label="Backup Time" value={settings.backup.time} />
                    <Input label="Retention (days)" value={settings.backup.retention} />
                    <Input label="Last Backup" value={settings.backup.lastBackup} readOnly />
                    <Input label="Backup Size" value={settings.backup.backupSize} readOnly />
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-floppy-disk">Save Changes</Button>
                      <Button variant="success" icon="ph ph-database">Backup Now</Button>
                      <Button variant="default" icon="ph ph-download-simple">Download Latest</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default Settings;
