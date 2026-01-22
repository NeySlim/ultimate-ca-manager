import { useState } from 'react';
import toast from 'react-hot-toast';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { PageTopBar, SectionTabs, Tab } from '../../components/common';
import { useProfile, useSessions, useRevokeSession, useRevokeAllSessions } from '../../hooks/useAccount';
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
  
  const { data: profile, isLoading: loadingProfile, error: errorProfile } = useProfile();
  const { data: sessions, isLoading: loadingSessions, error: errorSessions } = useSessions();
  
  const { mutate: revokeSession } = useRevokeSession();
  const { mutate: revokeAllSessions } = useRevokeAllSessions();

  const isLoading = loadingProfile || loadingSessions;
  const error = errorProfile || errorSessions;

  const handleRevokeSession = (sessionId) => {
    revokeSession(sessionId, {
      onSuccess: () => toast.success('Session revoked successfully'),
      onError: (err) => toast.error(`Failed to revoke session: ${err.message}`),
    });
  };

  const handleRevokeAllSessions = () => {
    if (window.confirm('Are you sure you want to revoke all sessions? You will be logged out.')) {
      revokeAllSessions(undefined, {
        onSuccess: () => toast.success('All sessions revoked successfully'),
        onError: (err) => toast.error(`Failed to revoke sessions: ${err.message}`),
      });
    }
  };

  if (isLoading) {
    return (
      <div className={styles.profile}>
        <PageTopBar
          icon="ph ph-user-circle"
          title="My Profile"
        />
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading profile...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.profile}>
        <PageTopBar
          icon="ph ph-user-circle"
          title="My Profile"
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading profile: {error.message}
        </div>
      </div>
    );
  }

  const profileData = profile || {};
  const sessionsData = sessions?.data || [];

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
                <input type="text" defaultValue={profileData.username || 'admin'} readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Full Name</label>
                <input type="text" defaultValue={profileData.full_name || 'Administrator'} />
              </div>
              <div className={styles.formGroup}>
                <label>Email Address</label>
                <input type="email" defaultValue={profileData.email || 'admin@ucm.local'} />
              </div>
              <div className={styles.formGroup}>
                <label>Role</label>
                <input type="text" defaultValue={profileData.role || 'Administrator'} readOnly />
              </div>
              <div className={styles.formGroup}>
                <label>Department</label>
                <input type="text" defaultValue={profileData.department || 'IT Operations'} />
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
              <div className={styles.sectionTitle}>Active Sessions</div>
              <div className={styles.certList}>
                {sessionsData.map((session) => (
                  <div key={session.id} className={styles.certItem}>
                    <div className={styles.certInfo}>
                      <div className={styles.certSubject}>
                        {session.current ? 'Current Session (This Device)' : session.device || 'Unknown Device'}
                      </div>
                      <div className={styles.certMeta}>
                        {session.user_agent || 'Unknown browser'} • IP: {session.ip_address || 'N/A'} • Started {session.created_at || 'N/A'}
                      </div>
                    </div>
                    <div className={styles.certActions}>
                      {session.current ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Button 
                          variant="default" 
                          size="sm" 
                          icon="ph ph-x"
                          onClick={() => handleRevokeSession(session.id)}
                        >
                          Revoke
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className={styles.formGroup}>
                <Button 
                  variant="danger" 
                  icon="ph ph-x-circle"
                  onClick={handleRevokeAllSessions}
                >
                  Revoke All Sessions
                </Button>
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
