import React, { useState, useMemo } from 'react';
import {
  Badge,
  Input,
  Select,
  ActionIcon,
  Tooltip,
  Group,
  Text,
  Box,
} from '../../../components/ui';
import {
  MagnifyingGlass,
  Eye,
  Download,
  Trash,
  WarningCircle,
} from '@phosphor-icons/react';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './CertificateTable.css';

const CertificateTable = ({ data, onRowClick, onDelete, onDownload, onView, selectedId }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState(null);
  const [caFilter, setCaFilter] = useState(null);

  // Filter data
  const filteredData = useMemo(() => {
      return data.filter(cert => {
        const matchesSearch =
          cert.commonName?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          cert.issuer?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          cert.serial?.toLowerCase().includes(searchTerm.toLowerCase());

        const matchesStatus = !statusFilter || cert.status === statusFilter;
        const matchesCA = !caFilter || cert.ca === caFilter;

        return matchesSearch && matchesStatus && matchesCA;
      });
  }, [data, searchTerm, statusFilter, caFilter]);

  // Get unique CAs for filter
  const caOptions = useMemo(() => 
    Array.from(new Set(data.map(cert => cert.ca)))
      .map(ca => ({ value: ca, label: ca })),
  [data]);

  // Status Color Helper
  const getStatusColor = (status) => {
    switch (status) {
      case 'Valid': return 'green';
      case 'Warning': return 'yellow';
      case 'Expired': return 'red';
      case 'Revoked': return 'gray';
      default: return 'blue';
    }
  };

  // Date Formatter
  const formatDate = (dateString) => {
    if (!dateString) return '-';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  // Expiry Check
  const getExpiryStatus = (expiryDate) => {
    if (!expiryDate) return null;
    const now = new Date();
    const expiry = new Date(expiryDate);
    const daysLeft = Math.ceil((expiry - now) / (1000 * 60 * 60 * 24));
    if (daysLeft < 0) return 'expired';
    if (daysLeft < 30) return 'critical';
    if (daysLeft < 90) return 'warning';
    return 'valid';
  };

  // Define Columns for ResizableTable
  const columns = [
    {
      key: 'status',
      label: 'Status',
      width: 100,
      minWidth: 80,
      render: (row) => (
        <Badge color={getStatusColor(row.status)} variant="dot" size="sm">
          {row.status}
        </Badge>
      )
    },
    {
      key: 'commonName',
      label: 'Common Name',
      width: 200,
      minWidth: 150,
      render: (row) => (
        <Text size="sm" fw={500} truncate>{row.commonName}</Text>
      )
    },
    {
      key: 'serial',
      label: 'Serial',
      width: 150,
      minWidth: 100,
      render: (row) => (
        <Tooltip label={row.serial}>
            <Text size="xs" className="mono-text" truncate>
            {row.serial?.substring(0, 16)}...
            </Text>
        </Tooltip>
      )
    },
    {
      key: 'issuer',
      label: 'Issuer',
      width: 180,
      minWidth: 120,
      render: (row) => <Text size="sm" truncate>{row.issuer}</Text>
    },
    {
      key: 'issuedDate',
      label: 'Issued',
      width: 120,
      render: (row) => <Text size="sm">{formatDate(row.issuedDate)}</Text>
    },
    {
      key: 'expiryDate',
      label: 'Expires',
      width: 140,
      render: (row) => {
        const status = getExpiryStatus(row.expiryDate);
        return (
          <Group gap="xs">
            <Text size="sm">{formatDate(row.expiryDate)}</Text>
            {status === 'critical' && <WarningCircle size={16} color="var(--accent-primary)" weight="fill" />}
          </Group>
        );
      }
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 100,
      minWidth: 80,
      render: (row) => (
        <Group gap={4}>
            <Tooltip label="Download">
                <ActionIcon size="sm" variant="subtle" onClick={(e) => { e.stopPropagation(); onDownload?.(row); }}>
                    <Download size={16} />
                </ActionIcon>
            </Tooltip>
            <Tooltip label="Delete">
                <ActionIcon size="sm" variant="subtle" color="red" onClick={(e) => { e.stopPropagation(); onDelete?.(row); }}>
                    <Trash size={16} />
                </ActionIcon>
            </Tooltip>
        </Group>
      )
    }
  ];

  return (
    <div className="certificate-table-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-surface)' }}>
      {/* Filters Toolbar */}
      <div className="certificate-toolbar" style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '12px', alignItems: 'center', background: 'var(--bg-surface)' }}>
        <Input
          placeholder="Search..."
          leftSection={<MagnifyingGlass size={16} className="icon-gradient-subtle" />}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.currentTarget.value)}
          size="xs"
          style={{ width: 250 }}
        />
        <Select
          placeholder="Status"
          data={['Valid', 'Warning', 'Expired', 'Revoked']}
          value={statusFilter}
          onChange={setStatusFilter}
          clearable
          size="xs"
          style={{ width: 120 }}
        />
        <Select
          placeholder="CA"
          data={caOptions}
          value={caFilter}
          onChange={setCaFilter}
          clearable
          size="xs"
          style={{ width: 150 }}
        />
        <div style={{ flex: 1 }} />
        <Text size="xs" c="dimmed">
          {filteredData.length} items
        </Text>
      </div>

      {/* Resizable Table */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <ResizableTable 
            columns={columns}
            data={filteredData}
            onRowClick={(row) => {
                onRowClick?.(row);
            }}
            rowClassName={(row) => row.id === selectedId ? 'selected' : ''}
        />
      </div>
    </div>
  );
};

export default CertificateTable;
