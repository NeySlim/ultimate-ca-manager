import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Group,
  Badge,
  Text,
  ActionIcon,
  TextInput,
  Menu,
  Pagination,
  Loader,
  Center
} from '@mantine/core';
import {
  Plus,
  CaretRight,
  CaretDown,
  ArrowElbowDownRight,
  ShieldCheck,
  Certificate,
  MagnifyingGlass,
  Download,
  CloudArrowUp,
  FileArchive,
  FileText,
  Upload
} from '@phosphor-icons/react';
import { PageHeader } from '../../../components/ui/Layout';
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
    if (expandedIds.includes(node.refid || node.id) && node.children) {
      flat = flat.concat(flattenTree(node.children, expandedIds, level + 1));
    }
  });
  return flat;
};

// Auto-detect hierarchy from flat list
const buildHierarchy = (cas) => {
    const map = {};
    const subjectMap = {};
    const roots = [];
    const orphans = [];
    
    // Index all CAs
    cas.forEach(ca => {
        map[ca.id] = { ...ca, children: [], refid: ca.id }; // Ensure refid exists
        if (ca.subject) {
            // Normalize subject for matching? (Removing spaces might help)
            subjectMap[ca.subject] = map[ca.id];
        }
    });

    // Build tree
    cas.forEach(ca => {
        const node = map[ca.id];
        
        // 1. Explicit Parent (DB Relationship)
        if (ca.parent_ca_id && map[ca.parent_ca_id]) {
            map[ca.parent_ca_id].children.push(node);
            return;
        } 
        
        // 2. Explicit Parent but missing in map -> Orphan
        if (ca.parent_ca_id && !map[ca.parent_ca_id]) {
            orphans.push(node);
            return;
        }
        
        // 3. No explicit parent. Check if Self-Signed (Root)
        // Check issuer/subject equality. 
        // Note: Imported CAs might have null issuer/subject if parsing failed, 
        // but typically backend parses them.
        const isSelfSigned = ca.subject && ca.issuer && ca.subject === ca.issuer;
        
        if (isSelfSigned) {
            roots.push(node);
            return;
        }
        
        // 4. Not Self-Signed, No Parent ID. Try to soft-link by Issuer DN
        if (ca.issuer && subjectMap[ca.issuer]) {
             subjectMap[ca.issuer].children.push(node);
             // Optionally mark as soft-linked?
             return;
        }

        // 5. Fallback: It's an intermediate with no known parent -> Orphan
        orphans.push(node);
    });

    return { hierarchy: roots, orphans };
};

const CATreePage = () => {
  const navigate = useNavigate();
  const { setSelectedItem, selectedItem } = useSelection();
  const [expanded, setExpanded] = useState([]); 
  const [treeData, setTreeData] = useState([]);
  const [orphansData, setOrphansData] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  
  // Sorting
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

  // Resizable Splitter
  const [splitRatio, setSplitRatio] = useState(0.7); // 70% top, 30% bottom
  const splitRef = useRef(null);
  const containerRef = useRef(null);
  const [isResizingSplit, setIsResizingSplit] = useState(false);

  // Pagination States
  const [orphanPage, setOrphanPage] = useState(1);
  const orphanPageSize = 5;

  // Fetch Data
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const allCAs = await caService.getAll();
        const { hierarchy, orphans } = buildHierarchy(allCAs);
        setTreeData(hierarchy);
        setOrphansData(orphans);
        
        // Expand all by default
        const getAllIds = (nodes) => nodes.reduce((acc, n) => [...acc, n.refid, ...(n.children ? getAllIds(n.children) : [])], []);
        setExpanded(getAllIds(hierarchy));
      } catch (error) {
        console.error("Failed to fetch CAs", error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  // Sorting Logic
  const handleSort = (key) => {
      let direction = 'asc';
      if (sortConfig.key === key && sortConfig.direction === 'asc') {
          direction = 'desc';
      }
      setSortConfig({ key, direction });
  };

  const sortData = (data) => {
      if (!sortConfig.key) return data;
      
      return [...data].sort((a, b) => {
          if (a[sortConfig.key] < b[sortConfig.key]) {
              return sortConfig.direction === 'asc' ? -1 : 1;
          }
          if (a[sortConfig.key] > b[sortConfig.key]) {
              return sortConfig.direction === 'asc' ? 1 : -1;
          }
          return 0;
      });
  };

  // Filtering
  const filterNodes = (nodes, query) => {
      if (!query) return nodes;
      return nodes.reduce((acc, node) => {
        const matches = node.name.toLowerCase().includes(query.toLowerCase());
        const filteredChildren = node.children ? filterNodes(node.children, query) : [];
        if (matches || filteredChildren.length > 0) {
            acc.push({ ...node, children: filteredChildren });
        }
        return acc;
      }, []);
  };

  const finalTreeData = useMemo(() => {
      let filtered = filterNodes(treeData, searchQuery);
      // Note: Sorting tree data is complex as it breaks hierarchy structure if not careful.
      // For now, we only sort siblings.
      const sortNodes = (nodes) => {
          if (!sortConfig.key) return nodes;
          const sorted = [...nodes].sort((a, b) => {
              // Custom sort for name to keep tree feel? No, standard sort.
              if (a[sortConfig.key] < b[sortConfig.key]) return sortConfig.direction === 'asc' ? -1 : 1;
              if (a[sortConfig.key] > b[sortConfig.key]) return sortConfig.direction === 'asc' ? 1 : -1;
              return 0;
          });
          return sorted.map(n => ({ ...n, children: sortNodes(n.children) }));
      };
      
      filtered = sortNodes(filtered);
      return flattenTree(filtered, expanded);
  }, [treeData, expanded, searchQuery, sortConfig]);

  const finalOrphansData = useMemo(() => {
      let filtered = orphansData;
      if (searchQuery) {
          filtered = orphansData.filter(o => o.name.toLowerCase().includes(searchQuery.toLowerCase()));
      }
      return sortData(filtered);
  }, [orphansData, searchQuery, sortConfig]);

  const paginatedOrphans = useMemo(() => {
      const start = (orphanPage - 1) * orphanPageSize;
      return finalOrphansData.slice(start, start + orphanPageSize);
  }, [finalOrphansData, orphanPage]);

  const orphanTotalPages = Math.ceil(finalOrphansData.length / orphanPageSize);

  const toggleExpand = (id) => {
    setExpanded(prev => 
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    );
  };

  const getBadgeColor = (type) => {
      // Use semantic color classes instead of Mantine color names
      switch(type) {
          case 'Root CA': return { className: 'badge-warning' }; // Yellow
          case 'Intermediate': return { className: 'badge-info' }; // Blue
          case 'Orphan': return { className: 'badge-error' }; // Orange/Red
          default: return { className: 'badge-neutral' }; // Gray
      }
  };

  // Splitter Logic
  const handleSplitMouseDown = (e) => {
      setIsResizingSplit(true);
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
  };

  const handleSplitMouseMove = useCallback((e) => {
      if (!isResizingSplit || !containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const relativeY = e.clientY - containerRect.top;
      const ratio = Math.max(0.2, Math.min(0.8, relativeY / containerRect.height));
      setSplitRatio(ratio);
  }, [isResizingSplit]);

  const handleSplitMouseUp = useCallback(() => {
      setIsResizingSplit(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
  }, []);

  useEffect(() => {
      if (isResizingSplit) {
          window.addEventListener('mousemove', handleSplitMouseMove);
          window.addEventListener('mouseup', handleSplitMouseUp);
      }
      return () => {
          window.removeEventListener('mousemove', handleSplitMouseMove);
          window.removeEventListener('mouseup', handleSplitMouseUp);
      };
  }, [isResizingSplit, handleSplitMouseMove, handleSplitMouseUp]);

  const columns = [
    {
      key: 'name',
      label: 'Authority Name',
      width: 350,
      minWidth: 200,
      sortable: true,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center', paddingLeft: row.level ? `calc(var(--control-height) * ${row.level})` : 0 }}>
          {/* Connector */}
          {row.level > 0 && (
            <ArrowElbowDownRight 
              size={14} 
              color="var(--text-tertiary)" 
              style={{ marginRight: 4, minWidth: 14 }} 
            />
          )}

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
            <span style={{ width: 22, display: 'inline-block' }} />
          )}

          {/* Icon */}
          {row.type === 'Root CA' ? 
            <ShieldCheck size={18} weight="fill" color="var(--status-warning)" style={{ marginRight: 8 }} /> : 
            <Certificate size={18} className="icon-gradient" style={{ marginRight: 8 }} />
          }
          
          <Text size="sm" fw={500} c="var(--text-primary)">{row.name}</Text>
        </div>
      )
    },
    {
      key: 'type',
      label: 'Type',
      width: 140,
      sortable: true,
      render: (row) => <Badge {...getBadgeColor(row.type)} variant="outline" size="sm">{row.type}</Badge>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      sortable: true,
      render: (row) => (
        <Badge 
          className={row.status === 'Active' ? 'badge-active' : 'badge-error'}
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'certs',
      label: 'Issued',
      width: 80,
      sortable: true,
      render: (row) => <Text size="sm" ta="center" c="var(--text-primary)">{row.certs || 0}</Text>
    },
    {
      key: 'expiry',
      label: 'Expires',
      minWidth: 120,
      flex: true,
      sortable: true,
      render: (row) => <Text size="sm" c="var(--text-secondary)">{row.expiry}</Text>
    }
  ];

  return (
    <div className="ca-tree-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Certificate Authorities" 
        actions={
          <Group spacing="xs">
             <Menu shadow="md" width={200}>
                <Menu.Target>
                  <Button variant="default" leftSection={<Upload size={16} />} size="xs">Import</Button>
                </Menu.Target>
                <Menu.Dropdown>
                   <Menu.Label>Import From</Menu.Label>
                   <Menu.Item leftSection={<CloudArrowUp size={14} />} onClick={() => navigate('/settings?tab=security')}>
                     OPNsense Config
                   </Menu.Item>
                   <Menu.Item leftSection={<FileArchive size={14} />}>
                     Backup File
                   </Menu.Item>
                </Menu.Dropdown>
             </Menu>
             <Menu shadow="md" width={200}>
                <Menu.Target>
                  <Button variant="default" leftSection={<Download size={16} />} size="xs">Export All</Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>Export Format</Menu.Label>
                  <Menu.Item leftSection={<FileArchive size={14} />}>JSON (Full Backup)</Menu.Item>
                  <Menu.Item leftSection={<FileText size={14} />}>CSV List</Menu.Item>
                </Menu.Dropdown>
             </Menu>
             <Button leftSection={<Plus size={16} />} size="xs" onClick={() => navigate('/cas/create')}>
                Create New CA
             </Button>
          </Group>
        }
      />

      {/* Toolbar */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-panel)', display: 'flex' }}>
        <TextInput 
            placeholder="Search CAs..." 
            size="xs"
            leftSection={<MagnifyingGlass size={16} className="icon-gradient-subtle" />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: 300 }}
        />
      </div>

      <div style={{ flex: 1, overflow: 'hidden', padding: '12px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', border: '1px solid var(--border-color)', borderRadius: 'var(--control-radius)', background: 'var(--bg-surface)', overflow: 'hidden' }}>
        {loading ? (
             <Center style={{ height: '100%' }}>
                <Loader size="sm" />
             </Center>
        ) : (
            <>
                {/* Hierarchy Section */}
                <div style={{ height: `${splitRatio * 100}%`, display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--border-color)', minHeight: '100px' }}>
                    <div style={{ padding: '8px 16px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text size="xs" fw={700} c="dimmed" tt="uppercase">Authority Hierarchy</Text>
                        <Badge size="xs" variant="outline" color="gray">{finalTreeData.length} items</Badge>
                    </div>
                    <ResizableTable 
                        columns={columns}
                        data={finalTreeData}
                        onRowClick={(row) => setSelectedItem({...row, type: 'CA', title: row.name, subtitle: row.status})}
                        onSort={handleSort}
                        sortConfig={sortConfig}
                        rowClassName={(row) => selectedItem?.id === row.id ? 'selected' : ''}
                        emptyMessage="No Certificate Authorities found"
                    />
                </div>

                {/* Resizer Handle */}
                <div 
                    onMouseDown={handleSplitMouseDown}
                    style={{ 
                        height: '6px', 
                        background: isResizingSplit ? 'var(--mantine-color-blue-filled)' : 'var(--bg-app)', 
                        cursor: 'row-resize',
                        zIndex: 10,
                        margin: '-3px 0',
                        position: 'relative',
                        borderTop: '1px solid var(--border-color)',
                        borderBottom: '1px solid var(--border-color)'
                    }} 
                />

                {/* Orphans Section */}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: '100px' }}>
                    <div style={{ padding: '8px 16px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                         <Text size="xs" fw={700} c="dimmed" tt="uppercase">Orphan Intermediates</Text>
                         <Badge size="xs" variant="outline" color="orange">{paginatedOrphans.length} orphans</Badge>
                    </div>
                    <ResizableTable 
                        columns={columns}
                        data={paginatedOrphans}
                        onRowClick={(row) => setSelectedItem({...row, type: 'CA', title: row.name, subtitle: 'Orphan Intermediate'})}
                        onSort={handleSort}
                        sortConfig={sortConfig}
                        rowClassName={(row) => selectedItem?.id === row.id ? 'selected' : ''}
                        emptyMessage="No orphan intermediates found"
                    />
                    {orphanTotalPages > 1 && (
                        <div style={{ padding: '4px 8px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
                            <Pagination total={orphanTotalPages} value={orphanPage} onChange={setOrphanPage} size="xs" />
                        </div>
                    )}
                </div>
            </>
        )}
        </div>
      </div>
    </div>
  );
};

export default CATreePage;
