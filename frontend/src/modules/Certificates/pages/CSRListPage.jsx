import React, { useState, useEffect, useMemo } from 'react';
import { useSelection } from '../../../core/context/SelectionContext';
import { Loader, Center, Input, Group, Button, Menu, Badge, Text } from '@mantine/core';
import { MagnifyingGlass, Download, Plus, FileArchive, FileText, FileDashed } from '@phosphor-icons/react';
import { PageHeader } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';

// Mock CSR Data until backend endpoint exists
const MOCK_CSRS = [
    { id: 1, commonName: 'web.lan.pew.pet', subject: 'CN=web.lan.pew.pet,O=PewPet,C=FR', keyType: 'RSA 2048', created: '2026-01-20' },
    { id: 2, commonName: 'db.lan.pew.pet', subject: 'CN=db.lan.pew.pet,O=PewPet,C=FR', keyType: 'ECDSA P-256', created: '2026-01-19' },
];

const CSRListPage = () => {
  const { setSelectedItem } = useSelection();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    // TODO: Replace with real API call
    setTimeout(() => {
        setItems(MOCK_CSRS);
        setLoading(false);
    }, 500);
  }, []);

  const filteredItems = useMemo(() => {
      if (!searchQuery) return items;
      return items.filter(i => 
          i.commonName.toLowerCase().includes(searchQuery.toLowerCase()) || 
          i.subject.toLowerCase().includes(searchQuery.toLowerCase())
      );
  }, [items, searchQuery]);

  const columns = [
      {
          key: 'commonName',
          label: 'Common Name',
          width: 250,
          render: (row) => (
              <Group spacing={8} noWrap>
                  <FileDashed size={16} className="icon-gradient-subtle" />
                  <Text size="sm" fw={500}>{row.commonName}</Text>
              </Group>
          )
      },
      {
          key: 'subject',
          label: 'Subject DN',
          width: 300,
          render: (row) => <Text size="sm" c="dimmed" style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>{row.subject}</Text>
      },
      {
          key: 'keyType',
          label: 'Key Algorithm',
          width: 120,
          render: (row) => <Badge variant="outline" color="gray" size="xs">{row.keyType}</Badge>
      },
      {
          key: 'created',
          label: 'Created',
          width: 120,
          flex: true,
          render: (row) => <Text size="sm">{row.created}</Text>
      },
      {
          key: 'actions',
          label: 'Actions',
          width: 100,
          align: 'center',
          render: (row) => (
              <Button variant="subtle" size="xs" compact>Sign</Button>
          )
      }
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Certificate Signing Requests" 
        actions={
          <Group spacing="xs">
             <div style={{ width: 250 }}>
                <Input 
                    placeholder="Search CSRs..." 
                    size="xs"
                    leftSection={<MagnifyingGlass size={14} />}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                />
             </div>
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
                Create CSR
             </Button>
          </Group>
        }
      />

      <div style={{ flex: 1, overflow: 'hidden', padding: '12px' }}>
         <div style={{ height: '100%', border: '1px solid var(--border-color)', borderRadius: 'var(--control-radius)', background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {loading ? (
                <Center style={{ height: '100%' }}>
                    <div className="spinner" size="sm" />
                </Center>
            ) : (
                <ResizableTable 
                    columns={columns}
                    data={filteredItems}
                    onRowClick={(row) => setSelectedItem({...row, type: 'CSR', title: row.commonName, subtitle: row.keyType, details: row})}
                    emptyMessage="No pending CSRs found"
                />
            )}
         </div>
      </div>
    </div>
  );
};

export default CSRListPage;
