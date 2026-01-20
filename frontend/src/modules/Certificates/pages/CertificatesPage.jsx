import React, { useState, useEffect, useMemo } from 'react';
import { useSelection } from '../../../core/context/SelectionContext';
import { CertificateService } from '../services/certificates.service';
import { Loader, Center, Input, Group, Button, Menu, Badge, Text, Pagination } from '@mantine/core';
import { MagnifyingGlass, Download, Plus, FileArchive, FileText, Certificate as CertIcon } from '@phosphor-icons/react';
import { PageHeader } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';

const CertificatesPage = () => {
  const { setSelectedItem, selectedItem } = useSelection();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 15;
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

  useEffect(() => {
    const loadData = async () => {
        setLoading(true);
        try {
            const data = await CertificateService.getAll();
            setItems(data);
        } catch (error) {
            console.error("Failed to load certificates", error);
        } finally {
            setLoading(false);
        }
    };
    loadData();
  }, []);

  const handleSort = (key) => {
      let direction = 'asc';
      if (sortConfig.key === key && sortConfig.direction === 'asc') {
          direction = 'desc';
      }
      setSortConfig({ key, direction });
  };

  const filteredItems = useMemo(() => {
      let result = items;
      if (searchQuery) {
          result = items.filter(i => 
              i.commonName.toLowerCase().includes(searchQuery.toLowerCase()) || 
              i.issuer.toLowerCase().includes(searchQuery.toLowerCase())
          );
      }
      
      if (sortConfig.key) {
        result = [...result].sort((a, b) => {
            if (a[sortConfig.key] < b[sortConfig.key]) return sortConfig.direction === 'asc' ? -1 : 1;
            if (a[sortConfig.key] > b[sortConfig.key]) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });
      }

      return result;
  }, [items, searchQuery, sortConfig]);

  const paginatedItems = useMemo(() => {
      const start = (currentPage - 1) * itemsPerPage;
      return filteredItems.slice(start, start + itemsPerPage);
  }, [filteredItems, currentPage]);

  const totalPages = Math.ceil(filteredItems.length / itemsPerPage);

  const columns = [
      {
          key: 'commonName',
          label: 'Common Name',
          width: 250,
          sortable: true,
          render: (row) => (
              <Group spacing={8} noWrap>
                  <CertIcon size={16} className="icon-gradient-subtle" />
                  <Text size="sm" fw={500}>{row.commonName}</Text>
              </Group>
          )
      },
      {
          key: 'issuer',
          label: 'Issuer',
          width: 200,
          sortable: true,
          render: (row) => <Text size="sm" c="dimmed">{row.issuer}</Text>
      },
      {
          key: 'serial',
          label: 'Serial Number',
          width: 150,
          sortable: true,
          render: (row) => <Text size="sm" style={{ fontFamily: 'var(--font-mono)' }}>{row.serial?.substring(0, 16)}...</Text>
      },
      {
          key: 'validTo',
          label: 'Expires',
          width: 120,
          sortable: true,
          render: (row) => <Text size="sm">{row.validTo}</Text>
      },
      {
          key: 'status',
          label: 'Status',
          width: 100,
          flex: true,
          sortable: true,
          render: (row) => (
              <Badge 
                  color={row.isValid ? 'green' : 'red'} 
                  variant="dot" 
                  size="sm"
              >
                  {row.isValid ? 'Valid' : 'Expired'}
              </Badge>
          )
      }
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Certificates" 
        actions={
          <Group spacing="xs">
             <Menu shadow="md" width={200}>
                <Menu.Target>
                  <Button variant="default" leftSection={<Download size={16} />} size="xs">Export</Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item leftSection={<FileText size={14} />}>Export CSV</Menu.Item>
                  <Menu.Item leftSection={<FileArchive size={14} />}>Export JSON</Menu.Item>
                </Menu.Dropdown>
             </Menu>
             <Button leftSection={<Plus size={16} />} size="xs">
                Issue Certificate
             </Button>
          </Group>
        }
      />

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-panel)', display: 'flex' }}>
        <Input 
            placeholder="Search certificates..." 
            size="xs"
            leftSection={<MagnifyingGlass size={16} className="icon-gradient-subtle" />}
            value={searchQuery}
            onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
            }}
            style={{ width: 300 }}
        />
      </div>

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '12px' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', border: '1px solid var(--border-color)', borderRadius: 'var(--control-radius)', background: 'var(--bg-surface)', overflow: 'hidden' }}>
        {loading ? (
            <Center style={{ height: '100%' }}>
                <div className="spinner" size="sm" />
            </Center>
        ) : (
            <>
                <ResizableTable 
                    columns={columns}
                    data={paginatedItems}
                    onRowClick={(row) => setSelectedItem({...row, type: 'Certificate', title: row.commonName, subtitle: row.issuer, details: row})}
                    onSort={handleSort}
                    sortConfig={sortConfig}
                    rowClassName={(row) => selectedItem?.id === row.id ? 'selected' : ''}
                    emptyMessage="No certificates found"
                />
            </>
        )}
        </div>
      </div>

      {totalPages > 1 && (
        <div style={{ padding: '8px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
            <Pagination total={totalPages} value={currentPage} onChange={setCurrentPage} size="xs" />
        </div>
      )}
    </div>
  );
};

export default CertificatesPage;
