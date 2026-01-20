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

import { useSelection } from '../../../core/context/SelectionContext';

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
  const { setSelectedItem } = useSelection();
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
            <Certificate size={18} className="icon-gradient" style={{ marginRight: 8 }} />
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
      minWidth: 120,
      flex: true,
      render: (row) => <Text size="sm" c="dimmed">{row.expiry}</Text>
    }
  ];

  const columnsOrphans = [
    {
        key: 'name',
        label: 'CA Name',
        width: 250,
        render: (row) => (
            <div style={{ display: 'flex', alignItems: 'center' }}>
                <Certificate size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
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
        minWidth: 120,
        flex: true,
        render: (row) => <Text size="sm" c="dimmed">{row.expiry}</Text>
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

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <Tabs 
              value={activeTab} 
              onChange={setActiveTab} 
              radius="xs"
              style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
              classNames={{
                tab: 'custom-tab',
                list: 'custom-tab-list',
                panel: 'custom-tab-panel' // Add class for panel
              }}
            >
                <div style={{ padding: '0 16px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-panel)' }}>
                    <Tabs.List style={{ borderBottom: 'none' }}>
                        <Tabs.Tab 
                          value="hierarchy" 
                          leftSection={<TreeView size={16} />}
                          style={{ fontSize: 'var(--font-size-control)', fontWeight: 500 }}
                        >
                            Hierarchy
                        </Tabs.Tab>
                        <Tabs.Tab 
                          value="orphans" 
                          leftSection={<ListDashes size={16} />}
                          style={{ fontSize: 'var(--font-size-control)', fontWeight: 500 }}
                        >
                            Orphan Intermediates
                        </Tabs.Tab>
                    </Tabs.List>
                </div>

                <div style={{ flex: 1, position: 'relative', background: 'var(--bg-app)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                    <Tabs.Panel value="hierarchy" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                        <ResizableTable 
                            columns={columnsTree}
                            data={flatData}
                            onRowClick={(row) => setSelectedItem({...row, type: 'CA', title: row.name, subtitle: row.status})}
                        />
                    </Tabs.Panel>
                    <Tabs.Panel value="orphans" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                        <ResizableTable 
                            columns={columnsOrphans}
                            data={orphansData}
                            onRowClick={(row) => setSelectedItem({...row, type: 'CA', title: row.name, subtitle: row.issuer})}
                            emptyMessage="No orphan intermediate CAs found"
                        />
                    </Tabs.Panel>
                </div>
            </Tabs>
      </div>
    </div>
  );
};

export default CATreePage;
