/**
 * Templates Page - Certificate template management
 * Uses PageLayout for consistent UI structure
 */
import { useState, useEffect, useRef } from 'react'
import { 
  List, Plus, Copy, Trash, FloppyDisk, Download, FileArrowUp,
  MagnifyingGlass, Database, Files
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Badge, Card,
  Input, Select, Textarea, Modal,
  LoadingSpinner, EmptyState, HelpCard
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
      if (templatesList.length > 0 && !selectedTemplate) {
        selectTemplate(templatesList[0])
      }
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
      subject: {
        C: '',
        ST: '',
        L: '',
        O: '',
        OU: '',
        CN: '',
      },
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

  // Filter templates by search
  const filteredTemplates = templates.filter(t => 
    t.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.type?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Calculate stats for help content
  const certTemplates = templates.filter(t => t.type === 'certificate').length
  const caTemplates = templates.filter(t => t.type === 'ca').length
  const totalUsage = templates.reduce((sum, t) => sum + (t.usage_count || 0), 0)

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* Template Statistics */}
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

      {/* Usage Stats */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-emerald-500/10 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Files size={16} className="text-accent-primary" />
          Usage Statistics
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Total Certificates Issued</span>
            <span className="text-sm font-medium text-text-primary">{totalUsage}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Most Used Type</span>
            <span className="text-sm font-medium text-text-primary">
              {certTemplates >= caTemplates ? 'Certificate' : 'CA'}
            </span>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
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

  // Focus panel content (search + template list)
  const focusContent = (
    <div className="p-2 space-y-1.5">
      {/* Search */}
      <div className="px-1 pb-2">
        <div className="relative">
          <MagnifyingGlass 
            size={14} 
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" 
          />
          <input
            type="text"
            placeholder="Search templates..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary"
          />
        </div>
      </div>

      {/* Template List */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <LoadingSpinner size="sm" />
        </div>
      ) : filteredTemplates.length === 0 ? (
        <EmptyState 
          icon={List}
          title={searchQuery ? "No matches" : "No templates"}
          description={searchQuery ? "Try a different search" : "Create your first template"}
        />
      ) : (
        filteredTemplates.map((template) => (
          <FocusItem
            key={template.id}
            icon={List}
            title={template.name}
            subtitle={`${template.type} • ${template.usage_count || 0} used`}
            badge={
              <Badge variant={template.type === 'ca' ? 'warning' : 'secondary'} size="sm">
                {template.type}
              </Badge>
            }
            selected={selectedTemplate?.id === template.id}
            onClick={() => selectTemplate(template)}
          />
        ))
      )}
    </div>
  )

  // Focus panel actions (create + import buttons)
  const focusActions = canWrite('templates') && (
    <>
      <Button size="sm" onClick={handleCreate} className="flex-1">
        <Plus size={14} />
        New
      </Button>
      <Button size="sm" variant="secondary" onClick={() => openModal('import')}>
        <FileArrowUp size={14} />
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
      <PageLayout
        title="Templates"
        focusTitle="Templates"
        focusContent={focusContent}
        focusActions={focusActions}
        focusFooter={`${filteredTemplates.length} template(s)`}
        helpContent={helpContent}
        helpTitle="Templates - Aide"
      >
        {/* Main Content - Template Details */}
        {!selectedTemplate ? (
          <div className="flex items-center justify-center h-full">
            <EmptyState
              icon={List}
              title="No template selected"
              description="Select a template from the list to view details"
            />
          </div>
        ) : (
          <div className="p-6 space-y-6">
            {/* Header with actions */}
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-text-primary">
                {selectedTemplate.name}
              </h3>
              {canWrite('templates') && (
                <div className="flex items-center gap-2">
                  {editing ? (
                    <Button size="sm" onClick={handleSave}>
                      <FloppyDisk size={16} />
                      Save
                    </Button>
                  ) : (
                    <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                      Edit
                    </Button>
                  )}
                  <Button variant="secondary" size="sm" onClick={() => handleExportTemplate(selectedTemplate.id)}>
                    <Download size={16} />
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => handleDuplicate(selectedTemplate.id)}>
                    <Copy size={16} />
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => handleDelete(selectedTemplate.id)}>
                    <Trash size={16} />
                  </Button>
                </div>
              )}
            </div>

            {/* Basic Info */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">
                Basic Information
              </h3>
              <div className="space-y-4">
                <Input
                  label="Template Name"
                  value={formData.name || ''}
                  onChange={(e) => updateFormData('name', e.target.value)}
                  disabled={!editing}
                />
                <Textarea
                  label="Description"
                  value={formData.description || ''}
                  onChange={(e) => updateFormData('description', e.target.value)}
                  disabled={!editing}
                  rows={3}
                />
                <Select
                  label="Type"
                  options={[
                    { value: 'certificate', label: 'Certificate' },
                    { value: 'ca', label: 'Certificate Authority' },
                  ]}
                  value={formData.type || 'certificate'}
                  onChange={(val) => updateFormData('type', val)}
                  disabled={!editing}
                />
              </div>
            </div>

            {/* Validity */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">
                Validity Period
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Default Validity (days)"
                  type="number"
                  value={formData.validity_days || 365}
                  onChange={(e) => updateFormData('validity_days', parseInt(e.target.value))}
                  disabled={!editing}
                />
                <Input
                  label="Max Validity (days)"
                  type="number"
                  value={formData.max_validity_days || 3650}
                  onChange={(e) => updateFormData('max_validity_days', parseInt(e.target.value))}
                  disabled={!editing}
                />
              </div>
            </div>

            {/* Subject */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">
                Subject Template
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Country (C)"
                  value={formData.subject?.C || ''}
                  onChange={(e) => updateSubject('C', e.target.value)}
                  disabled={!editing}
                  placeholder="US"
                />
                <Input
                  label="State (ST)"
                  value={formData.subject?.ST || ''}
                  onChange={(e) => updateSubject('ST', e.target.value)}
                  disabled={!editing}
                  placeholder="California"
                />
                <Input
                  label="Organization (O)"
                  value={formData.subject?.O || ''}
                  onChange={(e) => updateSubject('O', e.target.value)}
                  disabled={!editing}
                  placeholder="Example Corp"
                />
                <Input
                  label="Common Name (CN)"
                  value={formData.subject?.CN || ''}
                  onChange={(e) => updateSubject('CN', e.target.value)}
                  disabled={!editing}
                  placeholder="*.example.com"
                />
              </div>
            </div>

            {/* Key Usage Summary */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">
                Usage Summary
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Key Usage</p>
                  <p className="text-sm text-text-primary">
                    {formData.key_usage?.length > 0 ? formData.key_usage.join(', ') : 'None'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Extended Key Usage</p>
                  <p className="text-sm text-text-primary">
                    {formData.extended_key_usage?.length > 0 ? formData.extended_key_usage.join(', ') : 'None'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </PageLayout>

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
