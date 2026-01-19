import { useState, useEffect } from 'react';
import { 
  Box, 
  Stack, 
  Paper, 
  Table, 
  TextInput, 
  Select, 
  Group, 
  Button, 
  Badge,
  Text,
  Pagination,
  ActionIcon,
  Menu
} from '@mantine/core';
import { 
  MagnifyingGlass,
  Plus,
  DotsThree,
  Download,
  TrashSimple,
  Eye
} from '@phosphor-icons/react';
import { certificatesAPI } from '../lib/api';
import { notifications } from '@mantine/notifications';

export default function CertificatesPage() {
  const [certificates, setCertificates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    loadCertificates();
  }, [page, search, statusFilter]);

  const loadCertificates = async () => {
    try {
      setLoading(true);
      const data = await certificatesAPI.list({
        page,
        search,
        status: statusFilter === 'all' ? undefined : statusFilter
      });
      setCertificates(data.items || []);
      setTotalPages(data.pages || 1);
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

  const getStatusBadge = (status) => {
    const colors = {
      valid: 'green',
      expired: 'red',
      revoked: 'gray'
    };
    return (
      <Badge 
        size="xs" 
        color={colors[status] || 'gray'}
        style={{ textTransform: 'capitalize' }}
      >
        {status}
      </Badge>
    );
  };

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <div>
          <Text size="24px" fw={600}>Certificates</Text>
          <Text size="13px" c="dimmed">Manage SSL/TLS certificates</Text>
        </div>
        <Button 
          leftSection={<Plus size={16} />}
          style={{
            background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)'
          }}
        >
          New Certificate
        </Button>
      </Group>

      <Paper p="md" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
        <Group mb="md">
          <TextInput
            placeholder="Search certificates..."
            leftSection={<MagnifyingGlass size={16} />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            placeholder="Status"
            data={[
              { value: 'all', label: 'All Status' },
              { value: 'valid', label: 'Valid' },
              { value: 'expired', label: 'Expired' },
              { value: 'revoked', label: 'Revoked' }
            ]}
            value={statusFilter}
            onChange={(value) => setStatusFilter(value || 'all')}
            style={{ width: '150px' }}
          />
        </Group>

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
              <Table.Th>Serial Number</Table.Th>
              <Table.Th>Issuer</Table.Th>
              <Table.Th>Expires</Table.Th>
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
            ) : certificates.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={6} style={{ textAlign: 'center', padding: '40px' }}>
                  <Text size="13px" c="dimmed">No certificates found</Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              certificates.map((cert) => (
                <Table.Tr key={cert.id}>
                  <Table.Td>
                    <Text fw={500}>{cert.common_name}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text ff="JetBrains Mono" size="12px">{cert.serial_number}</Text>
                  </Table.Td>
                  <Table.Td>{cert.issuer}</Table.Td>
                  <Table.Td>{new Date(cert.not_after).toLocaleDateString()}</Table.Td>
                  <Table.Td>{getStatusBadge(cert.status)}</Table.Td>
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
                        <Menu.Item leftSection={<Download size={14} />}>
                          Download
                        </Menu.Item>
                        <Menu.Divider />
                        <Menu.Item leftSection={<TrashSimple size={14} />} color="red">
                          Revoke
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              ))
            )}
          </Table.Tbody>
        </Table>

        {totalPages > 1 && (
          <Group justify="center" mt="md">
            <Pagination 
              total={totalPages} 
              value={page} 
              onChange={setPage}
              size="sm"
            />
          </Group>
        )}
      </Paper>
    </Stack>
  );
}
