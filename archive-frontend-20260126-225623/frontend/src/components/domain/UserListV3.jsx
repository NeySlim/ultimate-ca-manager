import { useState } from 'react';
import {
  Users,
  Plus,
  MagnifyingGlass,
  UserPlus,
  Trash,
  ShieldCheck,
  ShieldWarning,
  User,
  Envelope,
  Calendar,
  DotsThree,
  Eye,
  Key,
  Clock
} from '@phosphor-icons/react';

// Design System V3
import { Table } from '../../design-system/components/primitives/Table';
import { Button } from '../../design-system/components/primitives/Button';
import { Input } from '../../design-system/components/primitives/Input';
import { Select } from '../../design-system/components/primitives/Select';
import { Badge } from '../../design-system/components/primitives/Badge';
import { GradientBadge } from '../../design-system/components/primitives/GradientBadge';
import { GlassCard } from '../../design-system/components/primitives/GlassCard';
import { Card } from '../../design-system/components/primitives/Card';
import { Stack } from '../../design-system/components/layout/Stack';
import { Inline } from '../../design-system/components/layout/Inline';
import { Grid } from '../../design-system/components/layout/Grid';
import { Modal } from '../../design-system/components/overlays/Modal';
import { Dropdown } from '../../design-system/components/overlays/Dropdown';
import { Alert } from '../../design-system/components/feedback/Alert';
import { EmptyState } from '../../design-system/components/feedback/EmptyState';

import { useUsers } from '../../hooks/useUsers';
import styles from './UserListV3.module.css';

// Invite User Modal
function InviteUserModal({ isOpen, onClose, onInvite }) {
  const [formData, setFormData] = useState({
    email: '',
    firstName: '',
    lastName: '',
    role: 'viewer',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onInvite?.(formData);
    setFormData({ email: '', firstName: '', lastName: '', role: 'viewer' });
  };

  const roles = [
    { value: 'admin', label: 'Administrator', description: 'Full system access', icon: <ShieldCheck size={20} />, color: 'danger' },
    { value: 'operator', label: 'Operator', description: 'Can manage CAs and certificates', icon: <ShieldWarning size={20} />, color: 'warning' },
    { value: 'viewer', label: 'Viewer', description: 'Read-only access', icon: <Eye size={20} />, color: 'info' },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="md"
      title="Invite User"
    >
      <form onSubmit={handleSubmit}>
        <Stack gap="lg">
          <Alert variant="info">
            An invitation email will be sent to the user with instructions to set up their account.
          </Alert>

          <Stack gap="md">
            <Input
              label="Email Address"
              type="email"
              placeholder="user@example.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
              leftIcon={<Envelope size={18} />}
            />

            <Grid cols={2} gap="md">
              <Input
                label="First Name"
                placeholder="John"
                value={formData.firstName}
                onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                required
              />
              <Input
                label="Last Name"
                placeholder="Doe"
                value={formData.lastName}
                onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                required
              />
            </Grid>

            <div>
              <label className={styles.label}>Role</label>
              <Stack gap="sm">
                {roles.map((role) => (
                  <Card
                    key={role.value}
                    hoverable
                    className={styles.roleCard}
                    data-selected={formData.role === role.value}
                    onClick={() => setFormData({ ...formData, role: role.value })}
                  >
                    <Inline gap="md" align="center">
                      <div className={styles.roleIcon} data-color={role.color}>
                        {role.icon}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div className={styles.roleLabel}>{role.label}</div>
                        <div className={styles.roleDescription}>{role.description}</div>
                      </div>
                      <div className={styles.roleRadio}>
                        <input
                          type="radio"
                          name="role"
                          value={role.value}
                          checked={formData.role === role.value}
                          onChange={() => setFormData({ ...formData, role: role.value })}
                        />
                      </div>
                    </Inline>
                  </Card>
                ))}
              </Stack>
            </div>
          </Stack>

          <Inline gap="sm" justify="end">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" leftIcon={<UserPlus size={18} />}>
              Send Invitation
            </Button>
          </Inline>
        </Stack>
      </form>
    </Modal>
  );
}

// User Activity Timeline
function UserActivityTimeline({ activities = [] }) {
  const getActivityIcon = (type) => {
    switch (type) {
      case 'certificate_issued': return <ShieldCheck size={16} weight="fill" />;
      case 'certificate_revoked': return <ShieldWarning size={16} weight="fill" />;
      case 'login': return <User size={16} weight="fill" />;
      case 'settings_changed': return <Key size={16} weight="fill" />;
      default: return <Clock size={16} weight="fill" />;
    }
  };

  const getActivityColor = (type) => {
    switch (type) {
      case 'certificate_issued': return 'success';
      case 'certificate_revoked': return 'warning';
      case 'login': return 'info';
      case 'settings_changed': return 'primary';
      default: return 'default';
    }
  };

  if (!activities || activities.length === 0) {
    return (
      <EmptyState
        icon={<Clock size={48} />}
        title="No recent activity"
        description="User activity will appear here"
      />
    );
  }

  return (
    <div className={styles.timeline}>
      {activities.map((activity, idx) => (
        <div key={idx} className={styles.timelineItem}>
          <div className={styles.timelineDot}>
            <GradientBadge variant={getActivityColor(activity.type)} size="sm">
              {getActivityIcon(activity.type)}
            </GradientBadge>
          </div>
          <div className={styles.timelineContent}>
            <div className={styles.timelineMessage}>{activity.message}</div>
            <div className={styles.timelineMeta}>
              <Clock size={12} />
              <span>{activity.timestamp}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// User Details Modal
function UserDetailsModal({ user, isOpen, onClose }) {
  if (!user) return null;

  const tabs = ['Overview', 'Activity', 'Permissions'];
  const [activeTab, setActiveTab] = useState('Overview');

  const roleColors = {
    admin: 'danger',
    operator: 'warning',
    viewer: 'info',
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title={`${user.first_name} ${user.last_name}`}
    >
      <Stack gap="lg">
        {/* User Header */}
        <Card>
          <Inline gap="md" align="center">
            <div className={styles.userAvatar}>
              <User size={32} weight="bold" />
            </div>
            <div style={{ flex: 1 }}>
              <div className={styles.userName}>{user.first_name} {user.last_name}</div>
              <div className={styles.userEmail}>{user.email}</div>
            </div>
            <GradientBadge variant={roleColors[user.role]} size="md">
              {user.role}
            </GradientBadge>
          </Inline>
        </Card>

        {/* Tabs */}
        <div className={styles.tabs}>
          {tabs.map((tab) => (
            <button
              key={tab}
              className={styles.tab}
              data-active={activeTab === tab}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'Overview' && (
          <Stack gap="md">
            <Grid cols={2} gap="md">
              <div className={styles.infoItem}>
                <div className={styles.infoLabel}>Status</div>
                <Badge variant={user.status === 'active' ? 'success' : 'danger'}>
                  {user.status}
                </Badge>
              </div>
              <div className={styles.infoItem}>
                <div className={styles.infoLabel}>Created</div>
                <div className={styles.infoValue}>{user.created_at}</div>
              </div>
              <div className={styles.infoItem}>
                <div className={styles.infoLabel}>Last Login</div>
                <div className={styles.infoValue}>{user.last_login || 'Never'}</div>
              </div>
              <div className={styles.infoItem}>
                <div className={styles.infoLabel}>Certificates Issued</div>
                <div className={styles.infoValue}>{user.certificates_issued || 0}</div>
              </div>
            </Grid>
          </Stack>
        )}

        {activeTab === 'Activity' && (
          <UserActivityTimeline activities={user.activities} />
        )}

        {activeTab === 'Permissions' && (
          <Stack gap="sm">
            {user.permissions?.map((perm, idx) => (
              <Card key={idx}>
                <Inline gap="sm" align="center">
                  <ShieldCheck size={20} weight="duotone" />
                  <div>
                    <div className={styles.permName}>{perm.name}</div>
                    <div className={styles.permDesc}>{perm.description}</div>
                  </div>
                </Inline>
              </Card>
            )) || <p style={{ color: 'var(--color-text-secondary)' }}>No specific permissions</p>}
          </Stack>
        )}

        <Inline gap="sm" justify="end">
          <Button variant="secondary" leftIcon={<Key size={18} />}>
            Reset Password
          </Button>
          <Button variant="danger" leftIcon={<Trash size={18} />}>
            Remove User
          </Button>
        </Inline>
      </Stack>
    </Modal>
  );
}

export function UserListV3() {
  const { data: users, isLoading } = useUsers();

  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const handleInvite = (formData) => {
    console.log('Invite user:', formData);
    setInviteModalOpen(false);
    // TODO: API call
  };

  const getRoleIcon = (role) => {
    switch (role) {
      case 'admin': return <ShieldCheck size={16} weight="fill" />;
      case 'operator': return <ShieldWarning size={16} weight="fill" />;
      case 'viewer': return <Eye size={16} weight="fill" />;
      default: return <User size={16} />;
    }
  };

  const getRoleVariant = (role) => {
    switch (role) {
      case 'admin': return 'danger';
      case 'operator': return 'warning';
      case 'viewer': return 'info';
      default: return 'default';
    }
  };

  const filteredUsers = users?.filter(user => {
    if (searchQuery && !`${user.first_name} ${user.last_name} ${user.email}`.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    if (roleFilter !== 'all' && user.role !== roleFilter) {
      return false;
    }
    if (statusFilter !== 'all' && user.status !== statusFilter) {
      return false;
    }
    return true;
  });

  const columns = [
    {
      key: 'name',
      label: 'User',
      sortable: true,
      width: '25%',
      render: (user) => (
        <Inline gap="sm" align="center">
          <div className={styles.userAvatarSmall}>
            <User size={20} weight="bold" />
          </div>
          <div>
            <div className={styles.tableUserName}>{user.first_name} {user.last_name}</div>
            <div className={styles.tableUserEmail}>{user.email}</div>
          </div>
        </Inline>
      ),
    },
    {
      key: 'role',
      label: 'Role',
      sortable: true,
      width: '15%',
      render: (user) => (
        <GradientBadge variant={getRoleVariant(user.role)} size="sm">
          <Inline gap="xs" align="center">
            {getRoleIcon(user.role)}
            <span>{user.role}</span>
          </Inline>
        </GradientBadge>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      width: '12%',
      render: (user) => (
        <Badge variant={user.status === 'active' ? 'success' : 'danger'}>
          {user.status}
        </Badge>
      ),
    },
    {
      key: 'last_login',
      label: 'Last Login',
      sortable: true,
      width: '18%',
      render: (user) => (
        <div className={styles.lastLogin}>{user.last_login || 'Never'}</div>
      ),
    },
    {
      key: 'created_at',
      label: 'Created',
      sortable: true,
      width: '15%',
      render: (user) => (
        <div className={styles.created}>{user.created_at}</div>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: '10%',
      render: (user) => (
        <Dropdown
          items={[
            { label: 'View Details', icon: <Eye size={16} />, onClick: () => { setSelectedUser(user); setDetailsOpen(true); } },
            { label: 'Reset Password', icon: <Key size={16} />, onClick: () => {} },
            { type: 'divider' },
            { label: 'Remove', icon: <Trash size={16} />, onClick: () => {}, variant: 'danger' },
          ]}
        >
          <Button variant="ghost" size="sm">
            <DotsThree size={20} weight="bold" />
          </Button>
        </Dropdown>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <Stack gap="xl">
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Users</h1>
            <p className={styles.subtitle}>{filteredUsers?.length || 0} user{filteredUsers?.length !== 1 ? 's' : ''}</p>
          </div>
          <Button 
            variant="primary" 
            leftIcon={<UserPlus size={20} weight="bold" />}
            onClick={() => setInviteModalOpen(true)}
          >
            Invite User
          </Button>
        </div>

        {/* Filters */}
        <GlassCard blur="md">
          <Inline gap="sm">
            <Input
              placeholder="Search users..."
              leftIcon={<MagnifyingGlass size={18} />}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: '300px' }}
            />
            <Select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              style={{ width: '150px' }}
            >
              <option value="all">All Roles</option>
              <option value="admin">Admin</option>
              <option value="operator">Operator</option>
              <option value="viewer">Viewer</option>
            </Select>
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ width: '150px' }}
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </Inline>
        </GlassCard>

        {/* Table */}
        <Table
          columns={columns}
          data={filteredUsers || []}
          isLoading={isLoading}
          selectable={true}
          striped={true}
          hoverable={true}
          onRowClick={(user) => { setSelectedUser(user); setDetailsOpen(true); }}
          emptyMessage="No users found"
          emptyIcon={<Users size={64} />}
        />
      </Stack>

      {/* Modals */}
      <InviteUserModal
        isOpen={inviteModalOpen}
        onClose={() => setInviteModalOpen(false)}
        onInvite={handleInvite}
      />

      <UserDetailsModal
        user={selectedUser}
        isOpen={detailsOpen}
        onClose={() => setDetailsOpen(false)}
      />
    </div>
  );
}

export default UserListV3;
