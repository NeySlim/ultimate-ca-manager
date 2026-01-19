import { useState, useEffect } from 'react';
import { 
  Box, 
  Stack, 
  Paper, 
  Table, 
  Group, 
  Button, 
  Text,
  Badge,
  ActionIcon,
  Menu
} from '@mantine/core';
import { 
  Plus,
  DotsThree,
  Eye,
  TrashSimple,
  TreeStructure
} from '@phosphor-icons/react';
import { casAPI } from '../lib/api';
import { notifications } from '@mantine/notifications';

export default function CAsPage() {
  const [cas, setCas] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCAs();
  }, []);

  const loadCAs = async () => {
    try {
      setLoading(true);
      const data = await casAPI.list();
      setCas(data.items || []);
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: error.message,
        color: 'red'
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <div>
          <Text size="24px" fw={600}>Certificate Authorities</Text>
          <Text size="13px" c="dimmed">Manage certificate authorities</Text>
        </div>
        <Group>
          <Button 
            leftSection={<TreeStructure size={16} />}
            variant="default"
          >
            View Tree
          </Button>
          <Button 
            leftSection={<Plus size={16} />}
            style={{
              background: 'linear-gradient(135deg, #5eb89b, #7bc9af)'
            }}
          >
            New CA
          </Button>
        </Group>
      </Group>

      <Paper p="md" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
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
              <Table.Th>Common Name</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Parent</Table.Th>
              <Table.Th>Certificates</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th style={{ width: '60px' }}></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {loading ? (
              <Table.Tr>
                <Table.Td colSpan={6} style={{ textAlign: 'center', padding: '40px' }}>
                  <Text size="13px" c="dimmed">Loading...</Text>
                </Table.Td>
              </Table.Tr>
            ) : cas.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={6} style={{ textAlign: 'center', padding: '40px' }}>
                  <Text size="13px" c="dimmed">No certificate authorities found</Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              cas.map((ca) => (
                <Table.Tr key={ca.id}>
                  <Table.Td>
                    <Text fw={500}>{ca.common_name}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={ca.is_root ? 'blue' : 'gray'}>
                      {ca.is_root ? 'Root' : 'Intermediate'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{ca.parent_name || '-'}</Table.Td>
                  <Table.Td>{ca.cert_count || 0}</Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={ca.active ? 'green' : 'gray'}>
                      {ca.active ? 'Active' : 'Inactive'}
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
              ))
            )}
          </Table.Tbody>
        </Table>
      </Paper>
    </Stack>
  );
}
