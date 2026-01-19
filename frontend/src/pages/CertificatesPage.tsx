/**
 * Certificates Management Page
 */

import { useState, useEffect } from 'react';
import { Table, Button, TextInput, Select, Badge, Group, ActionIcon, Menu, Text, Stack, Modal } from '@mantine/core';
import { IconSearch, IconPlus, IconDownload, IconTrash, IconEye, IconRefresh, IconFileImport, IconDots } from '@tabler/icons-react';
import { api } from '../utils/api';

interface Certificate {
  id: number;
  common_name: string;
  serial_number: string;
  issuer_cn: string;
  valid_from: string;
  valid_to: string;
  status: string;
  certificate_type: string;
}

export function CertificatesPage() {
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedCert, setSelectedCert] = useState<Certificate | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const loadCertificates = async () => {
    try {
      setLoading(true);
      const params: any = { page, limit: 20 };
      if (search) params.search = search;
      if (statusFilter) params.status = statusFilter;
      
      const data: any = await api.certificates.list(params);
      setCertificates(data.items || []);
      setTotal(data.total || 0);
    } catch (error: any) {
      console.error('Failed to load certificates:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCertificates();
  }, [page, search, statusFilter]);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this certificate?')) return;
    try {
      await api.certificates.delete(id);
      loadCertificates();
    } catch (error: any) {
      alert('Failed to delete certificate');
    }
  };

  const handleRevoke = async (id: number) => {
    if (!confirm('Revoke this certificate?')) return;
    try {
      await api.certificates.revoke(id, { reason: 'unspecified' });
      loadCertificates();
    } catch (error: any) {
      alert('Failed to revoke certificate');
    }
  };

  const handleDownload = async (id: number, format: 'pem' | 'der' | 'p12') => {
    try {
      const data: any = await api.certificates.export(id, format);
      const blob = new Blob([data.certificate || ''], { type: 'application/x-pem-file' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `cert-${id}.${format}`;
      a.click();
    } catch (error: any) {
      alert('Failed to export certificate');
    }
  };

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      valid: 'green',
      expired: 'red',
      revoked: 'orange',
      pending: 'blue'
    };
    return <Badge color={colors[status] || 'gray'}>{status}</Badge>;
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="xl" fw={700}>Certificates</Text>
        <Group>
          <Button leftSection={<IconFileImport size={16} />} variant="light">
            Import
          </Button>
          <Button leftSection={<IconPlus size={16} />}>
            New Certificate
          </Button>
        </Group>
      </Group>

      <Group>
        <TextInput
          placeholder="Search certificates..."
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1 }}
        />
        <Select
          placeholder="Filter by status"
          data={[
            { value: 'valid', label: 'Valid' },
            { value: 'expired', label: 'Expired' },
            { value: 'revoked', label: 'Revoked' },
            { value: 'pending', label: 'Pending' }
          ]}
          value={statusFilter}
          onChange={setStatusFilter}
          clearable
          style={{ width: 200 }}
        />
        <ActionIcon onClick={loadCertificates} variant="light">
          <IconRefresh size={18} />
        </ActionIcon>
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Common Name</Table.Th>
            <Table.Th>Serial Number</Table.Th>
            <Table.Th>Issuer</Table.Th>
            <Table.Th>Valid From</Table.Th>
            <Table.Th>Valid To</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {loading ? (
            <Table.Tr>
              <Table.Td colSpan={8} style={{ textAlign: 'center' }}>Loading...</Table.Td>
            </Table.Tr>
          ) : certificates.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={8} style={{ textAlign: 'center' }}>No certificates found</Table.Td>
            </Table.Tr>
          ) : (
            certificates.map((cert) => (
              <Table.Tr key={cert.id}>
                <Table.Td>{cert.common_name}</Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">{cert.serial_number}</Text>
                </Table.Td>
                <Table.Td>{cert.issuer_cn}</Table.Td>
                <Table.Td>
                  <Text size="xs">{new Date(cert.valid_from).toLocaleDateString()}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{new Date(cert.valid_to).toLocaleDateString()}</Text>
                </Table.Td>
                <Table.Td>{getStatusBadge(cert.status)}</Table.Td>
                <Table.Td>
                  <Badge variant="light">{cert.certificate_type}</Badge>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <ActionIcon
                      variant="light"
                      onClick={() => {
                        setSelectedCert(cert);
                        setShowDetails(true);
                      }}
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
                        <Menu.Item
                          leftSection={<IconDownload size={14} />}
                          onClick={() => handleDownload(cert.id, 'pem')}
                        >
                          Download PEM
                        </Menu.Item>
                        <Menu.Item
                          leftSection={<IconDownload size={14} />}
                          onClick={() => handleDownload(cert.id, 'der')}
                        >
                          Download DER
                        </Menu.Item>
                        <Menu.Divider />
                        {cert.status === 'valid' && (
                          <Menu.Item
                            color="orange"
                            onClick={() => handleRevoke(cert.id)}
                          >
                            Revoke
                          </Menu.Item>
                        )}
                        <Menu.Item
                          color="red"
                          leftSection={<IconTrash size={14} />}
                          onClick={() => handleDelete(cert.id)}
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

      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Showing {certificates.length} of {total} certificates
        </Text>
        <Group>
          <Button
            variant="light"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <Text size="sm">Page {page}</Text>
          <Button
            variant="light"
            disabled={certificates.length < 20}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </Group>
      </Group>

      <Modal
        opened={showDetails}
        onClose={() => setShowDetails(false)}
        title="Certificate Details"
        size="lg"
      >
        {selectedCert && (
          <Stack gap="sm">
            <div>
              <Text size="sm" fw={600}>Common Name</Text>
              <Text size="sm">{selectedCert.common_name}</Text>
            </div>
            <div>
              <Text size="sm" fw={600}>Serial Number</Text>
              <Text size="sm" c="dimmed">{selectedCert.serial_number}</Text>
            </div>
            <div>
              <Text size="sm" fw={600}>Issuer</Text>
              <Text size="sm">{selectedCert.issuer_cn}</Text>
            </div>
            <div>
              <Text size="sm" fw={600}>Valid Period</Text>
              <Text size="sm">
                {new Date(selectedCert.valid_from).toLocaleDateString()} - {new Date(selectedCert.valid_to).toLocaleDateString()}
              </Text>
            </div>
            <div>
              <Text size="sm" fw={600}>Status</Text>
              {getStatusBadge(selectedCert.status)}
            </div>
            <div>
              <Text size="sm" fw={600}>Type</Text>
              <Badge variant="light">{selectedCert.certificate_type}</Badge>
            </div>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
