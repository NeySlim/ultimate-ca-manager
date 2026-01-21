import { useState } from 'react';
import styles from './CSRList.module.css';

// Mock CSR Data
const MOCK_PENDING = [
  {
    id: 1,
    cn: 'CN=api.newservice.com',
    email: 'admin@acme.com',
    key: 'RSA 2048',
    requested: 'Mar 15',
    requestedAgo: '2 hours ago',
    priority: 'HIGH',
  },
  {
    id: 2,
    cn: 'CN=mail.internal.net',
    email: 'jane.smith@acme.com',
    key: 'RSA 4096',
    requested: 'Mar 15',
    requestedAgo: '5 hours ago',
    priority: 'HIGH',
  },
  {
    id: 3,
    cn: 'CN=vpn.acme.com',
    email: 'robert.wilson@acme.com',
    key: 'RSA 2048',
    requested: 'Mar 14',
    requestedAgo: '1 day ago',
    priority: 'NORMAL',
  },
  {
    id: 4,
    cn: 'CN=ldap.corp.local',
    email: 'alice.brown@acme.com',
    key: 'RSA 4096',
    requested: 'Mar 13',
    requestedAgo: '2 days ago',
    priority: 'NORMAL',
  },
  {
    id: 5,
    cn: 'CN=monitoring.local',
    email: 'bob.jones@acme.com',
    key: 'RSA 2048',
    requested: 'Mar 12',
    requestedAgo: '3 days ago',
    priority: 'NORMAL',
  },
  {
    id: 6,
    cn: 'CN=backup.internal',
    email: 'emma.davis@acme.com',
    key: 'ECDSA P-256',
    requested: 'Mar 11',
    requestedAgo: '4 days ago',
    priority: 'NORMAL',
  },
  {
    id: 7,
    cn: 'CN=test.dev.local',
    email: 'michael.lee@acme.com',
    key: 'RSA 2048',
    requested: 'Mar 10',
    requestedAgo: '5 days ago',
    priority: 'LOW',
  },
  {
    id: 8,
    cn: 'CN=admin.acme.com',
    email: 'sarah.white@acme.com',
    key: 'RSA 4096',
    requested: 'Mar 8',
    requestedAgo: '1 week ago',
    priority: 'LOW',
  },
];

const MOCK_APPROVED = [
  {
    id: 1,
    cn: 'CN=netsuit.lan.pew.pet',
    email: 'admin@acme.com',
    key: 'RSA 4096',
    approved: 'Mar 14',
    approvedBy: 'admin',
    certificateId: '#2847',
  },
  {
    id: 2,
    cn: 'CN=git.internal.net',
    email: 'dev.team@acme.com',
    key: 'RSA 2048',
    approved: 'Mar 14',
    approvedBy: 'admin',
    certificateId: '#2846',
  },
  {
    id: 3,
    cn: 'CN=jenkins.local',
    email: 'ci.cd@acme.com',
    key: 'RSA 2048',
    approved: 'Mar 13',
    approvedBy: 'admin',
    certificateId: '#2845',
  },
  {
    id: 4,
    cn: 'CN=db.internal',
    email: 'dba.team@acme.com',
    key: 'RSA 4096',
    approved: 'Mar 13',
    approvedBy: 'security.team',
    certificateId: '#2844',
  },
];

const MOCK_REJECTED = [
  {
    id: 1,
    cn: 'CN=suspicious.domain.com',
    email: 'unknown@example.com',
    key: 'RSA 2048',
    rejected: 'Mar 10',
    rejectedBy: 'security.team',
    reason: 'Unauthorized domain',
  },
];

export function CSRList() {
  const getPriorityClass = (priority) => {
    if (priority === 'HIGH') return styles.badgeHigh;
    if (priority === 'NORMAL') return styles.badgeNormal;
    return styles.badgeLow;
  };

  return (
    <div className={styles.csrList}>
      {/* Page Header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>
          <i className="ph ph-file-text"></i>
          Certificate Signing Requests
          <span className={styles.badgeTopbar}>{MOCK_PENDING.length} Pending</span>
        </div>
        <div className={styles.pageActions}>
          <button className={styles.btn}>
            <i className="ph ph-upload-simple"></i>
            Import CSR
          </button>
          <button className={styles.btn}>
            <i className="ph ph-download-simple"></i>
            Export
          </button>
          <button className={`${styles.btn} ${styles.btnPrimary}`}>
            <i className="ph ph-file-plus"></i>
            Create CSR
          </button>
        </div>
      </div>

      {/* Pending Approval Section */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionIconWarning}>
            <i className="ph ph-clock"></i>
          </div>
          <span className={styles.sectionTitle}>Pending Approval</span>
        </div>

        <div className={styles.tableContainer}>
          <table>
            <thead>
              <tr>
                <th style={{ width: '30%' }}>SUBJECT</th>
                <th style={{ width: '15%' }}>KEY</th>
                <th style={{ width: '15%' }}>REQUESTED</th>
                <th style={{ width: '15%' }}>PRIORITY</th>
                <th style={{ width: '25%' }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_PENDING.map((csr) => (
                <tr key={csr.id}>
                  <td>
                    <div className={styles.subjectCell}>
                      <span className={styles.cn}>{csr.cn}</span>
                      <span className={styles.email}>{csr.email}</span>
                    </div>
                  </td>
                  <td>{csr.key}</td>
                  <td>
                    <div className={styles.requestedCell}>
                      <span className={styles.date}>{csr.requested}</span>
                      <span className={styles.ago}>{csr.requestedAgo}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`${styles.priorityBadge} ${getPriorityClass(csr.priority)}`}>
                      {csr.priority}
                    </span>
                  </td>
                  <td>
                    <div className={styles.actionsCell}>
                      <button className={`${styles.actionBtn} ${styles.btnApprove}`}>
                        Approve
                      </button>
                      <button className={`${styles.actionBtn} ${styles.btnReject}`}>
                        Reject
                      </button>
                      <button className={styles.actionBtn}>
                        Details
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recently Approved Section */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionIconSuccess}>
            <i className="ph ph-check-circle"></i>
          </div>
          <span className={styles.sectionTitle}>Recently Approved</span>
        </div>

        <div className={styles.tableContainer}>
          <table>
            <thead>
              <tr>
                <th style={{ width: '30%' }}>SUBJECT</th>
                <th style={{ width: '15%' }}>KEY</th>
                <th style={{ width: '15%' }}>APPROVED</th>
                <th style={{ width: '15%' }}>CERTIFICATE</th>
                <th style={{ width: '25%' }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_APPROVED.map((csr) => (
                <tr key={csr.id}>
                  <td>
                    <div className={styles.subjectCell}>
                      <span className={styles.cn}>{csr.cn}</span>
                      <span className={styles.email}>{csr.email}</span>
                    </div>
                  </td>
                  <td>{csr.key}</td>
                  <td>
                    <div className={styles.approvedCell}>
                      <span className={styles.date}>{csr.approved}</span>
                      <span className={styles.by}>by {csr.approvedBy}</span>
                    </div>
                  </td>
                  <td>
                    <a href="#" className={styles.certificateLink}>{csr.certificateId}</a>
                  </td>
                  <td>
                    <div className={styles.actionsCell}>
                      <button className={styles.actionBtn}>
                        View
                      </button>
                      <button className={styles.actionBtn}>
                        Download
                      </button>
                      <button className={styles.actionBtn}>
                        Details
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Rejected Section */}
      {MOCK_REJECTED.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionIconError}>
              <i className="ph ph-x-circle"></i>
            </div>
            <span className={styles.sectionTitle}>Rejected</span>
          </div>

          <div className={styles.tableContainer}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>SUBJECT</th>
                  <th style={{ width: '15%' }}>KEY</th>
                  <th style={{ width: '15%' }}>REJECTED</th>
                  <th style={{ width: '20%' }}>REASON</th>
                  <th style={{ width: '20%' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_REJECTED.map((csr) => (
                  <tr key={csr.id}>
                    <td>
                      <div className={styles.subjectCell}>
                        <span className={styles.cn}>{csr.cn}</span>
                        <span className={styles.email}>{csr.email}</span>
                      </div>
                    </td>
                    <td>{csr.key}</td>
                    <td>
                      <div className={styles.approvedCell}>
                        <span className={styles.date}>{csr.rejected}</span>
                        <span className={styles.by}>by {csr.rejectedBy}</span>
                      </div>
                    </td>
                    <td>
                      <span className={styles.reason}>{csr.reason}</span>
                    </td>
                    <td>
                      <div className={styles.actionsCell}>
                        <button className={styles.actionBtn}>
                          Details
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

export default CSRList;
