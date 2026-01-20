import React, { useState, useEffect } from 'react';
import {
  Button,
  Group,
  Badge,
  Text,
  ActionIcon,
  Tooltip,
  Tabs,
} from '@mantine/core';
import {
  Plus,
  CaretRight,
  CaretDown,
  ShieldCheck,
  Certificate,
  Eye,
  Gear,
  TreeView,
  ListDashes,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './CATreePage.css';

// Mock Data
const MOCK_CAS = [
  {
    id: 1,
    name: 'Root CA - UCM Global',
    type: 'Root CA',
    status: 'Active',
    certs: 124,
    expiry: '2035-01-01',
    children: [
      {
        id: 2,
        name: 'Intermediate CA - Web Server',
        type: 'Intermediate',
        status: 'Active',
        certs: 45,
        expiry: '2030-01-01',
        children: []
      },
      {
        id: 3,
        name: 'Intermediate CA - VPN Access',
        type: 'Intermediate',
        status: 'Active',
        certs: 78,
        expiry: '2030-01-01',
        children: []
      }
    ]
  },
  {
    id: 4,
    name: 'Root CA - Legacy 2020',
    type: 'Root CA',
    status: 'Expired',
    certs: 12,
    expiry: '2025-01-01',
    children: []
  }
];

const MOCK_ORPHANS = [
  {
    id: 101,
    name: 'Imported Intermediate CA',
    type: 'Intermediate',
    status: 'Active',
    certs: 5,
    expiry: '2028-05-15',
    issuer: 'External Root CA G2'
  },
  {
    id: 102,
    name: 'Old Dev Intermediate',
    type: 'Intermediate',
    status: 'Revoked',
    certs: 0,
    expiry: '2024-12-31',
    issuer: 'Unknown'
  }
];

// Flatten tree for table display
const flattenTree = (nodes, expandedIds, level = 0) => {
  let flat = [];
  nodes.forEach(node => {
    flat.push({ ...node, level });
    if (expandedIds.includes(node.id) && node.children) {
      flat = flat.concat(flattenTree(node.children, expandedIds, level + 1));
    }
  });
  return flat;
};

const CATreePage = () => {
  const [expanded, setExpanded] = useState([1]); // Expand first root by default
  const [data, setData] = useState([]);
  const [activeTab, setActiveTab] = useState('hierarchy');

  useEffect(() => {
    setData(flattenTree(MOCK_CAS, expanded));
  }, [expanded]);

  const toggleExpand = (id) => {
    setExpanded(prev => 
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    );
  };

  const columnsTree = [
    {
      key: 'name',
      label: 'Authority Name',
      width: 300,
      minWidth: 200,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center', paddingLeft: row.level * 24 }}>
          {/* Toggle Button */}
          {row.children && row.children.length > 0 ? (
            <ActionIcon 
              size="xs" 
              variant="subtle" 
              onClick={(e) => { e.stopPropagation(); toggleExpand(row.id); }}
              style={{ marginRight: 8 }}
            >
              {expanded.includes(row.id) ? <CaretDown /> : <CaretRight />}
            </ActionIcon>
          ) : (
            <span style={{ width: 22 }} />
          )}

          {/* Icon */}
          {row.type === 'Root CA' ? 
            <ShieldCheck size={18} weight="fill" color="#e8b339" style={{ marginRight: 8 }} /> : 
            <Certificate size={18} color="var(--accent-primary)" style={{ marginRight: 8 }} />
          }
          
          <Text size="sm" fw={500}>{row.name}</Text>
        </div>
      )
    },
    {
      key: 'type',
      label: 'Type',
      width: 120,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.type}</Badge>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Active' ? 'green' : 'red'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'certs',
      label: 'Issued Certs',
      width: 100,
      render: (row) => <Text size="sm">{row.certs}</Text>
    },
    {
      key: 'expiry',
      label: 'Expires',
      width: 120,
      render: (row) => <Text size="sm" c="dimmed">{row.expiry}</Text>
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 100,
      render: (row) => (
        <Group gap={4}>
          <Tooltip label="View Details">
            <ActionIcon size="sm" variant="light">
              <Eye size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Manage">
            <ActionIcon size="sm" variant="light">
              <Gear size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      )
    }
  ];

  const columnsOrphans = [
    {
        key: 'name',
        label: 'CA Name',
        width: 250,
        render: (row) => (
            <div style={{ display: 'flex', alignItems: 'center' }}>
                <Certificate size={18} color="var(--accent-secondary)" style={{ marginRight: 8 }} />
                <Text size="sm" fw={500}>{row.name}</Text>
            </div>
        )
    },
    {
        key: 'issuer',
        label: 'Issuer (Unknown/External)',
        width: 200,
        render: (row) => <Text size="sm" c="dimmed">{row.issuer}</Text>
    },
    {
        key: 'status',
        label: 'Status',
        width: 100,
        render: (row) => (
          <Badge 
            color={row.status === 'Active' ? 'green' : 'gray'} 
            variant="dot" 
            size="sm"
          >
            {row.status}
          </Badge>
        )
    },
    {
        key: 'expiry',
        label: 'Expires',
        width: 120,
        render: (row) => <Text size="sm" c="dimmed">{row.expiry}</Text>
    },
    {
        key: 'actions',
        label: 'Actions',
        width: 120,
        render: (row) => (
            <Group gap={4}>
            <Tooltip label="View Details">
                <ActionIcon size="sm" variant="light">
                <Eye size={16} />
                </ActionIcon>
            </Tooltip>
            </Group>
        )
    }
  ];

  return (
    <div className="ca-tree-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Certificate Authorities" 
        actions={
          <Button leftSection={<Plus size={16} />} size="xs">
            Create New CA
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column' }}>
        <Tabs value={activeTab} onChange={setActiveTab} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Tabs.List style={{ marginBottom: 0, borderBottom: 'none', paddingLeft: 4 }}>
                <Tabs.Tab value="hierarchy" leftSection={<TreeView size={16} />}>
                    Hierarchy
                </Tabs.Tab>
                <Tabs.Tab value="orphans" leftSection={<ListDashes size={16} />}>
                    Orphan Intermediates
                </Tabs.Tab>
            </Tabs.List>

            <Widget className="widget-full" style={{ flex: 1, padding: 0, overflow: 'hidden', marginTop: 8 }}>
                <Tabs.Panel value="hierarchy" style={{ height: '100%' }}>
                    <ResizableTable 
                        columns={columnsTree}
                        data={data}
                        onRowClick={(row) => console.log('Clicked', row)}
                    />
                </Tabs.Panel>
                <Tabs.Panel value="orphans" style={{ height: '100%' }}>
                    <ResizableTable 
                        columns={columnsOrphans}
                        data={MOCK_ORPHANS}
                        onRowClick={(row) => console.log('Clicked orphan', row)}
                        emptyMessage="No orphan intermediate CAs found"
                    />
                </Tabs.Panel>
            </Widget>
        </Tabs>
      </Grid>
    </div>
  );
};

export default CATreePage;
