import { useState, useEffect } from 'react';
import { 
  Stack, 
  Paper, 
  Table, 
  Group, 
  Button, 
  Text,
  Badge,
  ActionIcon,
  Menu,
  TextInput
} from '@mantine/core';
import { 
  Plus,
  DotsThree,
  Eye,
  TrashSimple,
  MagnifyingGlass,
  UserCircle
} from '@phosphor-icons/react';
import { notifications } from '@mantine/notifications';

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const mockUsers = [
    { id: 1, username: 'admin', email: 'admin@ucm.local', role: 'admin', active: true },
    { id: 2, username: 'operator', email: 'operator@ucm.local', role: 'operator', active: true }
  ];

  useEffect(() => {
    setUsers(mockUsers);
  }, []);

  const getRoleBadge = (role) => {
    const colors = {
      admin: 'red',
      operator: 'blue',
      viewer: 'gray'
    };
    return (
      <Badge size="xs" color={colors[role] || 'gray'}>
        {role}
      </Badge>
    );
  };

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <div>
          <Text size="24px" fw={600}>Users</Text>
          <Text size="13px" c="dimmed">Manage user accounts</Text>
        </div>
        <Button 
          leftSection={<Plus size={16} />}
          style={{
            background: 'linear-gradient(135deg, #c99652, #d9ac73)'
          }}
        >
          New User
        </Button>
      </Group>

      <Paper p="md" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
        <TextInput
          placeholder="Search users..."
          leftSection={<MagnifyingGlass size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          mb="md"
        />

        <Table
          highlightOnHover
          styles={{
            th: {
              background: '#1e1e1e',
              fontSize: '11px',
              textTransform: 'uppercase',
              fontWeight: 600,
              padding: '8px 12px'
            },
            td: {
              fontSize: '13px',
              padding: '8px 12px'
            }
          }}
        >
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Username</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th>Role</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th style={{ width: '60px' }}></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users.map((user) => (
              <Table.Tr key={user.id}>
                <Table.Td>
                  <Group gap="xs">
                    <UserCircle size={18} weight="fill" />
                    <Text fw={500}>{user.username}</Text>
                  </Group>
                </Table.Td>
                <Table.Td>{user.email}</Table.Td>
                <Table.Td>{getRoleBadge(user.role)}</Table.Td>
                <Table.Td>
                  <Badge size="xs" color={user.active ? 'green' : 'gray'}>
                    {user.active ? 'Active' : 'Inactive'}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Menu shadow="md" width={180}>
                    <Menu.Target>
                      <ActionIcon variant="subtle" size="sm">
                        <DotsThree size={16} />
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item leftSection={<Eye size={14} />}>
                        View Details
                      </Menu.Item>
                      <Menu.Divider />
                      <Menu.Item leftSection={<TrashSimple size={14} />} color="red">
                        Delete
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
    </Stack>
  );
}
