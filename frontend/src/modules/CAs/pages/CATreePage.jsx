import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { caService } from '../services/ca.service';
import './CATreePage.css';

// Flatten tree for table display
const flattenTree = (nodes, expandedIds, level = 0) => {
  let flat = [];
  if (!nodes) return flat;
  
  nodes.forEach(node => {
    flat.push({ ...node, level });
    if (expandedIds.includes(node.refid) && node.children) {
      flat = flat.concat(flattenTree(node.children, expandedIds, level + 1));
    }
  });
  return flat;
};

const CATreePage = () => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState([]); // Don't pre-expand by default with real data unless we know ID
  const [treeData, setTreeData] = useState([]);
  const [orphansData, setOrphansData] = useState([]);
  const [flatData, setFlatData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('hierarchy');

  // Fetch Data
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [hierarchy, orphans] = await Promise.all([
          caService.getHierarchy(),
          caService.getOrphans()
        ]);
        setTreeData(hierarchy);
        setOrphansData(orphans);
      } catch (error) {
        console.error("Failed to fetch CAs", error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  // Recalculate flat data when tree or expansion changes
  useEffect(() => {
    setFlatData(flattenTree(treeData, expanded));
  }, [expanded, treeData]);

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
        <div style={{ display: 'flex', alignItems: 'center', paddingLeft: `calc(var(--control-height) * ${row.level})` }}>
          {/* Toggle Button */}
          {row.children && row.children.length > 0 ? (
            <ActionIcon 
              size="xs" 
              variant="subtle" 
              onClick={(e) => { e.stopPropagation(); toggleExpand(row.refid); }}
              style={{ marginRight: 8 }}
            >
              {expanded.includes(row.refid) ? <CaretDown /> : <CaretRight />}
            </ActionIcon>
          ) : (
            <span style={{ width: 'var(--control-height)', display: 'inline-block' }} />
          )}

          {/* Icon */}
          {row.type === 'Root CA' ? 
            <ShieldCheck size={18} weight="fill" color="var(--mantine-color-yellow-6)" style={{ marginRight: 8 }} /> : 
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
            <ActionIcon size="sm" variant="light" onClick={(e) => { e.stopPropagation(); navigate(`/cas/${row.id}`); }}>
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
          <Button leftSection={<Plus size={16} />} size="xs" onClick={() => navigate('/cas/create')}>
            Create New CA
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        <Widget className="col-12" style={{ padding: 0, overflow: 'hidden', height: '100%' }}>
            <Tabs value={activeTab} onChange={setActiveTab} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ padding: '0 16px', borderBottom: '1px solid var(--border-color)' }}>
                    <Tabs.List style={{ borderBottom: 'none' }}>
                        <Tabs.Tab value="hierarchy" leftSection={<TreeView size={16} />}>
                            Hierarchy
                        </Tabs.Tab>
                        <Tabs.Tab value="orphans" leftSection={<ListDashes size={16} />}>
                            Orphan Intermediates
                        </Tabs.Tab>
                    </Tabs.List>
                </div>

                <div style={{ flex: 1, position: 'relative' }}>
                    <Tabs.Panel value="hierarchy" style={{ height: '100%' }}>
                        <ResizableTable 
                            columns={columnsTree}
                            data={flatData}
                            onRowClick={(row) => console.log('Clicked', row)}
                        />
                    </Tabs.Panel>
                    <Tabs.Panel value="orphans" style={{ height: '100%' }}>
                        <ResizableTable 
                            columns={columnsOrphans}
                            data={orphansData}
                            onRowClick={(row) => console.log('Clicked orphan', row)}
                            emptyMessage="No orphan intermediate CAs found"
                        />
                    </Tabs.Panel>
                </div>
            </Tabs>
        </Widget>
      </Grid>
    </div>
  );
};

export default CATreePage;
