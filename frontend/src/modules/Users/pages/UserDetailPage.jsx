import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Group,
  Text,
  Badge,
  Stack,
  Tabs,
  ActionIcon,
  Tooltip,
  Avatar,
  Switch,
} from '../../../components/ui';
import {
  User,
  EnvelopeSimple,
  Shield,
  Key,
  Clock,
  ListDashes,
  Trash,
  PencilSimple,
  CheckCircle,
  XCircle,
  DeviceMobile,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './UserDetailPage.css';

// Mock Data
const MOCK_USER = {
  id: 1,
  username: 'admin',
  email: 'admin@internal.corp',
  role: 'Administrator',
  status: 'Active',
  mfaEnabled: true,
  lastLogin: '2024-03-20T10:30:00Z',
  created: '2023-01-01T00:00:00Z',
};

const MOCK_ACTIVITY = [
  { id: 1, action: 'Login Success', ip: '192.168.1.50', time: '2024-03-20T10:30:00Z', status: 'Success' },
  { id: 2, action: 'Issue Certificate', target: 'web.internal.corp', time: '2024-03-20T10:35:00Z', status: 'Success' },
  { id: 3, action: 'Revoke Certificate', target: 'old.internal.corp', time: '2024-03-19T14:20:00Z', status: 'Success' },
];

const UserDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('activity');
  const user = MOCK_USER; // Mock

  const columns = [
    {
      key: 'action',
      label: 'Action',
      width: 200,
      render: (row) => <Text size="sm" fw={500}>{row.action}</Text>
    },
    {
      key: 'target',
      label: 'Target / Details',
      width: 200,
      render: (row) => <Text size="sm" c="dimmed">{row.target || row.ip || '-'}</Text>
    },
    {
        key: 'status',
        label: 'Status',
        width: 100,
        render: (row) => (
            <Badge 
                color={row.status === 'Success' ? 'green' : 'red'} 
                variant="dot" 
                size="sm"
            >
                {row.status}
            </Badge>
        )
    },
    {
      key: 'time',
      label: 'Timestamp',
      width: 180,
      render: (row) => <Text size="sm">{new Date(row.time).toLocaleString()}</Text>
    }
  ];

  return (
    <div className="user-detail-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title={`User: ${user.username}`} 
        backAction={() => navigate('/users')}
        actions={
            <Group gap="xs">
                <Button variant="light" color="orange" leftSection={<Key size={16} />} size="xs">
                    Reset Password
                </Button>
                <Button variant="light" color="red" leftSection={<Trash size={16} />} size="xs">
                    Delete User
                </Button>
            </Group>
        }
      />

      <Grid style={{ flex: 1, padding: 'var(--spacing-lg)', display: 'flex', flexDirection: 'column' }}>
        {/* Top Info Widgets */}
        <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
            <Widget title="Profile" icon={<User size={18} className="icon-gradient-subtle" />} style={{ flex: 1 }}>
                <Group align="flex-start" gap="md">
                    <Avatar size="lg" radius="xl" color="blue">{user.username.charAt(0).toUpperCase()}</Avatar>
                    <Stack gap={4}>
                        <Text size="lg" fw={600}>{user.username}</Text>
                        <Group gap={4}>
                            <EnvelopeSimple size={14} color="var(--text-tertiary)" />
                            <Text size="sm" c="dimmed">{user.email}</Text>
                        </Group>
                         <Badge variant="light" color="blue" mt={4}>{user.role}</Badge>
                    </Stack>
                </Group>
            </Widget>

            <Widget title="Security" icon={<Shield size={18} className="icon-gradient-subtle" />} style={{ flex: 1 }}>
                <Stack gap="xs">
                     <Group justify="space-between">
                        <Text size="sm" c="dimmed">Account Status</Text>
                        <Badge color={user.status === 'Active' ? 'green' : 'gray'} variant="dot" size="sm">{user.status}</Badge>
                    </Group>
                    <Group justify="space-between">
                        <Text size="sm" c="dimmed">MFA Enabled</Text>
                         {user.mfaEnabled ? 
                            <Group gap={4}><CheckCircle size={16} color="var(--accent-primary)" /><Text size="sm">On</Text></Group> : 
                            <Group gap={4}><XCircle size={16} color="gray" /><Text size="sm">Off</Text></Group>
                         }
                    </Group>
                    <Group justify="space-between">
                        <Text size="sm" c="dimmed">Last Login</Text>
                        <Text size="sm">{new Date(user.lastLogin).toLocaleString()}</Text>
                    </Group>
                </Stack>
            </Widget>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onChange={setActiveTab} style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
            <Tabs.List style={{ marginBottom: 0, borderBottom: 'none', paddingLeft: 4 }}>
                <Tabs.Tab value="activity" leftSection={<ListDashes size={16} />}>
                    Recent Activity
                </Tabs.Tab>
                <Tabs.Tab value="permissions" leftSection={<Key size={16} />}>
                    Permissions & API Keys
                </Tabs.Tab>
            </Tabs.List>

            <div className="widget-full" style={{ flex: 1, padding: 0, overflow: 'hidden', marginTop: 'var(--spacing-sm)', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)', borderRadius: 'var(--radius)' }}>
                <Tabs.Panel value="activity" style={{ height: '100%' }}>
                     <ResizableTable 
                        columns={columns}
                        data={MOCK_ACTIVITY}
                     />
                </Tabs.Panel>
                <Tabs.Panel value="permissions" style={{ padding: 'var(--spacing-lg)' }}>
                    <Stack gap="md">
                         <Group justify="space-between">
                            <div>
                                <Text size="sm" fw={500}>API Access</Text>
                                <Text size="xs" c="dimmed">Allow this user to generate API keys</Text>
                            </div>
                            <Switch defaultChecked />
                        </Group>
                        <Text c="dimmed" size="sm" mt="md">No active API keys found.</Text>
                         <Button variant="outline" size="xs" leftSection={<Key size={14}/>} style={{ width: 'fit-content' }}>
                            Generate New API Key
                        </Button>
                    </Stack>
                </Tabs.Panel>
            </div>
        </Tabs>
      </Grid>
    </div>
  );
};

export default UserDetailPage;
