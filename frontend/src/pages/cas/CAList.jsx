import { useState } from 'react';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { PageTopBar } from '../../components/common';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { useCAs, useDeleteCA } from '../../hooks/useCAs';
import toast from 'react-hot-toast';
import styles from './CAList.module.css';

export function CAList() {
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('name');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCAs, setExpandedCAs] = useState(new Set());

  const { data: casResponse, isLoading, error } = useCAs();
  const deleteCA = useDeleteCA();

  const handleDelete = (ca) => {
    if (confirm(`Delete CA "${ca.name}"? This cannot be undone.`)) {
      deleteCA.mutate(ca.id, {
        onSuccess: () => toast.success('CA deleted'),
        onError: () => toast.error('Failed to delete CA')
      });
    }
  };

  const toggleCA = (caId) => {
    const newExpanded = new Set(expandedCAs);
    if (newExpanded.has(caId)) {
      newExpanded.delete(caId);
    } else {
      newExpanded.add(caId);
    }
    setExpandedCAs(newExpanded);
  };

  if (isLoading) {
    return (
      <div className={styles.caList}>
        <PageTopBar
          icon="ph ph-bank"
          title="Certificate Authorities"
          badge={<Badge variant="neutral">Loading...</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading CAs...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.caList}>
        <PageTopBar
          icon="ph ph-bank"
          title="Certificate Authorities"
          badge={<Badge variant="danger">Error</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading CAs: {error.message}
        </div>
      </div>
    );
  }

  const MOCK_CAS = casResponse?.data || [];
  const ORPHANED_CAS = [];

  const activeCount = MOCK_CAS.filter(ca => ca.status === 'ACTIVE').length;

  return (
    <div className={styles.caList}>
      {/* Page Header */}
      <PageTopBar
        icon="ph ph-bank"
        title="Certificate Authorities"
        badge={<Badge variant="success">{activeCount} Active</Badge>}
        actions={
          <>
            <Button icon="ph ph-upload-simple">Import</Button>
            <Button icon="ph ph-download-simple">Export</Button>
            <Button variant="primary" icon="ph ph-plus">Create CA</Button>
          </>
        }
      />

      {/* Filters Section */}
      <div className={styles.filtersSection}>
        <div className={styles.filterGroup}>
          <label htmlFor="type-filter">TYPE</label>
          <select 
            id="type-filter" 
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="all">All Types</option>
            <option value="root">Root</option>
            <option value="intermediate">Intermediate</option>
          </select>
        </div>
        <div className={styles.filterGroup}>
          <label htmlFor="status-filter">STATUS</label>
          <select 
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="expired">Expired</option>
          </select>
        </div>
        <div className={styles.filterGroup}>
          <label htmlFor="sort-filter">SORT BY</label>
          <select 
            id="sort-filter"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="name">Name</option>
            <option value="issued">Issued Date</option>
            <option value="expires">Expires Date</option>
          </select>
        </div>
        <div style={{ flex: 1 }}></div>
        <div className={styles.filterGroup}>
          <input 
            type="text" 
            id="search-filter" 
            placeholder="Search CAs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Main Table */}
      <div className={styles.tableContainer}>
        <table>
          <thead>
            <tr>
              <th style={{ width: '35%' }}>NAME</th>
              <th style={{ width: '15%' }}>TYPE</th>
              <th style={{ width: '12%' }}>STATUS</th>
              <th style={{ width: '12%' }}>ISSUED</th>
              <th style={{ width: '12%' }}>EXPIRES</th>
              <th style={{ width: '8%' }}>CERTS</th>
              <th style={{ width: '6%' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_CAS.map((ca) => (
              <>
                {/* Root CA Row */}
                <tr key={ca.id}>
                  <td>
                    <div className={styles.caNameCell}>
                      <button
                        className={`${styles.caExpandBtn} ${
                          ca.children ? '' : styles.noChildren
                        } ${expandedCAs.has(ca.id) ? '' : styles.collapsed}`}
                        onClick={() => ca.children && toggleCA(ca.id)}
                      >
                        <i className="ph ph-caret-down"></i>
                      </button>
                      <i className={`ph ph-bank ${styles.caIcon} ${styles.root}`}></i>
                      <span>{ca.name}</span>
                    </div>
                  </td>
                  <td><span>{ca.type}</span></td>
                  <td>
                    <span className={`${styles.statusBadge} ${ca.status.toLowerCase()}`}>
                      {ca.status}
                    </span>
                  </td>
                  <td>{ca.issued}</td>
                  <td>{ca.expires}</td>
                  <td>{ca.certs}</td>
                  <td>
                    <div className={styles.actionsCell}>
                      <button className={styles.actionBtn} title="View">
                        <i className="ph ph-eye"></i>
                      </button>
                      <button 
                        className={styles.actionBtn} 
                        title="Delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(ca);
                        }}
                      >
                        <i className="ph ph-trash"></i>
                      </button>
                    </div>
                  </td>
                </tr>

                {/* Children CA Rows */}
                {ca.children && expandedCAs.has(ca.id) && ca.children.map((child) => (
                  <tr key={child.id}>
                    <td>
                      <div className={styles.caTreeIndent}>
                        <i className={`ph ph-git-branch ${styles.caIcon} ${styles.intermediate}`}></i>
                        <span>{child.name}</span>
                      </div>
                    </td>
                    <td><span>{child.type}</span></td>
                    <td>
                      <span className={`${styles.statusBadge} ${child.status.toLowerCase()}`}>
                        {child.status}
                      </span>
                    </td>
                    <td>{child.issued}</td>
                    <td>{child.expires}</td>
                    <td>{child.certs}</td>
                    <td>
                      <div className={styles.actionsCell}>
                        <button className={styles.actionBtn} title="View">
                          <i className="ph ph-eye"></i>
                        </button>
                        <button 
                          className={styles.actionBtn} 
                          title="Delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(child);
                          }}
                        >
                          <i className="ph ph-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Orphaned Section */}
      {ORPHANED_CAS.length > 0 && (
        <div className={styles.orphanedSection}>
          <div className={styles.orphanedHeader}>
            <i className="ph ph-warning"></i>
            <span className={styles.orphanedHeaderText}>Orphaned Intermediate CAs</span>
          </div>
          <div className={styles.orphanedTable}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: '35%' }}>NAME</th>
                  <th style={{ width: '15%' }}>TYPE</th>
                  <th style={{ width: '12%' }}>STATUS</th>
                  <th style={{ width: '12%' }}>ISSUED</th>
                  <th style={{ width: '12%' }}>EXPIRES</th>
                  <th style={{ width: '8%' }}>CERTS</th>
                  <th style={{ width: '6%' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {ORPHANED_CAS.map((ca) => (
                  <tr key={ca.id}>
                    <td>
                      <div className={styles.caNameCell}>
                        <i className={`ph ph-warning ${styles.caIcon} ${styles.orphan}`}></i>
                        <span>{ca.name}</span>
                      </div>
                    </td>
                    <td><span>{ca.type}</span></td>
                    <td>
                      <span className={`${styles.statusBadge} ${ca.status.toLowerCase()}`}>
                        {ca.status}
                      </span>
                    </td>
                    <td>{ca.issued}</td>
                    <td>{ca.expires}</td>
                    <td>{ca.certs}</td>
                    <td>
                      <div className={styles.actionsCell}>
                        <button className={styles.actionBtn} title="View">
                          <i className="ph ph-eye"></i>
                        </button>
                        <button 
                          className={styles.actionBtn} 
                          title="Delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(ca);
                          }}
                        >
                          <i className="ph ph-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default CAList;
