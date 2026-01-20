import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Group,
  Text,
  Badge,
  Avatar,
  ActionIcon,
  Tooltip,
  Input,
} from '@mantine/core';
import {
  User,
  Plus,
  Key,
  Shield,
  Trash,
  PencilSimple,
  EnvelopeSimple,
  CheckCircle,
  MagnifyingGlass,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './UsersPage.css';

// Mock Data
const MOCK_USERS = [
  {
    id: 1,
    username: 'admin',
    email: 'admin@internal.corp',
    role: 'Administrator',
    status: 'Active',
    lastLogin: '2024-03-20T10:30:00Z',
    mfa: true
  },
  {
    id: 2,
    username: 'operator',
    email: 'ops@internal.corp',
    role: 'Operator',
    status: 'Active',
    lastLogin: '2024-03-19T15:45:00Z',
    mfa: true
  },
  {
    id: 3,
    username: 'auditor',
    email: 'audit@internal.corp',
    role: 'Auditor',
    status: 'Inactive',
    lastLogin: '2024-02-10T09:00:00Z',
    mfa: false
  }
];

const UsersPage = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');

  const columns = [
    {
      key: 'username',
      label: 'User',
      width: 250,
      render: (row) => (
        <Group gap="sm">
          <Avatar size="sm" radius="xl" color="blue">{row.username.charAt(0).toUpperCase()}</Avatar>
          <div>
            <Text size="sm" fw={500}>{row.username}</Text>
            <Group gap={4}>
                <EnvelopeSimple size={12} color="var(--text-tertiary)" />
                <Text size="xs" c="dimmed">{row.email}</Text>
            </Group>
          </div>
        </Group>
      )
    },
    {
      key: 'role',
      label: 'Role',
      width: 150,
      render: (row) => (
        <Group gap={6}>
            <Shield size={14} className="icon-gradient-subtle" />
            <Text size="sm">{row.role}</Text>
        </Group>
      )
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Active' ? 'green' : 'gray'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'mfa',
      label: 'MFA',
      width: 80,
      render: (row) => (
        row.mfa ? 
        <Tooltip label="MFA Enabled">
            <CheckCircle size={18} color="var(--status-success)" weight="fill" />
        </Tooltip> 
        : 
        <Text size="xs" c="dimmed">-</Text>
      )
    },
    {
      key: 'lastLogin',
      label: 'Last Login',
      width: 150,
      render: (row) => <Text size="sm" c="dimmed">{new Date(row.lastLogin).toLocaleDateString()}</Text>
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 120,
      render: (row) => (
        <Group gap={4}>
          <Tooltip label="Edit User">
            <ActionIcon size="sm" variant="light" onClick={(e) => { e.stopPropagation(); navigate(`/users/${row.id}`); }}>
              <PencilSimple size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Reset Password">
            <ActionIcon size="sm" variant="light" color="orange">
              <Key size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Delete">
            <ActionIcon size="sm" variant="light" color="red">
              <Trash size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      )
    }
  ];

  return (
    <div className="users-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="User Management" 
        actions={
          <Button leftSection={<Plus size={16} />} size="xs">
            Add User
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        <Widget className="widget-full" style={{ height: '100%', padding: 0, overflow: 'hidden' }}>
          
          {/* Integrated Toolbar matching Certificates */}
          <div style={{ padding: '12px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '12px', alignItems: 'center', backgroundColor: 'var(--bg-panel)' }}>
             <Input
               placeholder="Search users..."
               leftSection={<MagnifyingGlass size={16} className="icon-gradient-subtle" />}
               value={searchTerm}
               onChange={(e) => setSearchTerm(e.currentTarget.value)}
               size="xs"
               style={{ width: 250 }}
             />
             <div style={{ flex: 1 }} />
             <Text size="xs" c="dimmed">
               {MOCK_USERS.length} users
             </Text>
          </div>

          <ResizableTable 
            columns={columns}
            data={MOCK_USERS}
            onRowClick={(row) => console.log('Clicked User', row)}
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default UsersPage;
