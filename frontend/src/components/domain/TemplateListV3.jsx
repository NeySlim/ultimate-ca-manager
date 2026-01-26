import { useState } from 'react';
import {
  Files,
  Plus,
  MagnifyingGlass,
  Copy,
  Pencil,
  Trash,
  Eye,
  Download,
  FileText,
  Star,
  StarFill,
  Check
} from '@phosphor-icons/react';

// Design System V3
import { Card } from '../../design-system/components/primitives/Card';
import { Button } from '../../design-system/components/primitives/Button';
import { Input } from '../../design-system/components/primitives/Input';
import { Select } from '../../design-system/components/primitives/Select';
import { Badge } from '../../design-system/components/primitives/Badge';
import { GradientBadge } from '../../design-system/components/primitives/GradientBadge';
import { GlassCard } from '../../design-system/components/primitives/GlassCard';
import { Stack } from '../../design-system/components/layout/Stack';
import { Inline } from '../../design-system/components/layout/Inline';
import { Grid } from '../../design-system/components/layout/Grid';
import { Modal } from '../../design-system/components/overlays/Modal';
import { Dropdown } from '../../design-system/components/overlays/Dropdown';
import { EmptyState } from '../../design-system/components/feedback/EmptyState';
import { Skeleton } from '../../design-system/components/feedback/Skeleton';
import { Tabs } from '../../design-system/components/navigation/Tabs';

import { useTemplates } from '../../hooks/useTemplates';
import styles from './TemplateListV3.module.css';

// Template Card
function TemplateCard({ template, onSelect, onDuplicate, onEdit, onDelete, onToggleFavorite }) {
  const typeVariants = {
    'server-auth': 'blue',
    'client-auth': 'green',
    'email': 'purple',
    'code-signing': 'orange',
  };

  return (
    <Card hoverable className={styles.templateCard} onClick={() => onSelect?.(template)}>
      <Stack gap="md">
        {/* Header */}
        <div className={styles.cardHeader}>
          <div className={styles.cardIcon}>
            <FileText size={28} weight="duotone" />
          </div>
          <button
            className={styles.favoriteButton}
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite?.(template);
            }}
          >
            {template.is_favorite ? (
              <StarFill size={20} weight="fill" color="var(--color-warning-500)" />
            ) : (
              <Star size={20} />
            )}
          </button>
        </div>

        {/* Content */}
        <div>
          <div className={styles.cardTitle}>{template.name}</div>
          <div className={styles.cardDescription}>
            {template.description || 'No description'}
          </div>
        </div>

        {/* Badges */}
        <Inline gap="xs" wrap>
          <GradientBadge variant={typeVariants[template.type] || 'blue'} size="sm">
            {template.type}
          </GradientBadge>
          {template.usage_count > 0 && (
            <Badge variant="default" size="sm">
              {template.usage_count} used
            </Badge>
          )}
        </Inline>

        {/* Meta */}
        <div className={styles.cardMeta}>
          <span>Updated {template.updated_at}</span>
        </div>

        {/* Actions */}
        <div className={styles.cardActions} onClick={(e) => e.stopPropagation()}>
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Copy size={16} />}
            onClick={() => onDuplicate?.(template)}
          >
            Duplicate
          </Button>
          <Dropdown
            items={[
              { label: 'Edit', icon: <Pencil size={16} />, onClick: () => onEdit?.(template) },
              { label: 'Preview', icon: <Eye size={16} />, onClick: () => onSelect?.(template) },
              { label: 'Export', icon: <Download size={16} />, onClick: () => {} },
              { type: 'divider' },
              { label: 'Delete', icon: <Trash size={16} />, onClick: () => onDelete?.(template), variant: 'danger' },
            ]}
          >
            <Button variant="ghost" size="sm">•••</Button>
          </Dropdown>
        </div>
      </Stack>
    </Card>
  );
}

// Template Preview Modal
function TemplatePreviewModal({ template, isOpen, onClose }) {
  if (!template) return null;

  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <Eye size={16} /> },
    { id: 'fields', label: 'Fields', icon: <FileText size={16} /> },
    { id: 'extensions', label: 'Extensions', icon: <Check size={16} /> },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title={template.name}
    >
      <Stack gap="lg">
        <Tabs
          tabs={tabs}
          activeTab={activeTab}
          onChange={setActiveTab}
        />

        {activeTab === 'overview' && (
          <Stack gap="md">
            <div className={styles.previewSection}>
              <h3 className={styles.previewSectionTitle}>Description</h3>
              <p className={styles.previewText}>{template.description || 'No description provided'}</p>
            </div>

            <div className={styles.previewSection}>
              <h3 className={styles.previewSectionTitle}>Details</h3>
              <Grid cols={2} gap="md">
                <div className={styles.detailItem}>
                  <div className={styles.detailLabel}>Type</div>
                  <div className={styles.detailValue}>{template.type}</div>
                </div>
                <div className={styles.detailItem}>
                  <div className={styles.detailLabel}>Key Size</div>
                  <div className={styles.detailValue}>{template.key_size} bits</div>
                </div>
                <div className={styles.detailItem}>
                  <div className={styles.detailLabel}>Validity Period</div>
                  <div className={styles.detailValue}>{template.validity_days} days</div>
                </div>
                <div className={styles.detailItem}>
                  <div className={styles.detailLabel}>Usage Count</div>
                  <div className={styles.detailValue}>{template.usage_count || 0}</div>
                </div>
              </Grid>
            </div>
          </Stack>
        )}

        {activeTab === 'fields' && (
          <Stack gap="sm">
            {template.fields?.map((field, idx) => (
              <Card key={idx}>
                <Inline gap="md" align="center">
                  <div className={styles.fieldName}>{field.name}</div>
                  <div style={{ flex: 1 }} />
                  {field.required && <Badge variant="warning" size="sm">Required</Badge>}
                  <Badge variant="default" size="sm">{field.type}</Badge>
                </Inline>
                {field.default_value && (
                  <div className={styles.fieldDefault}>Default: {field.default_value}</div>
                )}
              </Card>
            )) || <p style={{ color: 'var(--color-text-secondary)' }}>No custom fields</p>}
          </Stack>
        )}

        {activeTab === 'extensions' && (
          <Stack gap="sm">
            {template.extensions?.map((ext, idx) => (
              <Card key={idx}>
                <Stack gap="xs">
                  <Inline gap="sm" align="center">
                    <div className={styles.extensionName}>{ext.name}</div>
                    {ext.critical && <Badge variant="danger" size="sm">Critical</Badge>}
                  </Inline>
                  <div className={styles.extensionValue}>{ext.value}</div>
                </Stack>
              </Card>
            )) || <p style={{ color: 'var(--color-text-secondary)' }}>No extensions configured</p>}
          </Stack>
        )}

        <Inline gap="sm" justify="end">
          <Button variant="secondary" leftIcon={<Copy size={18} />}>
            Duplicate
          </Button>
          <Button variant="primary" leftIcon={<Pencil size={18} />}>
            Edit Template
          </Button>
        </Inline>
      </Stack>
    </Modal>
  );
}

export function TemplateListV3() {
  const { data: templates, isLoading } = useTemplates();

  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [viewMode, setViewMode] = useState('all'); // 'all' or 'favorites'
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const handleToggleFavorite = (template) => {
    console.log('Toggle favorite:', template);
    // TODO: API call
  };

  const handleDuplicate = (template) => {
    console.log('Duplicate template:', template);
    // TODO: API call
  };

  const filteredTemplates = templates?.filter(template => {
    if (searchQuery && !template.name.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    if (typeFilter !== 'all' && template.type !== typeFilter) {
      return false;
    }
    if (viewMode === 'favorites' && !template.is_favorite) {
      return false;
    }
    return true;
  });

  const handleClearFilters = () => {
    setSearchQuery('');
    setTypeFilter('all');
    setViewMode('all');
  };

  const hasFilters = searchQuery || typeFilter !== 'all' || viewMode === 'favorites';

  if (isLoading) {
    return (
      <div className={styles.container}>
        <Stack gap="xl">
          <Skeleton height="60px" />
          <Skeleton height="120px" />
          <Grid cols={3} gap="lg">
            {[...Array(6)].map((_, i) => <Skeleton key={i} height="280px" />)}
          </Grid>
        </Stack>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <Stack gap="xl">
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Templates</h1>
            <p className={styles.subtitle}>
              {filteredTemplates?.length || 0} template{filteredTemplates?.length !== 1 ? 's' : ''}
            </p>
          </div>
          <Button 
            variant="primary" 
            leftIcon={<Plus size={20} weight="bold" />}
            onClick={() => {/* TODO: Create template */}}
          >
            Create Template
          </Button>
        </div>

        {/* Filters */}
        <GlassCard blur="md">
          <div className={styles.filtersBar}>
            <div className={styles.filtersLeft}>
              <Input
                placeholder="Search templates..."
                leftIcon={<MagnifyingGlass size={18} />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ width: '300px' }}
              />
              
              <Select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                style={{ width: '180px' }}
              >
                <option value="all">All Types</option>
                <option value="server-auth">Server Auth</option>
                <option value="client-auth">Client Auth</option>
                <option value="email">Email</option>
                <option value="code-signing">Code Signing</option>
              </Select>

              <div className={styles.viewToggle}>
                <Button
                  variant={viewMode === 'all' ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => setViewMode('all')}
                >
                  All
                </Button>
                <Button
                  variant={viewMode === 'favorites' ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => setViewMode('favorites')}
                  leftIcon={<Star size={16} />}
                >
                  Favorites
                </Button>
              </div>
            </div>

            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={handleClearFilters}>
                Clear Filters
              </Button>
            )}
          </div>
        </GlassCard>

        {/* Templates Grid */}
        {!filteredTemplates || filteredTemplates.length === 0 ? (
          <EmptyState
            icon={<Files size={64} />}
            title={hasFilters ? "No templates match your filters" : "No templates"}
            description={hasFilters ? "Try adjusting your filters" : "Create your first template to get started"}
            action={!hasFilters && (
              <Button variant="primary" leftIcon={<Plus size={20} />}>
                Create Template
              </Button>
            )}
          />
        ) : (
          <Grid cols={3} gap="lg">
            {filteredTemplates.map((template) => (
              <TemplateCard
                key={template.id}
                template={template}
                onSelect={(t) => { setSelectedTemplate(t); setPreviewOpen(true); }}
                onDuplicate={handleDuplicate}
                onToggleFavorite={handleToggleFavorite}
              />
            ))}
          </Grid>
        )}
      </Stack>

      {/* Preview Modal */}
      <TemplatePreviewModal
        template={selectedTemplate}
        isOpen={previewOpen}
        onClose={() => setPreviewOpen(false)}
      />
    </div>
  );
}

export default TemplateListV3;
