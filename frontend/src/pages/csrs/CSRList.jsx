import { useState } from 'react';
import { PageTopBar } from '../../components/common';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { useCSRs } from '../../hooks/useCSRs';
import { exportTableData } from '../../utils/export';
import { CreateCSRModal } from '../../components/modals/CreateCSRModal';
import { ImportCSRModal } from '../../components/modals/ImportCSRModal';
import toast from 'react-hot-toast';
import styles from './CSRList.module.css';

export function CSRList() {
  const { data: csrsResponse, isLoading, error } = useCSRs();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);

  const handleExport = () => {
    const csrs = csrsResponse?.data || [];
    if (csrs.length === 0) {
      toast.error('No data to export');
      return;
    }
    exportTableData(csrs, 'csrs-export', {
      format: 'csv',
      columns: ['id', 'commonName', 'requestedBy', 'status', 'priority', 'createdAt']
    });
    toast.success('CSRs exported successfully');
  };

  const getPriorityClass = (priority) => {
    if (priority === 'HIGH') return styles.badgeHigh;
    if (priority === 'NORMAL') return styles.badgeNormal;
    return styles.badgeLow;
  };

  if (isLoading) {
    return (
      <div className={styles.csrList}>
        <PageTopBar
          icon="ph ph-file-text"
          title="Certificate Signing Requests"
          badge={<Badge variant="neutral">Loading...</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading CSRs...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.csrList}>
        <PageTopBar
          icon="ph ph-file-text"
          title="Certificate Signing Requests"
          badge={<Badge variant="danger">Error</Badge>}
        />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading CSRs: {error.message}
        </div>
      </div>
    );
  }

  const allCSRs = csrsResponse?.data || [];
  const MOCK_PENDING = allCSRs.filter(csr => csr.status === 'PENDING');
  const MOCK_APPROVED = allCSRs.filter(csr => csr.status === 'APPROVED');
  const MOCK_REJECTED = allCSRs.filter(csr => csr.status === 'REJECTED');

  return (
    <div className={styles.csrList}>
      {/* Page Header */}
      <PageTopBar
        icon="ph ph-file-text"
        title="Certificate Signing Requests"
        badge={<Badge variant="warning">{MOCK_PENDING.length} Pending</Badge>}
        actions={
          <>
            <Button icon="ph ph-upload-simple" onClick={() => setShowImportModal(true)}>Import CSR</Button>
            <Button icon="ph ph-download-simple" onClick={handleExport}>Export</Button>
            <Button variant="primary" icon="ph ph-file-plus" onClick={() => setShowCreateModal(true)}>Create CSR</Button>
          </>
        }
      />

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
      
      <CreateCSRModal 
        isOpen={showCreateModal} 
        onClose={() => setShowCreateModal(false)} 
      />
      
      <ImportCSRModal 
        isOpen={showImportModal} 
        onClose={() => setShowImportModal(false)} 
      />
    </div>
  );
}

export default CSRList;
