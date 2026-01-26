import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  Tree,
  Plus,
  MagnifyingGlass,
  Funnel,
  CaretRight,
  CaretDown,
  Certificate,
  Key,
  Download,
  Trash,
  Eye,
  CircleNotch
} from '@phosphor-icons/react';

// Design System V3
import { Card } from '../../design-system/components/primitives/Card';
import { GlassCard } from '../../design-system/components/primitives/GlassCard';
import { Button } from '../../design-system/components/primitives/Button';
import { Input } from '../../design-system/components/primitives/Input';
import { Select } from '../../design-system/components/primitives/Select';
import { Badge } from '../../design-system/components/primitives/Badge';
import { GradientBadge } from '../../design-system/components/primitives/GradientBadge';
import { Grid } from '../../design-system/components/layout/Grid';
import { Stack } from '../../design-system/components/layout/Stack';
import { Inline } from '../../design-system/components/layout/Inline';
import { EmptyState } from '../../design-system/components/feedback/EmptyState';
import { Skeleton } from '../../design-system/components/feedback/Skeleton';
import { Dropdown } from '../../design-system/components/overlays/Dropdown';

import { useCAs } from '../../hooks/useCAs';
import styles from './CAListV3.module.css';

// CA Tree Node Component
function CATreeNode({ ca, level = 0, onExpand, expanded, onSelect }) {
  const hasChildren = ca.children && ca.children.length > 0;
  const isExpanded = expanded.has(ca.id);

  const handleToggle = (e) => {
    e.stopPropagation();
    onExpand(ca.id);
  };

  const typeColors = {
    root: 'success',
    intermediate: 'info',
    issuing: 'primary'
  };

  return (
    <div className={styles.treeNode} style={{ '--level': level }}>
      <Card 
        hoverable 
        className={styles.caCard}
        onClick={() => onSelect?.(ca)}
      >
        <div className={styles.caCardContent}>
          {/* Expand/Collapse Button */}
          <button
            className={styles.expandButton}
            onClick={handleToggle}
            disabled={!hasChildren}
          >
            {hasChildren ? (
              isExpanded ? <CaretDown size={16} weight="bold" /> : <CaretRight size={16} weight="bold" />
            ) : (
              <div style={{ width: '16px' }} />
            )}
          </button>

          {/* CA Icon */}
          <div className={styles.caIcon}>
            <ShieldCheck size={24} weight="duotone" />
          </div>

          {/* CA Info */}
          <div className={styles.caInfo}>
            <div className={styles.caName}>{ca.common_name || ca.name}</div>
            <div className={styles.caMeta}>
              <GradientBadge variant={typeColors[ca.type] || 'primary'} size="sm">
                {ca.type}
              </GradientBadge>
              <span>•</span>
              <span>{ca.serial_number?.substring(0, 16)}...</span>
              {ca.expires_in && (
                <>
                  <span>•</span>
                  <Badge variant={ca.expires_in_days < 30 ? 'warning' : 'default'} size="sm">
                    {ca.expires_in}
                  </Badge>
                </>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className={styles.caActions} onClick={(e) => e.stopPropagation()}>
            <Dropdown
              items={[
                { label: 'View Details', icon: <Eye size={16} />, onClick: () => onSelect?.(ca) },
                { label: 'Export Certificate', icon: <Download size={16} />, onClick: () => {} },
                { label: 'Export Private Key', icon: <Key size={16} />, onClick: () => {} },
                { type: 'divider' },
                { label: 'Delete', icon: <Trash size={16} />, onClick: () => {}, variant: 'danger' },
              ]}
            >
              <Button variant="ghost" size="sm">•••</Button>
            </Dropdown>
          </div>
        </div>
      </Card>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div className={styles.treeChildren}>
          {ca.children.map((child) => (
            <CATreeNode
              key={child.id}
              ca={child}
              level={level + 1}
              onExpand={onExpand}
              expanded={expanded}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// CA Grid Card (alternative view)
function CAGridCard({ ca, onSelect }) {
  const typeColors = {
    root: 'success',
    intermediate: 'info',
    issuing: 'primary'
  };

  return (
    <Card hoverable className={styles.gridCard} onClick={() => onSelect?.(ca)}>
      <Stack gap="md">
        <div className={styles.gridCardHeader}>
          <div className={styles.gridCardIcon} style={{ 
            background: `linear-gradient(135deg, var(--color-${typeColors[ca.type]}-500) 0%, var(--color-${typeColors[ca.type]}-600) 100%)`
          }}>
            <ShieldCheck size={32} weight="bold" color="white" />
          </div>
          <Dropdown
            items={[
              { label: 'View Details', icon: <Eye size={16} />, onClick: () => onSelect?.(ca) },
              { label: 'Export', icon: <Download size={16} />, onClick: () => {} },
              { type: 'divider' },
              { label: 'Delete', icon: <Trash size={16} />, onClick: () => {}, variant: 'danger' },
            ]}
          >
            <Button variant="ghost" size="sm">•••</Button>
          </Dropdown>
        </div>

        <div>
          <div className={styles.gridCardTitle}>{ca.common_name || ca.name}</div>
          <div className={styles.gridCardSubtitle}>{ca.organization || 'No Organization'}</div>
        </div>

        <Inline gap="xs" wrap>
          <GradientBadge variant={typeColors[ca.type]} size="sm">
            {ca.type}
          </GradientBadge>
          {ca.expires_in && (
            <Badge variant={ca.expires_in_days < 30 ? 'warning' : 'default'} size="sm">
              {ca.expires_in}
            </Badge>
          )}
        </Inline>

        <div className={styles.gridCardFooter}>
          <div className={styles.gridCardStat}>
            <Certificate size={16} />
            <span>{ca.issued_certificates || 0} certs</span>
          </div>
          <div className={styles.gridCardStat}>
            <Tree size={16} />
            <span>{ca.children?.length || 0} children</span>
          </div>
        </div>
      </Stack>
    </Card>
  );
}

export function CAListV3() {
  const navigate = useNavigate();
  const { data: cas, isLoading, error } = useCAs();

  const [viewMode, setViewMode] = useState('tree'); // 'tree' or 'grid'
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('name');
  const [expanded, setExpanded] = useState(new Set());
  const [selectedCA, setSelectedCA] = useState(null);

  const handleExpand = (id) => {
    const newExpanded = new Set(expanded);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpanded(newExpanded);
  };

  const handleExpandAll = () => {
    const allIds = new Set();
    const collectIds = (items) => {
      items?.forEach(item => {
        allIds.add(item.id);
        if (item.children) collectIds(item.children);
      });
    };
    collectIds(cas);
    setExpanded(allIds);
  };

  const handleCollapseAll = () => {
    setExpanded(new Set());
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    setTypeFilter('all');
    setStatusFilter('all');
    setSortBy('name');
  };

  // Filter logic
  const filteredCAs = cas?.filter(ca => {
    if (searchQuery && !ca.common_name?.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    if (typeFilter !== 'all' && ca.type !== typeFilter) {
      return false;
    }
    if (statusFilter !== 'all') {
      if (statusFilter === 'active' && ca.status !== 'active') return false;
      if (statusFilter === 'expired' && ca.status !== 'expired') return false;
    }
    return true;
  });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <Stack gap="xl">
          <Skeleton height="60px" />
          <Skeleton height="120px" />
          <Stack gap="sm">
            {[...Array(5)].map((_, i) => <Skeleton key={i} height="80px" />)}
          </Stack>
        </Stack>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <EmptyState
          icon={<ShieldCheck size={64} />}
          title="Error loading CAs"
          description={error.message}
        />
      </div>
    );
  }

  const hasFilters = searchQuery || typeFilter !== 'all' || statusFilter !== 'all';

  return (
    <div className={styles.container}>
      <Stack gap="xl">
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Certificate Authorities</h1>
            <p className={styles.subtitle}>Manage your CA hierarchy</p>
          </div>
          <Button 
            variant="primary" 
            leftIcon={<Plus size={20} weight="bold" />}
            onClick={() => navigate('/cas/new')}
          >
            Create CA
          </Button>
        </div>

        {/* Filters Bar */}
        <GlassCard blur="md">
          <div className={styles.filtersBar}>
            <div className={styles.filtersLeft}>
              <Input
                placeholder="Search CAs..."
                leftIcon={<MagnifyingGlass size={18} />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ width: '300px' }}
              />
              
              <Select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                style={{ width: '150px' }}
              >
                <option value="all">All Types</option>
                <option value="root">Root CA</option>
                <option value="intermediate">Intermediate</option>
                <option value="issuing">Issuing CA</option>
              </Select>

              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                style={{ width: '150px' }}
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="expired">Expired</option>
              </Select>

              <Select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                style={{ width: '150px' }}
              >
                <option value="name">Sort by Name</option>
                <option value="date">Sort by Date</option>
                <option value="expiry">Sort by Expiry</option>
              </Select>
            </div>

            <div className={styles.filtersRight}>
              {hasFilters && (
                <Button variant="ghost" size="sm" onClick={handleClearFilters}>
                  Clear Filters
                </Button>
              )}
              
              <div className={styles.viewToggle}>
                <Button
                  variant={viewMode === 'tree' ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => setViewMode('tree')}
                >
                  <Tree size={18} />
                </Button>
                <Button
                  variant={viewMode === 'grid' ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => setViewMode('grid')}
                >
                  Grid
                </Button>
              </div>

              {viewMode === 'tree' && (
                <Inline gap="xs">
                  <Button variant="ghost" size="sm" onClick={handleExpandAll}>
                    Expand All
                  </Button>
                  <Button variant="ghost" size="sm" onClick={handleCollapseAll}>
                    Collapse All
                  </Button>
                </Inline>
              )}
            </div>
          </div>
        </GlassCard>

        {/* Content */}
        {!filteredCAs || filteredCAs.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck size={64} />}
            title={hasFilters ? "No CAs match your filters" : "No Certificate Authorities"}
            description={hasFilters ? "Try adjusting your filters" : "Create your first CA to get started"}
            action={!hasFilters && (
              <Button variant="primary" leftIcon={<Plus size={20} />} onClick={() => navigate('/cas/new')}>
                Create CA
              </Button>
            )}
          />
        ) : (
          viewMode === 'tree' ? (
            <div className={styles.treeView}>
              {filteredCAs.map((ca) => (
                <CATreeNode
                  key={ca.id}
                  ca={ca}
                  level={0}
                  onExpand={handleExpand}
                  expanded={expanded}
                  onSelect={setSelectedCA}
                />
              ))}
            </div>
          ) : (
            <Grid cols={3} gap="lg">
              {filteredCAs.map((ca) => (
                <CAGridCard key={ca.id} ca={ca} onSelect={setSelectedCA} />
              ))}
            </Grid>
          )
        )}
      </Stack>
    </div>
  );
}

export default CAListV3;
