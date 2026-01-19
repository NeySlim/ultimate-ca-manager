/**
 * Certificate Authorities Management Page
 */

import { useState, useEffect } from 'react';
import { Table, Button, TextInput, Badge, Group, ActionIcon, Menu, Text, Stack, Modal, Card } from '@mantine/core';
import { IconSearch, IconPlus, IconTrash, IconEye, IconRefresh, IconDots, IconCertificate } from '@tabler/icons-react';
import { api } from '../utils/api';

interface CA {
  id: number;
  common_name: string;
  organization: string;
  country: string;
  valid_from: string;
  valid_to: string;
  is_root: boolean;
  parent_ca_id: number | null;
  status: string;
}

export function CAsPage() {
  const [cas, setCAs] = useState<CA[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCA, setSelectedCA] = useState<CA | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [issuedCerts, setIssuedCerts] = useState<any[]>([]);

  const loadCAs = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (search) params.search = search;
      
      const data: any = await api.cas.list(params);
      setCAs(data.items || []);
    } catch (error: any) {
      console.error('Failed to load CAs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCAs();
  }, [search]);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this CA? This will also affect all issued certificates.')) return;
    try {
      await api.cas.delete(id);
      loadCAs();
    } catch (error: any) {
      alert('Failed to delete CA');
    }
  };

  const handleViewIssued = async (ca: CA) => {
    try {
      const data: any = await api.cas.getIssuedCertificates(ca.id);
      setIssuedCerts(data.items || []);
      setSelectedCA(ca);
      setShowDetails(true);
    } catch (error: any) {
      alert('Failed to load issued certificates');
    }
  };

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      active: 'green',
      expired: 'red',
      revoked: 'orange'
    };
    return <Badge color={colors[status] || 'gray'}>{status}</Badge>;
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="xl" fw={700}>Certificate Authorities</Text>
        <Button leftSection={<IconPlus size={16} />}>
          New CA
        </Button>
      </Group>

      <Group>
        <TextInput
          placeholder="Search CAs..."
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1 }}
        />
        <ActionIcon onClick={loadCAs} variant="light">
          <IconRefresh size={18} />
        </ActionIcon>
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Common Name</Table.Th>
            <Table.Th>Organization</Table.Th>
            <Table.Th>Country</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Valid From</Table.Th>
            <Table.Th>Valid To</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {loading ? (
            <Table.Tr>
              <Table.Td colSpan={8} style={{ textAlign: 'center' }}>Loading...</Table.Td>
            </Table.Tr>
          ) : cas.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={8} style={{ textAlign: 'center' }}>No CAs found</Table.Td>
            </Table.Tr>
          ) : (
            cas.map((ca) => (
              <Table.Tr key={ca.id}>
                <Table.Td>
                  <Group gap="xs">
                    <IconCertificate size={16} />
                    <Text fw={500}>{ca.common_name}</Text>
                  </Group>
                </Table.Td>
                <Table.Td>{ca.organization}</Table.Td>
                <Table.Td>{ca.country}</Table.Td>
                <Table.Td>
                  <Badge variant="light" color={ca.is_root ? 'blue' : 'gray'}>
                    {ca.is_root ? 'Root CA' : 'Intermediate CA'}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{new Date(ca.valid_from).toLocaleDateString()}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{new Date(ca.valid_to).toLocaleDateString()}</Text>
                </Table.Td>
                <Table.Td>{getStatusBadge(ca.status)}</Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <ActionIcon
                      variant="light"
                      onClick={() => handleViewIssued(ca)}
                    >
                      <IconEye size={16} />
                    </ActionIcon>
                    <Menu position="bottom-end">
                      <Menu.Target>
                        <ActionIcon variant="light">
                          <IconDots size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item>View Details</Menu.Item>
                        <Menu.Item>View Issued Certificates</Menu.Item>
                        <Menu.Item>Download Certificate</Menu.Item>
                        <Menu.Divider />
                        <Menu.Item
                          color="red"
                          leftSection={<IconTrash size={14} />}
                          onClick={() => handleDelete(ca.id)}
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

      <Modal
        opened={showDetails}
        onClose={() => setShowDetails(false)}
        title={`Issued Certificates - ${selectedCA?.common_name}`}
        size="xl"
      >
        {selectedCA && (
          <Stack gap="md">
            <Card withBorder>
              <Stack gap="xs">
                <Text size="sm" fw={600}>CA Information</Text>
                <Group>
                  <Text size="sm" c="dimmed">Type:</Text>
                  <Badge variant="light" color={selectedCA.is_root ? 'blue' : 'gray'}>
                    {selectedCA.is_root ? 'Root CA' : 'Intermediate CA'}
                  </Badge>
                </Group>
                <Group>
                  <Text size="sm" c="dimmed">Organization:</Text>
                  <Text size="sm">{selectedCA.organization}</Text>
                </Group>
                <Group>
                  <Text size="sm" c="dimmed">Status:</Text>
                  {getStatusBadge(selectedCA.status)}
                </Group>
              </Stack>
            </Card>

            <Text size="sm" fw={600}>Issued Certificates ({issuedCerts.length})</Text>
            {issuedCerts.length === 0 ? (
              <Text size="sm" c="dimmed">No certificates issued yet</Text>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Common Name</Table.Th>
                    <Table.Th>Serial Number</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th>Valid To</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {issuedCerts.map((cert) => (
                    <Table.Tr key={cert.id}>
                      <Table.Td>{cert.common_name}</Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">{cert.serial_number}</Text>
                      </Table.Td>
                      <Table.Td>{getStatusBadge(cert.status)}</Table.Td>
                      <Table.Td>
                        <Text size="xs">{new Date(cert.valid_to).toLocaleDateString()}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
