import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getTemplates } from '../../services/mockData';
import styles from './TemplateList.module.css';

/**
 * Templates Page
 * 
 * Certificate templates management with:
 * - Cards grid layout
 * - Template metadata display
 * - Create/Edit/Delete actions
 */
export function TemplateList() {
  const templates = getTemplates();

  const filters = [
    {
      label: 'Type',
      options: ['All Types', 'Web Server', 'Email', 'Code Signing', 'VPN', 'User', 'OCSP'],
    },
  ];

  const actions = [
    { label: 'Create Template', icon: 'ph ph-plus', variant: 'primary' },
    { label: 'Import Template', icon: 'ph ph-upload', variant: 'default' },
  ];

  return (
    <div className={styles.templateList}>
      <SearchToolbar
        placeholder="Search templates..."
        filters={filters}
        actions={actions}
        onSearch={(query) => console.log('Search:', query)}
        onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
      />

      <div className={styles.grid}>
        {templates.map((template) => (
          <Card key={template.id} className={styles.templateCard}>
            <div className={styles.cardHeader}>
              <div className={styles.iconWrapper}>
                <Icon name={template.icon} size={32} gradient />
              </div>
              <div className={styles.cardActions}>
                <button
                  className={styles.iconButton}
                  onClick={() => console.log('Edit:', template)}
                  title="Edit template"
                >
                  <Icon name="pencil-simple" size={16} />
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() => console.log('Delete:', template)}
                  title="Delete template"
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>

            <div className={styles.cardContent}>
              <h3 className={styles.templateName}>{template.name}</h3>
              <p className={styles.description}>{template.description}</p>

              <div className={styles.metadata}>
                <div className={styles.metadataItem}>
                  <span className={styles.metadataLabel}>Type</span>
                  <Badge variant={getBadgeVariant('template-type', template.type)}>
                    {template.type}
                  </Badge>
                </div>

                <div className={styles.metadataItem}>
                  <span className={styles.metadataLabel}>Certificates Issued</span>
                  <span className={styles.metadataValue}>{template.certificatesIssued}</span>
                </div>

                <div className={styles.metadataItem}>
                  <span className={styles.metadataLabel}>Default Validity</span>
                  <span className={styles.metadataValue}>{template.defaultValidity} days</span>
                </div>
              </div>

              <div className={styles.usage}>
                <div className={styles.usageLabel}>Key Usage:</div>
                <div className={styles.usageTags}>
                  {template.keyUsage.map((usage) => (
                    <span key={usage} className={styles.usageTag}>
                      {usage}
                    </span>
                  ))}
                </div>
              </div>

              {template.extKeyUsage.length > 0 && (
                <div className={styles.usage}>
                  <div className={styles.usageLabel}>Extended Key Usage:</div>
                  <div className={styles.usageTags}>
                    {template.extKeyUsage.map((usage) => (
                      <span key={usage} className={styles.usageTag}>
                        {usage}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className={styles.cardFooter}>
              <Button
                variant="primary"
                icon="ph ph-certificate"
                onClick={() => console.log('Use template:', template)}
              >
                Use Template
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default TemplateList;
