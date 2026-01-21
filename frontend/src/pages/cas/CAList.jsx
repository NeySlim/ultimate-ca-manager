import { useState } from 'react';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import styles from './CAList.module.css';

// Mock CAs data matching prototype
const MOCK_CAS = [
  {
    id: 'root-1',
    name: 'Enterprise Root CA',
    type: 'Root',
    status: 'ACTIVE',
    issued: '2020-01-15',
    expires: '2040-01-15',
    certs: 2,
    children: [
      {
        id: 'int-1',
        name: 'Server CA',
        type: 'Intermediate',
        status: 'ACTIVE',
        issued: '2022-03-10',
        expires: '2032-03-10',
        certs: 145,
      },
      {
        id: 'int-2',
        name: 'Client CA',
        type: 'Intermediate',
        status: 'ACTIVE',
        issued: '2022-06-20',
        expires: '2032-06-20',
        certs: 312,
      },
    ],
  },
  {
    id: 'root-2',
    name: 'Dev Root CA',
    type: 'Root',
    status: 'ACTIVE',
    issued: '2021-05-01',
    expires: '2041-05-01',
    certs: 1,
    children: [
      {
        id: 'int-3',
        name: 'ACME CA',
        type: 'Intermediate',
        status: 'ACTIVE',
        issued: '2023-02-14',
        expires: '2033-02-14',
        certs: 89,
      },
    ],
  },
  {
    id: 'root-3',
    name: 'VPN Root CA',
    type: 'Root',
    status: 'ACTIVE',
    issued: '2019-07-20',
    expires: '2039-07-20',
    certs: 0,
  },
  {
    id: 'root-4',
    name: 'Mobile Device CA',
    type: 'Root',
    status: 'ACTIVE',
    issued: '2021-11-10',
    expires: '2041-11-10',
    certs: 0,
  },
  {
    id: 'root-5',
    name: 'Legacy Root CA',
    type: 'Root',
    status: 'EXPIRED',
    issued: '2015-03-01',
    expires: '2023-03-01',
    certs: 0,
  },
];

const ORPHANED_CAS = [
  {
    id: 'orphan-1',
    name: 'Orphaned Test CA',
    type: 'Intermediate',
    status: 'ACTIVE',
    issued: '2023-08-12',
    expires: '2033-08-12',
    certs: 23,
  },
];

export function CAList() {
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('name');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCAs, setExpandedCAs] = useState(new Set(['root-1', 'root-2']));

  const toggleCA = (caId) => {
    const newExpanded = new Set(expandedCAs);
    if (newExpanded.has(caId)) {
      newExpanded.delete(caId);
    } else {
      newExpanded.add(caId);
    }
    setExpandedCAs(newExpanded);
  };

  const activeCount = MOCK_CAS.filter(ca => ca.status === 'ACTIVE').length;

  return (
    <div className={styles.caList}>
      {/* Page Header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>
          <i className="ph ph-bank"></i>
          Certificate Authorities
          <span className={styles.badgeTopbar}>{activeCount} Active</span>
        </div>
        <div className={styles.pageActions}>
          <button className={styles.btn}>
            <i className="ph ph-upload-simple"></i>
            Import
          </button>
          <button className={styles.btn}>
            <i className="ph ph-download-simple"></i>
            Export
          </button>
          <button className={`${styles.btn} ${styles.btnPrimary}`}>
            <i className="ph ph-plus"></i>
            Create CA
          </button>
        </div>
      </div>

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
