/**
 * Users Management Page
 */

import { useState, useEffect } from 'react';
import { Table, Button, TextInput, Badge, Group, ActionIcon, Menu, Text, Stack } from '@mantine/core';
import { IconSearch, IconPlus, IconTrash, IconEdit, IconRefresh, IconDots, IconShield } from '@tabler/icons-react';
import { api } from '../utils/api';

interface User {
  id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const loadUsers = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (search) params.search = search;
      
      const data: any = await api.users.list(params);
      setUsers(data.items || []);
    } catch (error: any) {
      console.error('Failed to load users:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, [search]);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this user?')) return;
    try {
      await api.users.delete(id);
      loadUsers();
    } catch (error: any) {
      alert('Failed to delete user');
    }
  };

  const handleToggleActive = async (user: User) => {
    try {
      await api.users.update(user.id, { is_active: !user.is_active });
      loadUsers();
    } catch (error: any) {
      alert('Failed to update user');
    }
  };

  const getRoleBadge = (role: string) => {
    const colors: Record<string, string> = {
      admin: 'red',
      operator: 'blue',
      viewer: 'gray'
    };
    return <Badge color={colors[role] || 'gray'}>{role}</Badge>;
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="xl" fw={700}>Users</Text>
        <Button leftSection={<IconPlus size={16} />}>
          New User
        </Button>
      </Group>

      <Group>
        <TextInput
          placeholder="Search users..."
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1 }}
        />
        <ActionIcon onClick={loadUsers} variant="light">
          <IconRefresh size={18} />
        </ActionIcon>
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Username</Table.Th>
            <Table.Th>Email</Table.Th>
            <Table.Th>Role</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Last Login</Table.Th>
            <Table.Th>Created</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {loading ? (
            <Table.Tr>
              <Table.Td colSpan={7} style={{ textAlign: 'center' }}>Loading...</Table.Td>
            </Table.Tr>
          ) : users.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={7} style={{ textAlign: 'center' }}>No users found</Table.Td>
            </Table.Tr>
          ) : (
            users.map((user) => (
              <Table.Tr key={user.id}>
                <Table.Td>
                  <Group gap="xs">
                    <IconShield size={16} />
                    <Text fw={500}>{user.username}</Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">{user.email}</Text>
                </Table.Td>
                <Table.Td>{getRoleBadge(user.role)}</Table.Td>
                <Table.Td>
                  <Badge color={user.is_active ? 'green' : 'red'}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">
                    {user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{new Date(user.created_at).toLocaleDateString()}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <ActionIcon variant="light">
                      <IconEdit size={16} />
                    </ActionIcon>
                    <Menu position="bottom-end">
                      <Menu.Target>
                        <ActionIcon variant="light">
                          <IconDots size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item leftSection={<IconEdit size={14} />}>
                          Edit User
                        </Menu.Item>
                        <Menu.Item
                          onClick={() => handleToggleActive(user)}
                        >
                          {user.is_active ? 'Deactivate' : 'Activate'}
                        </Menu.Item>
                        <Menu.Item>Reset Password</Menu.Item>
                        <Menu.Item>View Permissions</Menu.Item>
                        <Menu.Divider />
                        <Menu.Item
                          color="red"
                          leftSection={<IconTrash size={14} />}
                          onClick={() => handleDelete(user.id)}
                        >
                          Delete
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))
          )}
        </Table.Tbody>
      </Table>

      <Text size="sm" c="dimmed">
        Total users: {users.length}
      </Text>
    </Stack>
  );
}
