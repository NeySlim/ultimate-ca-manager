/**
 * Templates Page - Certificate template management
 * Migrated to ResponsiveLayout for consistent UI
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { 
  List, Plus, Copy, Trash, FloppyDisk, Download, FileArrowUp,
  MagnifyingGlass, Database, Files, FileText, PencilSimple, Calendar,
  Certificate, ShieldCheck
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Badge, Card,
  Input, Select, Textarea, Modal,
  LoadingSpinner, EmptyState, HelpCard,
  CompactHeader, CompactSection, CompactGrid, CompactField
} from '../components'
import { templatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData } from '../lib/utils'

export default function TemplatesPage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const fileRef = useRef(null)
  const { modals, open: openModal, close: closeModal } = useModals(['import'])
  
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({})
  const [searchQuery, setSearchQuery] = useState('')
  const [filterType, setFilterType] = useState('')
  
  // Import state
  const [importFile, setImportFile] = useState(null)
  const [importJson, setImportJson] = useState('')
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    loadTemplates()
  }, [])

  const loadTemplates = async () => {
    setLoading(true)
    try {
      const data = await templatesService.getAll()
      const templatesList = data.data || []
      setTemplates(templatesList)
    } catch (error) {
      showError(error.message || 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }

  const selectTemplate = async (template) => {
    try {
      const response = await templatesService.getById(template.id)
      const data = extractData(response)
      setSelectedTemplate({ ...data })
      setFormData({ ...data })
      setEditing(false)
    } catch (error) {
      console.error('Failed to load template:', error)
      showError(error.message || 'Failed to load template details')
    }
  }

  const handleCreate = async () => {
    const newTemplate = {
      name: 'New Template',
      description: '',
      type: 'certificate',
      validity_days: 365,
      subject: { C: '', ST: '', L: '', O: '', OU: '', CN: '' },
      key_usage: [],
      extended_key_usage: [],
    }
    
    try {
      const created = await templatesService.create(newTemplate)
      showSuccess('Template created')
      loadTemplates()
      selectTemplate(created)
      setEditing(true)
    } catch (error) {
      showError(error.message || 'Failed to create template')
    }
  }

  const handleSave = async () => {
    try {
      await templatesService.update(selectedTemplate.id, formData)
      showSuccess('Template saved successfully')
      setEditing(false)
      loadTemplates()
    } catch (error) {
      showError(error.message || 'Failed to save template')
    }
  }

  const handleDuplicate = async (id) => {
    try {
      const duplicated = await templatesService.duplicate(id)
      showSuccess('Template duplicated')
      loadTemplates()
      selectTemplate(duplicated)
    } catch (error) {
      showError(error.message || 'Failed to duplicate template')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to delete this template?', {
      title: 'Delete Template',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await templatesService.delete(id)
      showSuccess('Template deleted')
      setSelectedTemplate(null)
      loadTemplates()
    } catch (error) {
      showError(error.message || 'Failed to delete template')
    }
  }

  const handleExportTemplate = async (id) => {
    try {
      const blob = await templatesService.export(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selectedTemplate?.name || 'template'}.json`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess('Template exported')
    } catch (error) {
      showError(error.message || 'Failed to export template')
    }
  }

  const handleImportTemplate = async () => {
    if (!importFile && !importJson.trim()) {
      showError('Please select a file or paste JSON content')
      return
    }
    setImporting(true)
    try {
      const formDataObj = new FormData()
      if (importFile) {
        formDataObj.append('file', importFile)
      } else {
        formDataObj.append('json_content', importJson)
      }
      formDataObj.append('update_existing', 'false')
      
      const result = await templatesService.import(formDataObj)
      showSuccess(result.message || 'Template imported successfully')
      closeModal('import')
      setImportFile(null)
      setImportJson('')
      if (fileRef.current) fileRef.current.value = ''
      loadTemplates()
    } catch (error) {
      showError(error.message || 'Failed to import template')
    } finally {
      setImporting(false)
    }
  }

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const updateSubject = (field, value) => {
    setFormData(prev => ({
      ...prev,
      subject: { ...prev.subject, [field]: value }
    }))
  }

  // Filter templates
  const filteredTemplates = useMemo(() => {
    return templates.filter(t => {
      const matchesSearch = !searchQuery || 
        t.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.type?.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesType = !filterType || t.type === filterType
      return matchesSearch && matchesType
    })
  }, [templates, searchQuery, filterType])

  // Helper to determine template type
  const getTemplateType = useCallback((t) => {
    if (t.type) return t.type
    // Infer from name or key_usage
    const name = (t.name || '').toLowerCase()
    if (name.includes('ca') || name.includes('authority') || t.is_ca || t.basic_constraints?.ca) {
      return 'ca'
    }
    return 'certificate'
  }, [])

  // Calculate stats
  const certTemplates = templates.filter(t => getTemplateType(t) === 'certificate').length
  const caTemplates = templates.filter(t => getTemplateType(t) === 'ca').length
  const totalUsage = templates.reduce((sum, t) => sum + (t.usage_count || 0), 0)

  // Stats for header
  const headerStats = useMemo(() => [
    { icon: Files, label: 'Total', value: templates.length },
    { icon: Certificate, label: 'Certificate', value: certTemplates, variant: 'info' },
    { icon: ShieldCheck, label: 'CA', value: caTemplates, variant: 'violet' },
    { icon: Database, label: 'Used', value: totalUsage }
  ], [templates.length, certTemplates, caTemplates, totalUsage])

  // Table columns
  const columns = useMemo(() => [
    { 
      key: 'name', 
      label: 'Name',
      render: (v, row) => (
        <div className="flex items-center gap-2">
          <List size={14} className="text-text-secondary" />
          <span className="font-medium">{v}</span>
        </div>
      )
    },
    { 
      key: 'type', 
      label: 'Type',
      width: '100px',
      render: (v, row) => {
        const type = getTemplateType(row)
        return (
          <Badge variant={type === 'ca' ? 'violet' : 'secondary'} size="sm">
            {type === 'ca' ? 'CA' : 'Certificate'}
          </Badge>
        )
      }
    },
    { 
      key: 'validity_days', 
      label: 'Validity',
      width: '100px',
      render: (v) => <span className="text-text-secondary">{v} days</span>
    },
    { 
      key: 'usage_count', 
      label: 'Used',
      width: '80px',
      render: (v) => <span className="text-text-secondary">{v || 0}x</span>
    }
  ], [getTemplateType])

  // Filters
  const filters = useMemo(() => [
    {
      key: 'type',
      label: 'Type',
      type: 'select',
      value: filterType,
      onChange: setFilterType,
      placeholder: 'All Types',
      options: [
        { value: 'certificate', label: 'Certificate' },
        { value: 'ca', label: 'CA' }
      ]
    }
  ], [filterType])

  // Row actions for table
  const getRowActions = useCallback((template) => [
    {
      label: 'Duplicate',
      icon: Copy,
      onClick: () => handleDuplicate(template.id)
    },
    {
      label: 'Export',
      icon: Download,
      onClick: () => handleExportTemplate(template.id)
    },
    ...(canDelete ? [{
      label: 'Delete',
      icon: Trash,
      variant: 'danger',
      onClick: () => handleDelete(template.id)
    }] : [])
  ], [canDelete])

  // Mobile card render
  const renderMobileCard = useCallback((template, isSelected) => (
    <div className={`p-4 ${isSelected ? 'mobile-row-selected' : ''}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-bg-tertiary flex items-center justify-center">
            <List size={20} className="text-text-secondary" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-text-primary truncate">{template.name}</span>
              <Badge variant={template.type === 'ca' ? 'violet' : 'secondary'} size="sm">
                {template.type === 'ca' ? 'CA' : 'Cert'}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-text-secondary mt-0.5">
              <span>{template.validity_days} days</span>
              <span>•</span>
              <span>{template.usage_count || 0} used</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  ), [])

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          Template Statistics
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{templates.length}</p>
            <p className="text-xs text-text-secondary">Total</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-accent-primary">{certTemplates}</p>
            <p className="text-xs text-text-secondary">Certificate</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-warning">{caTemplates}</p>
            <p className="text-xs text-text-secondary">CA</p>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        <HelpCard variant="info" title="About Templates">
          Certificate templates define default values for certificate issuance. 
          Use them to standardize certificate properties across your organization.
        </HelpCard>
        
        <HelpCard variant="tip" title="Template Types">
          Use "Certificate" type for end-entity certificates (servers, users). 
          Use "CA" type for intermediate certificate authorities.
        </HelpCard>

        <HelpCard variant="warning" title="Key Usage">
          Ensure Key Usage and Extended Key Usage match your certificate's intended purpose. 
          Incorrect settings may cause validation failures.
        </HelpCard>
      </div>
    </div>
  )

  // Template details slide-over content
  const templateDetailContent = selectedTemplate && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={FileText}
        iconClass={selectedTemplate.type === 'ca' ? "bg-violet-500/20" : "bg-accent-primary/20"}
        title={editing ? formData.name : selectedTemplate.name}
        subtitle={`${selectedTemplate.usage_count || 0} certificates issued`}
        badge={
          <Badge variant={selectedTemplate.type === 'ca' ? 'violet' : 'secondary'} size="sm">
            {selectedTemplate.type === 'ca' ? 'CA' : 'Cert'}
          </Badge>
        }
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {canWrite('templates') && (
          editing ? (
            <Button size="sm" variant="primary" onClick={handleSave}>
              <FloppyDisk size={14} /> Save
            </Button>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
              <PencilSimple size={14} /> Edit
            </Button>
          )
        )}
        <Button size="sm" variant="secondary" onClick={() => handleExportTemplate(selectedTemplate.id)}>
          <Download size={14} />
        </Button>
        {canWrite('templates') && (
          <Button size="sm" variant="secondary" onClick={() => handleDuplicate(selectedTemplate.id)}>
            <Copy size={14} />
          </Button>
        )}
        {canDelete('templates') && (
          <Button size="sm" variant="danger" onClick={() => handleDelete(selectedTemplate.id)}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Basic Information */}
      <CompactSection title="Basic Information">
        {editing ? (
          <div className="space-y-3">
            <Input
              label="Template Name"
              value={formData.name || ''}
              onChange={(e) => updateFormData('name', e.target.value)}
            />
            <Textarea
              label="Description"
              value={formData.description || ''}
              onChange={(e) => updateFormData('description', e.target.value)}
              rows={2}
            />
            <Select
              label="Type"
              options={[
                { value: 'certificate', label: 'Certificate' },
                { value: 'ca', label: 'Certificate Authority' },
              ]}
              value={formData.type || 'certificate'}
              onChange={(val) => updateFormData('type', val)}
            />
          </div>
        ) : (
          <CompactGrid>
            <CompactField label="Template Name" value={formData.name} />
            <CompactField label="Type" value={formData.type === 'ca' ? 'Certificate Authority' : 'Certificate'} />
            <CompactField label="Description" value={formData.description} />
          </CompactGrid>
        )}
      </CompactSection>

      {/* Validity Period */}
      <CompactSection title="Validity Period">
        {editing ? (
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Default (days)"
              type="number"
              value={formData.validity_days || 365}
              onChange={(e) => updateFormData('validity_days', parseInt(e.target.value))}
            />
            <Input
              label="Max (days)"
              type="number"
              value={formData.max_validity_days || 3650}
              onChange={(e) => updateFormData('max_validity_days', parseInt(e.target.value))}
            />
          </div>
        ) : (
          <CompactGrid>
            <CompactField label="Default Validity" value={`${formData.validity_days || 365} days`} />
            <CompactField label="Max Validity" value={`${formData.max_validity_days || 3650} days`} />
          </CompactGrid>
        )}
      </CompactSection>

      {/* Subject Template */}
      <CompactSection title="Subject Template" collapsible>
        {editing ? (
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Country (C)"
              value={formData.subject?.C || ''}
              onChange={(e) => updateSubject('C', e.target.value)}
              placeholder="US"
            />
            <Input
              label="State (ST)"
              value={formData.subject?.ST || ''}
              onChange={(e) => updateSubject('ST', e.target.value)}
              placeholder="California"
            />
            <Input
              label="Organization (O)"
              value={formData.subject?.O || ''}
              onChange={(e) => updateSubject('O', e.target.value)}
              placeholder="Example Corp"
            />
            <Input
              label="Common Name (CN)"
              value={formData.subject?.CN || ''}
              onChange={(e) => updateSubject('CN', e.target.value)}
              placeholder="*.example.com"
            />
          </div>
        ) : (
          <CompactGrid>
            <CompactField label="Country (C)" value={formData.subject?.C} />
            <CompactField label="State (ST)" value={formData.subject?.ST} />
            <CompactField label="Organization (O)" value={formData.subject?.O} />
            <CompactField label="Common Name (CN)" value={formData.subject?.CN} />
          </CompactGrid>
        )}
      </CompactSection>

      {/* Usage Summary */}
      <CompactSection title="Usage Summary" collapsible defaultOpen={false}>
        <CompactGrid cols={1}>
          <CompactField 
            label="Key Usage"
            value={formData.key_usage?.length > 0 ? formData.key_usage.join(', ') : 'None'}
          />
          <CompactField 
            label="Extended Key Usage"
            value={formData.extended_key_usage?.length > 0 ? formData.extended_key_usage.join(', ') : 'None'}
          />
        </CompactGrid>
      </CompactSection>
    </div>
  )

  // Header actions
  const headerActions = canWrite('templates') && (
    <>
      <Button size="sm" onClick={handleCreate} className="hidden md:inline-flex">
        <Plus size={14} />
        New
      </Button>
      <Button size="sm" variant="secondary" onClick={() => openModal('import')} className="hidden md:inline-flex">
        <FileArrowUp size={14} />
      </Button>
      {/* Mobile */}
      <Button size="lg" onClick={handleCreate} className="md:hidden h-11 w-11 p-0">
        <Plus size={22} />
      </Button>
    </>
  )

  if (loading && templates.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title="Templates"
        icon={List}
        subtitle={`${templates.length} templates`}
        stats={headerStats}
        helpContent={helpContent}
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <List size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">Select a template to view details</p>
          </div>
        }
        slideOverOpen={!!selectedTemplate}
        onSlideOverClose={() => { setSelectedTemplate(null); setEditing(false); }}
        slideOverTitle={editing ? 'Edit Template' : 'Template Details'}
        slideOverContent={templateDetailContent}
        slideOverWidth="lg"
      >
        <ResponsiveDataTable
          data={filteredTemplates}
          columns={columns}
          keyField="id"
          searchable
          searchPlaceholder="Search templates..."
          searchKeys={['name', 'description']}
          toolbarFilters={[
            {
              key: 'type',
              value: filterType,
              onChange: setFilterType,
              placeholder: 'All Types',
              options: [
                { value: 'certificate', label: 'Certificate' },
                { value: 'ca', label: 'CA' }
              ]
            }
          ]}
          toolbarActions={canWrite('templates') && (
            <>
              <Button size="sm" onClick={handleCreate} className="hidden md:inline-flex">
                <Plus size={14} />
                New
              </Button>
              <Button size="sm" variant="secondary" onClick={() => openModal('import')} className="hidden md:inline-flex">
                <FileArrowUp size={14} />
              </Button>
              {/* Mobile */}
              <Button size="lg" onClick={handleCreate} className="md:hidden h-11 w-11 p-0">
                <Plus size={22} />
              </Button>
            </>
          )}
          selectedId={selectedTemplate?.id}
          onRowClick={selectTemplate}
          rowActions={getRowActions}
          sortable
          emptyState={{
            icon: List,
            title: searchQuery ? 'No matches' : 'No templates',
            description: searchQuery ? 'Try a different search' : 'Create your first template'
          }}
        />
      </ResponsiveLayout>

      {/* Import Template Modal */}
      <Modal
        open={modals.import}
        onClose={() => closeModal('import')}
        title="Import Template"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Import a certificate template from a JSON file or paste JSON content
          </p>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">Template File (JSON)</label>
            <input
              ref={fileRef}
              type="file"
              accept=".json"
              onChange={(e) => { setImportFile(e.target.files[0]); setImportJson('') }}
              className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
            />
          </div>
          
          <div className="flex items-center gap-3">
            <div className="flex-1 border-t border-border"></div>
            <span className="text-xs text-text-secondary">OR paste JSON content</span>
            <div className="flex-1 border-t border-border"></div>
          </div>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">Paste JSON Content</label>
            <textarea
              value={importJson}
              onChange={(e) => { setImportJson(e.target.value); setImportFile(null); if (fileRef.current) fileRef.current.value = '' }}
              placeholder='{"name": "My Template", "validity_days": 365, ...}'
              rows={6}
              className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-sm text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
            />
          </div>
          
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => closeModal('import')}>Cancel</Button>
            <Button onClick={handleImportTemplate} disabled={importing || (!importFile && !importJson.trim())}>
              {importing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
              Import Template
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
