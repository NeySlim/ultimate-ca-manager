import { useState } from 'react';
import { PageTopBar } from '../../components/common';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { CreateTemplateModal } from '../../components/modals/CreateTemplateModal';
import { useTemplates, useDeleteTemplate } from '../../hooks/useTemplates';
import { exportTableData } from '../../utils/export';
import toast from 'react-hot-toast';
import styles from './TemplateList.module.css';

// Mock Templates Data
const MOCK_TEMPLATES = [
  {
    id: 1,
    name: 'Server Certificate',
    keyUsage: 'Digital Signature, Key Encipherment',
    validity: '1 year',
    subjectPattern: 'CN={hostname}, O=Company',
    usedBy: '142 certs',
    status: 'ACTIVE',
  },
  {
    id: 2,
    name: 'Client Authentication',
    keyUsage: 'Digital Signature, Non Repudiation',
    validity: '2 years',
    subjectPattern: 'CN={username}, OU=Users',
    usedBy: '87 certs',
    status: 'ACTIVE',
  },
  {
    id: 3,
    name: 'Code Signing',
    keyUsage: 'Digital Signature',
    validity: '3 years',
    subjectPattern: 'CN={developer}, O=Company',
    usedBy: '12 certs',
    status: 'ACTIVE',
  },
  {
    id: 4,
    name: 'Email Protection',
    keyUsage: 'Digital Signature, Key Encipherment',
    validity: '1 year',
    subjectPattern: 'CN={email}, OU=Email',
    usedBy: '234 certs',
    status: 'ACTIVE',
  },
  {
    id: 5,
    name: 'Wildcard SSL',
    keyUsage: 'Digital Signature, Key Encipherment',
    validity: '90 days',
    subjectPattern: 'CN=*.{domain}',
    usedBy: '45 certs',
    status: 'ACTIVE',
  },
  {
    id: 6,
    name: 'VPN Gateway',
    keyUsage: 'Digital Signature, Key Encipherment, TLS Server',
    validity: '2 years',
    subjectPattern: 'CN={gateway}, OU=VPN',
    usedBy: '8 certs',
    status: 'ACTIVE',
  },
  {
    id: 7,
    name: 'IoT Device',
    keyUsage: 'Digital Signature',
    validity: '5 years',
    subjectPattern: 'CN={device_id}, OU=IoT',
    usedBy: '567 certs',
    status: 'ACTIVE',
  },
  {
    id: 8,
    name: 'Intermediate CA',
    keyUsage: 'Certificate Sign, CRL Sign',
    validity: '10 years',
    subjectPattern: 'CN={ca_name}, O=Company',
    usedBy: '3 certs',
    status: 'SYSTEM',
  },
];

export function TemplateList() {
  const [filterOpen, setFilterOpen] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleExport = () => {
    if (MOCK_TEMPLATES.length === 0) {
      toast.error('No templates to export');
      return;
    }
    exportTableData(MOCK_TEMPLATES, 'templates-export', {
      format: 'csv',
      columns: ['id', 'name', 'keyUsage', 'validity', 'subjectPattern', 'usedBy', 'status']
    });
    toast.success('Templates exported successfully');
  };

  return (
    <div className={styles.templateList}>
      {/* Page Header */}
      <PageTopBar
        icon="ph ph-file-text"
        title="Certificate Templates"
        badge={<Badge variant="success">{templates.length} Templates</Badge>}
        actions={
          <>
            <Button icon="ph ph-download-simple" onClick={handleExport}>Export</Button>
            <Button variant="primary" icon="ph ph-plus" onClick={() => setShowCreateModal(true)}>New Template</Button>
          </>
        }
      />

      {/* Section Header */}
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>Available Templates</span>
        <button 
          className={styles.filterBtn}
          onClick={() => setFilterOpen(!filterOpen)}
        >
          <i className="ph ph-funnel"></i>
          Filter
        </button>
      </div>

      {/* Templates Table */}
      <div className={styles.tableContainer}>
        <table>
          <thead>
            <tr>
              <th style={{ width: '15%' }}>TEMPLATE NAME</th>
              <th style={{ width: '25%' }}>KEY USAGE</th>
              <th style={{ width: '10%' }}>VALIDITY</th>
              <th style={{ width: '20%' }}>SUBJECT PATTERN</th>
              <th style={{ width: '12%' }}>USED BY</th>
              <th style={{ width: '10%' }}>STATUS</th>
              <th style={{ width: '8%' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '2rem' }}>
                  Loading templates...
                </td>
              </tr>
            ) : templates.length === 0 ? (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '2rem' }}>
                  No templates found
                </td>
              </tr>
            ) : (
              templates.map((template) => (
                <tr key={template.id}>
                  <td>
                    <span className={styles.templateName}>{template.name}</span>
                    {template.isSystem && <Badge variant="info" style={{ marginLeft: '0.5rem' }}>System</Badge>}
                  </td>
                  <td>
                    <span className={styles.keyUsage}>{template.keyUsage}</span>
                  </td>
                  <td>{template.validity}</td>
                  <td>
                    <code className={styles.subjectPattern}>{template.subjectPattern}</code>
                  </td>
                  <td>{template.usedBy}</td>
                  <td>
                    <span 
                      className={`${styles.statusBadge} ${
                        template.status === 'ACTIVE' ? styles.badgeActive : styles.badgeSystem
                      }`}
                    >
                      {template.status}
                    </span>
                  </td>
                  <td>
                    <div className={styles.actionsCell}>
                      {!template.isSystem && (
                        <>
                          <button className={styles.actionBtn} title="Edit">
                            <i className="ph ph-pencil"></i>
                          </button>
                          <button className={styles.actionBtn} title="Delete" onClick={() => handleDelete(template)}>
                            <i className="ph ph-trash"></i>
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      
      <CreateTemplateModal 
        isOpen={showCreateModal} 
        onClose={() => setShowCreateModal(false)} 
      />
    </div>
  );
}

export default TemplateList;
