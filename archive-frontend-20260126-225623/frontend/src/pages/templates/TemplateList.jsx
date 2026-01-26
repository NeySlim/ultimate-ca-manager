import { useState } from 'react';
import { PageTopBar } from '../../components/common';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import ErrorState from '../../components/ui/ErrorState';
import { CreateTemplateModal } from '../../components/modals/CreateTemplateModal';
import { EditTemplateModal } from '../../components/modals/EditTemplateModal';
import { useTemplates, useDeleteTemplate } from '../../hooks/useTemplates';
import { exportTableData } from '../../utils/export';
import toast from 'react-hot-toast';
import styles from './TemplateList.module.css';

export function TemplateList() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState(null);
  const [filterOpen, setFilterOpen] = useState(false);

  // Fetch templates from backend
  const { data, isLoading, error } = useTemplates();
  const deleteTemplate = useDeleteTemplate();

  // Transform backend data to frontend format
  // Handle both {data: [...]} and [...] formats
  const rawTemplates = Array.isArray(data) ? data : (data?.data || []);
  
  const templates = rawTemplates.map(template => {
    try {
      // Format dn_template object as string
      const dnTemplate = template.dn_template;
      let subjectPattern = 'N/A';
      if (typeof dnTemplate === 'string') {
        subjectPattern = dnTemplate;
      } else if (dnTemplate && typeof dnTemplate === 'object') {
        // Convert {CN: "...", O: "...", ...} to "CN=..., O=..."
        const parts = Object.entries(dnTemplate)
          .filter(([k, v]) => v && v.trim())
          .map(([k, v]) => `${k}=${v}`);
        subjectPattern = parts.length > 0 ? parts.join(', ') : 'N/A';
      }
      
      return {
        id: template.id,
        name: template.name || 'Unnamed',
        keyUsage: template.extensions_template?.key_usage?.join(', ') || 'N/A',
        validity: template.validity_days ? `${template.validity_days} days` : 'N/A',
        subjectPattern: subjectPattern,
        usedBy: '0 certs', // Backend doesn't track this yet
        status: 'ACTIVE',
        isSystem: template.is_system || false,
      };
    } catch (err) {
      console.error('Error mapping template:', template, err);
      return null;
    }
  }).filter(Boolean);

  const handleExport = () => {
    if (templates.length === 0) {
      toast.error('No templates to export');
      return;
    }
    exportTableData(templates, 'templates-export', {
      format: 'csv',
      columns: ['id', 'name', 'keyUsage', 'validity', 'subjectPattern', 'usedBy', 'status']
    });
    toast.success('Templates exported successfully');
  };

  const handleDelete = (template) => {
    if (template.isSystem) {
      toast.error('Cannot delete system template');
      return;
    }
    if (confirm(`Delete template "${template.name}"?`)) {
      deleteTemplate.mutate(template.id);
    }
  };

  const handleEdit = (template) => {
    if (template.isSystem) {
      toast.error('Cannot edit system template');
      return;
    }
    setEditingTemplateId(template.id);
    setShowEditModal(true);
  };

  if (isLoading) {
    return (
      <div className={styles.templateList}>
        <PageTopBar
          icon="ph ph-file-text"
          title="Certificate Templates"
          badge={<Badge variant="neutral">Loading...</Badge>}
        />
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} width="100%" height={70} style={{ marginBottom: '10px' }} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.templateList}>
        <PageTopBar icon="ph ph-file-text" title="Certificate Templates" badge={<Badge variant="danger">Error</Badge>} />
        <ErrorState error={error} shake />
      </div>
    );
  }

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
        {templates.length === 0 ? (
          <EmptyState
            icon="ph ph-file-text"
            title="No Certificate Templates"
            message="Create reusable templates to standardize certificate issuance"
            action={{
              label: "New Template",
              onClick: () => setShowCreateModal(true)
            }}
          />
        ) : (
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
                          <button className={styles.actionBtn} title="Edit" onClick={() => handleEdit(template)}>
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
        )}
      </div>
      
      <CreateTemplateModal 
        isOpen={showCreateModal} 
        onClose={() => setShowCreateModal(false)} 
      />
      <EditTemplateModal 
        isOpen={showEditModal} 
        onClose={() => setShowEditModal(false)} 
        templateId={editingTemplateId}
      />
    </div>
  );
}

export default TemplateList;
