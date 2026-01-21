import { useState } from 'react';
import { DataTable } from '../../components/domain/DataTable';
import { CAHierarchy } from '../../components/domain/CAHierarchy';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getCAs } from '../../services/mockData';
import styles from './CAList.module.css';

/**
 * Certificate Authorities Page
 * 
 * Two view modes:
 * - List view (DataTable)
 * - Hierarchy view (CAHierarchy tree)
 */
export function CAList() {
  const [viewMode, setViewMode] = useState('hierarchy'); // 'list' or 'hierarchy'
  const cas = getCAs();

  const columns = [
    {
      key: 'name',
      label: 'CA Name',
      sortable: true,
      render: (row) => (
        <div className={styles.caName}>
          <Icon name={row.type === 'root' ? 'seal-check' : 'tree-structure'} gradient />
          <span>{row.name}</span>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'Type',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('ca-type', row.type)}>
          {row.type}
        </Badge>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('ca-status', row.status)}>
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'validUntil',
      label: 'Valid Until',
      sortable: true,
    },
    {
      key: 'certificates',
      label: 'Certificates',
      sortable: true,
      render: (row) => (
        <span style={{ color: 'var(--text-tertiary)' }}>
          {row.certificates}
        </span>
      ),
    },
  ];

  const filters = [
    {
      label: 'Type',
      options: ['All Types', 'Root', 'Intermediate'],
    },
    {
      label: 'Status',
      options: ['All Statuses', 'Active', 'Expired'],
    },
  ];

  const actions = [
    { label: 'Create CA', icon: 'ph ph-plus', variant: 'primary' },
    { label: 'Import CA', icon: 'ph ph-upload', variant: 'default' },
  ];

  return (
    <div className={styles.caList}>
      {/* Toolbar with view toggle */}
      <div className={styles.toolbar}>
        <SearchToolbar
          placeholder="Search certificate authorities..."
          filters={filters}
          actions={actions}
          onSearch={(query) => console.log('Search:', query)}
          onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
        />
        
        <div className={styles.viewToggle}>
          <Button
            variant={viewMode === 'list' ? 'primary' : 'default'}
            icon="ph ph-list"
            onClick={() => setViewMode('list')}
          >
            List
          </Button>
          <Button
            variant={viewMode === 'hierarchy' ? 'primary' : 'default'}
            icon="ph ph-tree-structure"
            onClick={() => setViewMode('hierarchy')}
          >
            Hierarchy
          </Button>
        </div>
      </div>

      {/* View mode content */}
      {viewMode === 'list' ? (
        <DataTable
          columns={columns}
          data={cas}
          onRowClick={(row) => console.log('CA clicked:', row)}
        />
      ) : (
        <CAHierarchy cas={cas} />
      )}
    </div>
  );
}

export default CAList;
