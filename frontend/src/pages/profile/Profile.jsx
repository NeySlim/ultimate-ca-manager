import { useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { PageTopBar, SectionTabs, Tab } from '../../components/common';
import styles from './Profile.module.css';

/**
 * Profile Page
 * 
 * Reference: prototype-profile.html
 * - TopBar with title + save/discard buttons
 * - 4 tabs: Profile, Security, Notifications, Preferences
 * - Form sections with avatar, personal info, password, client certs
 */
export function Profile() {
  const [activeTab, setActiveTab] = useState('profile');

  return (
    <div className={styles.profile}>
      <PageTopBar
        icon="ph ph-user-circle"
        title="My Profile"
        actions={
          <>
            <Button variant="default" icon="ph ph-arrow-counter-clockwise">Discard Changes</Button>
            <Button variant="primary" icon="ph ph-floppy-disk">Save Changes</Button>
          </>
        }
      />

      <SectionTabs>
        <Tab active={activeTab === 'profile'} onClick={() => setActiveTab('profile')}>
          Profile
        </Tab>
        <Tab active={activeTab === 'security'} onClick={() => setActiveTab('security')}>
          Security
        </Tab>
        <Tab active={activeTab === 'notifications'} onClick={() => setActiveTab('notifications')}>
          Notifications
        </Tab>
        <Tab active={activeTab === 'preferences'} onClick={() => setActiveTab('preferences')}>
          Preferences
        </Tab>
      </SectionTabs>

      <div className={styles.tabContent}>
        {activeTab === 'profile' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Account Information</div>
              
              <div className={styles.avatarSection}>
                <div className={styles.avatarLarge}>A</div>
                <div className={styles.avatarActions}>
                  <Button variant="default" icon="ph ph-upload">Upload Photo</Button>
                  <Button variant="default" icon="ph ph-trash">Remove Photo</Button>
                </div>
              </div>

              <div className={styles.formGroup}>
                <label>Username</label>
                <input type="text" defaultValue="admin" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Full Name</label>
                <input type="text" defaultValue="Administrator" />
              </div>
              <div className={styles.formGroup}>
                <label>Email Address</label>
                <input type="email" defaultValue="admin@ucm.local" />
              </div>
              <div className={styles.formGroup}>
                <label>Role</label>
                <input type="text" defaultValue="Administrator" readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Department</label>
                <input type="text" defaultValue="IT Operations" />
              </div>
              <div className={styles.formGroup}>
                <label>Phone Number</label>
                <input type="tel" defaultValue="+1 555-0123" />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Bio</div>
              <div className={styles.formGroup}>
                <label>About Me</label>
                <textarea placeholder="Tell us about yourself..." defaultValue="Senior system administrator managing certificate infrastructure." />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'security' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Password</div>
              <div className={styles.formGroup}>
                <label>Current Password</label>
                <input type="password" placeholder="Enter current password" />
              </div>
              <div className={styles.formGroup}>
                <label>New Password</label>
                <input type="password" placeholder="Enter new password" />
              </div>
              <div className={styles.formGroup}>
                <label>Confirm Password</label>
                <input type="password" placeholder="Confirm new password" />
              </div>
              <div className={styles.formGroup}>
                <Button variant="primary" icon="ph ph-lock">Change Password</Button>
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Two-Factor Authentication</div>
              <div className={styles.formGroup}>
                <label>Status</label>
                <Badge variant="error">Disabled</Badge>
              </div>
              <div className={styles.formGroup}>
                <Button variant="primary" icon="ph ph-shield-check">Enable 2FA</Button>
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Client Certificates</div>
              <div className={styles.certList}>
                <div className={styles.certItem}>
                  <div className={styles.certInfo}>
                    <div className={styles.certSubject}>CN=admin@ucm.local</div>
                    <div className={styles.certMeta}>Valid until: 2025-12-31 • Serial: AB:CD:EF:12:34</div>
                  </div>
                  <div className={styles.certActions}>
                    <Button variant="default" size="sm" icon="ph ph-eye">View</Button>
                    <Button variant="default" size="sm" icon="ph ph-download-simple">Download</Button>
                    <Button variant="default" size="sm" icon="ph ph-trash">Revoke</Button>
                  </div>
                </div>
              </div>
              <div className={styles.formGroup}>
                <Button variant="primary" icon="ph ph-plus">Generate New Certificate</Button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'notifications' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Email Notifications</div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" defaultChecked />
                  <span>Certificate Expiration Warnings</span>
                </label>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" defaultChecked />
                  <span>Security Alerts</span>
                </label>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" />
                  <span>System Maintenance Notifications</span>
                </label>
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>In-App Notifications</div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" defaultChecked />
                  <span>Show Desktop Notifications</span>
                </label>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" defaultChecked />
                  <span>Play Sound on Critical Alerts</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'preferences' && (
          <div className={styles.tabPanel}>
            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Display</div>
              <div className={styles.formGroup}>
                <label>Theme</label>
                <select>
                  <option>Dark</option>
                  <option>Light</option>
                  <option>Auto</option>
                </select>
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
                <label>Date Format</label>
                <select>
                  <option>YYYY-MM-DD</option>
                  <option>DD/MM/YYYY</option>
                  <option>MM/DD/YYYY</option>
                </select>
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.sectionTitle}>Accessibility</div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" />
                  <span>Reduce Animations</span>
                </label>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.checkbox}>
                  <input type="checkbox" />
                  <span>High Contrast Mode</span>
                </label>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Profile;
