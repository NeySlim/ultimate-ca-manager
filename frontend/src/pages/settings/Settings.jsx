import { useState } from 'react';
import toast from 'react-hot-toast';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { PageTopBar, SectionTabs, Tab } from '../../components/common';
import { useGeneralSettings, useUpdateGeneralSettings } from '../../hooks/useSettings';
import styles from './Settings.module.css';

/**
 * Settings Page
 * 
 * Reference: prototype-settings.html
 * - TopBar with title badge + save button
 * - 4 tabs: System, Database, Security, Backup
 * - Form sections with labels, inputs, selects, checkboxes
 */
export function Settings() {
  const [activeTab, setActiveTab] = useState('system');
  const [formData, setFormData] = useState({});
  
  const { data: settings, isLoading } = useGeneralSettings();
  const { mutate: updateSettings } = useUpdateGeneralSettings();
  
  const generalSettings = settings || {};
  
  const handleSave = () => {
    updateSettings(formData, {
      onSuccess: () => toast.success('Settings saved successfully'),
      onError: (err) => toast.error(`Failed to save settings: ${err.message}`),
    });
  };

  const handleReset = () => {
    if (window.confirm('Are you sure you want to reset all settings to default?')) {
      setFormData({});
      toast.success('Settings reset to default');
    }
  };
  
  if (isLoading) {
    return (
      <div className={styles.settings}>
        <PageTopBar
          icon="ph ph-gear"
          title="Settings"
          badge={<Badge variant="secondary">Loading...</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-tertiary)' }}>
          Loading settings...
        </div>
      </div>
    );
  }

  return (
    <div className={styles.settings}>
      <PageTopBar
        icon="ph ph-gear"
        title="Settings"
        badge={<Badge variant="warning">Requires Restart</Badge>}
        actions={
          <>
            <Button variant="default" onClick={handleReset}>Reset All</Button>
            <Button variant="primary" icon="ph ph-floppy-disk" onClick={handleSave}>Save Changes</Button>
          </>
        }
      />

      <SectionTabs>
        <Tab active={activeTab === 'system'} onClick={() => setActiveTab('system')}>
          System
        </Tab>
        <Tab active={activeTab === 'database'} onClick={() => setActiveTab('database')}>
          Database
        </Tab>
        <Tab active={activeTab === 'security'} onClick={() => setActiveTab('security')}>
          Security
        </Tab>
        <Tab active={activeTab === 'backup'} onClick={() => setActiveTab('backup')}>
          Backup
        </Tab>
      </SectionTabs>

      <div className={styles.tabContent}>
        {activeTab === 'system' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>General</div>
              <div className={styles.formGroup}>
                <label>Application Name</label>
                <input type="text" defaultValue="UCM - Certificate Manager" />
              </div>
              <div className={styles.formGroup}>
                <label>Application URL</label>
                <input type="text" defaultValue="https://netsuit.lan.pew.pet:8443" />
              </div>
              <div className={styles.formGroup}>
                <label>Timezone</label>
                <select>
                  <option>UTC</option>
                  <option>Europe/Paris</option>
                  <option>America/New_York</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Language</label>
                <select>
                  <option>English</option>
                  <option>Français</option>
                </select>
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Session</div>
              <div className={styles.formGroup}>
                <label>Session Timeout</label>
                <div className={styles.inputWithUnit}>
                  <input type="number" defaultValue="30" />
                  <span>minutes</span>
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Max Concurrent Sessions</label>
                <input type="number" defaultValue="5" />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Logging</div>
              <div className={styles.formGroup}>
                <label>Log Level</label>
                <select>
                  <option>Debug</option>
                  <option>Info</option>
                  <option>Warning</option>
                  <option>Error</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Log Retention</label>
                <div className={styles.inputWithUnit}>
                  <input type="number" defaultValue="90" />
                  <span>days</span>
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Enable Audit Log</label>
                <input type="checkbox" defaultChecked />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'database' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Database Configuration</div>
              <div className={styles.formGroup}>
                <label>Database Type</label>
                <input type="text" defaultValue="SQLite" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Database Path</label>
                <input type="text" defaultValue="/var/lib/ucm/ucm.db" readOnly />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Database Maintenance</div>
              <div className={styles.formGroup}>
                <label>Database Size</label>
                <input type="text" defaultValue="142.5 MB" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Fragmentation</label>
                <input type="text" defaultValue="3.2%" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Last Optimization</label>
                <input type="text" defaultValue="2024-03-15 02:00 UTC" readOnly />
              </div>
              <div className={styles.formGroup}>
                <Button variant="primary" icon="ph ph-broom">Optimize Database</Button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'security' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Password Policy</div>
              <div className={styles.formGroup}>
                <label>Minimum Length</label>
                <input type="number" defaultValue="12" />
              </div>
              <div className={styles.formGroup}>
                <label>Require Uppercase</label>
                <input type="checkbox" defaultChecked />
              </div>
              <div className={styles.formGroup}>
                <label>Require Numbers</label>
                <input type="checkbox" defaultChecked />
              </div>
              <div className={styles.formGroup}>
                <label>Password Expiration</label>
                <div className={styles.inputWithUnit}>
                  <input type="number" defaultValue="90" />
                  <span>days</span>
                </div>
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Authentication</div>
              <div className={styles.formGroup}>
                <label>Max Failed Login Attempts</label>
                <input type="number" defaultValue="5" />
              </div>
              <div className={styles.formGroup}>
                <label>Account Lockout Duration</label>
                <div className={styles.inputWithUnit}>
                  <input type="number" defaultValue="30" />
                  <span>minutes</span>
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Two-Factor Authentication</label>
                <input type="checkbox" />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>HTTPS Certificate</div>
              <div className={styles.formGroup}>
                <label>Current Certificate</label>
                <input type="text" defaultValue="CN=ucm.local" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Valid Until</label>
                <input type="text" defaultValue="2025-03-15" readOnly />
              </div>
              <div className={styles.formGroup}>
                <Button variant="primary" icon="ph ph-arrows-clockwise">Regenerate Self-Signed</Button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'backup' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Automated Backup</div>
              <div className={styles.formGroup}>
                <label>Enable Automated Backup</label>
                <input type="checkbox" defaultChecked />
              </div>
              <div className={styles.formGroup}>
                <label>Backup Schedule</label>
                <select>
                  <option>Daily at 03:00</option>
                  <option>Weekly on Sunday</option>
                  <option>Monthly on 1st</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>Backup Retention</label>
                <div className={styles.inputWithUnit}>
                  <input type="number" defaultValue="30" />
                  <span>days</span>
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Backup Location</label>
                <input type="text" defaultValue="/var/backups/ucm/" />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Manual Backup</div>
              <div className={styles.formGroup}>
                <label>Last Backup</label>
                <input type="text" defaultValue="2024-03-15 03:00 UTC" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Backup Size</label>
                <input type="text" defaultValue="245.3 MB" readOnly />
              </div>
              <div className={styles.formGroup}>
                <Button variant="primary" icon="ph ph-download-simple">Create Backup Now</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Settings;
