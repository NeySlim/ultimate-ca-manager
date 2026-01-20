import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Badge, Text, Group, ActionIcon, Input, Pagination } from '@mantine/core';
import { Plus, MagnifyingGlass, FileText, Trash, Key, User, CalendarBlank, PenNib } from '@phosphor-icons/react';
import { PageHeader } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import { CsrService } from '../services/csr.service';
import { useSelection } from '../../../core/context/SelectionContext';

const CSRListPage = () => {
  const navigate = useNavigate();
  const { setSelectedItem, selectedItem } = useSelection();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Fetch Data
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await CsrService.getAll();
      setItems(data);
    } catch (error) {
      console.error("Failed to fetch CSRs", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (row) => {
    if (confirm(`Are you sure you want to delete CSR ${row.cn}?`)) {
        await CsrService.delete(row.id);
        loadData();
        if (selectedItem?.id === row.id) setSelectedItem(null);
    }
  };

  // Filter & Pagination
  const filteredData = useMemo(() => {
    return items.filter(item => 
      item.cn.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.requester.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [items, searchTerm]);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredData.slice(start, start + itemsPerPage);
  }, [filteredData, currentPage]);

  const totalPages = Math.ceil(filteredData.length / itemsPerPage);

  // Columns
  const columns = [
    {
      key: 'status',
      label: 'Status',
      width: 100,
      minWidth: 80,
      sortable: true,
      render: (row) => (
        <Badge 
          color={row.status === 'Approved' ? 'green' : row.status === 'Pending' ? 'orange' : 'gray'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'cn',
      label: 'Common Name',
      minWidth: 200,
      flex: true, // This column will expand
      sortable: true,
      render: (row) => (
        <Group gap="xs" wrap="nowrap">
            <FileText size={16} className="icon-gradient" />
            <Text size="sm" fw={500} truncate>{row.cn}</Text>
        </Group>
      )
    },
    {
      key: 'key_type',
      label: 'Key Type',
      width: 140,
      sortable: true,
      render: (row) => (
        <Group gap="xs" wrap="nowrap" c="dimmed">
            <Key size={14} />
            <Text size="sm">{row.key_type}</Text>
        </Group>
      )
    },
    {
      key: 'requester',
      label: 'Requester',
      width: 150,
      sortable: true,
      render: (row) => (
        <Group gap="xs" wrap="nowrap" c="dimmed">
            <User size={14} />
            <Text size="sm">{row.requester}</Text>
        </Group>
      )
    },
    {
      key: 'created_at',
      label: 'Created',
      width: 150,
      sortable: true,
      render: (row) => (
        <Group gap="xs" wrap="nowrap" c="dimmed">
            <CalendarBlank size={14} />
            <Text size="sm">{new Date(row.created_at).toLocaleDateString()}</Text>
        </Group>
      )
    },
    {
      key: 'actions',
      label: '',
      width: 60,
      render: (row) => (
        <ActionIcon size="sm" variant="subtle" color="red" onClick={(e) => { e.stopPropagation(); handleDelete(row); }}>
            <Trash size={16} />
        </ActionIcon>
      )
    }
  ];

  return (
    <div className="csr-list-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Certificate Signing Requests" 
        actions={
          <Button leftSection={<Plus size={16} />} size="xs" onClick={() => navigate('/csrs/create')}>
            New CSR
          </Button>
        }
      />

      {/* Toolbar */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-panel)', display: 'flex' }}>
        <Input
            placeholder="Search CSRs..."
            leftSection={<MagnifyingGlass size={16} className="icon-gradient-subtle" />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.currentTarget.value)}
            size="xs"
            style={{ width: 300 }}
        />
      </div>

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
         <ResizableTable 
            columns={columns}
            data={paginatedData}
            onRowClick={(row) => setSelectedItem({
                ...row, 
                type: 'CSR', 
                title: row.cn, 
                subtitle: `${row.key_type} • ${row.status}`,
                details: row
            })}
            onSort={handleSort}
            sortConfig={sortConfig}
            rowClassName={(row) => selectedItem?.id === row.id ? 'selected' : ''}
            emptyMessage="No CSRs found"
         />
      </div>
      
      {totalPages > 1 && (
        <div style={{ padding: '8px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
            <Pagination total={totalPages} value={currentPage} onChange={setCurrentPage} size="xs" />
        </div>
      )}
    </div>
  );
};

export default CSRListPage;
