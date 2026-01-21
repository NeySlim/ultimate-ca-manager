import { Tabs } from '../../components/ui/Tabs';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/domain/DataTable';
import { ActivityFeed } from '../../components/domain/ActivityFeed';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getProfileData } from '../../services/mockData';
import styles from './Profile.module.css';

/**
 * Profile Page
 * 
 * Four tabs:
 * - Account (user information)
 * - Security (password, MFA, sessions)
 * - Activity (user activity log)
 * - Preferences (UI preferences)
 */
export function Profile() {
  const profile = getProfileData();

  const sessionColumns = [
    {
      key: 'browser',
      label: 'Browser',
      sortable: true,
    },
    {
      key: 'os',
      label: 'Operating System',
      sortable: true,
    },
    {
      key: 'ip',
      label: 'IP Address',
      sortable: true,
    },
    {
      key: 'loginAt',
      label: 'Login At',
      sortable: true,
    },
    {
      key: 'current',
      label: 'Status',
      render: (row) => (
        row.current ? (
          <Badge variant="success">Current</Badge>
        ) : (
          <Button variant="danger" icon="ph ph-x" onClick={() => console.log('Revoke:', row)}>
            Revoke
          </Button>
        )
      ),
    },
  ];

  return (
    <div className={styles.profile}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>Account</Tabs.Tab>
          <Tabs.Tab>Security</Tabs.Tab>
          <Tabs.Tab>Activity</Tabs.Tab>
          <Tabs.Tab>Preferences</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* Account Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Account Information</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="Username" value={profile.user.username} readOnly />
                    <Input label="Email" value={profile.user.email} />
                    <Input label="First Name" value={profile.user.firstName} />
                    <Input label="Last Name" value={profile.user.lastName} />
                    <Input label="Role" value={profile.user.role} readOnly />
                    <Input label="Timezone" value={profile.user.timezone} />
                    <Input label="Language" value={profile.user.language} />
                    
                    <div className={styles.metadata}>
                      <div className={styles.metadataItem}>
                        <span className={styles.metadataLabel}>Account Created</span>
                        <span className={styles.metadataValue}>{profile.user.createdAt}</span>
                      </div>
                      <div className={styles.metadataItem}>
                        <span className={styles.metadataLabel}>Last Login</span>
                        <span className={styles.metadataValue}>{profile.user.lastLogin}</span>
                      </div>
                    </div>
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-floppy-disk">Save Changes</Button>
                      <Button variant="default">Cancel</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Security Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              {/* Change Password */}
              <Card>
                <Card.Header>
                  <h3>Change Password</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="Current Password" type="password" placeholder="Enter current password" />
                    <Input label="New Password" type="password" placeholder="Enter new password" />
                    <Input label="Confirm Password" type="password" placeholder="Confirm new password" />
                    
                    <div className={styles.metadata}>
                      <div className={styles.metadataItem}>
                        <span className={styles.metadataLabel}>Password Last Changed</span>
                        <span className={styles.metadataValue}>{profile.security.passwordLastChanged}</span>
                      </div>
                    </div>
                    
                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-lock-key">Change Password</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>

              {/* Two-Factor Authentication */}
              <Card>
                <Card.Header>
                  <h3>Two-Factor Authentication</h3>
                  <Badge variant={profile.security.mfaEnabled ? 'success' : 'secondary'}>
                    {profile.security.mfaEnabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </Card.Header>
                <Card.Body>
                  <div className={styles.infoBox}>
                    <div className={styles.infoIcon}>
                      <i className="ph ph-shield-check" />
                    </div>
                    <div>
                      <div className={styles.infoTitle}>Enhance Your Security</div>
                      <div className={styles.infoText}>
                        Two-factor authentication adds an extra layer of security to your account.
                      </div>
                    </div>
                  </div>
                  <div className={styles.formActions}>
                    {profile.security.mfaEnabled ? (
                      <Button variant="danger" icon="ph ph-x">Disable 2FA</Button>
                    ) : (
                      <Button variant="success" icon="ph ph-shield-check">Enable 2FA</Button>
                    )}
                  </div>
                </Card.Body>
              </Card>

              {/* Active Sessions */}
              <Card>
                <Card.Header>
                  <h3>Active Sessions</h3>
                </Card.Header>
                <Card.Body>
                  <DataTable
                    columns={sessionColumns}
                    data={profile.security.sessions}
                  />
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Activity Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Recent Activity</h3>
                </Card.Header>
                <Card.Body>
                  <ActivityFeed items={profile.activity.map(item => ({
                    icon: 'clock',
                    text: `${item.action}: ${item.details}`,
                    time: item.timestamp,
                    variant: 'info',
                  }))} />
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Preferences Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>UI Preferences</h3>
                </Card.Header>
                <Card.Body>
                  <div className={styles.infoBox}>
                    <div className={styles.infoIcon}>
                      <i className="ph ph-palette" />
                    </div>
                    <div>
                      <div className={styles.infoTitle}>Theme Settings</div>
                      <div className={styles.infoText}>
                        Use the theme picker in the top right to change your color scheme and accent color.
                        Your preferences are saved automatically.
                      </div>
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default Profile;
