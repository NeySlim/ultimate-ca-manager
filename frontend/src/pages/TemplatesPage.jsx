/**
 * Templates Page
 */
import { useState, useEffect, useRef } from 'react'
import { List, Plus, Copy, Trash, FloppyDisk, Download, FileArrowUp } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Table, Button, Badge,
  Input, Select, Textarea, Modal,
  LoadingSpinner, EmptyState
, HelpCard } from '../components'
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
      const formData = new FormData()
      if (importFile) {
        formData.append('file', importFile)
      } else {
        formData.append('json_content', importJson)
      }
      formData.append('update_existing', 'false')
      
      const result = await templatesService.import(formData)
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

  const templateColumns = [
    { key: 'name', label: 'Name', render: (val) => <span className="font-medium">{val}</span> },
    { 
      key: 'type', 
      label: 'Type',
      render: (val) => <Badge variant="secondary">{val}</Badge>
    },
    { 
      key: 'usage_count', 
      label: 'Used',
      render: (val) => val || 0
    },
    { 
      key: 'created_at', 
      label: 'Created',
      render: (val) => val ? new Date(val).toLocaleDateString() : '-'
    },
  ]

  const keyUsageOptions = [
    'Digital Signature',
    'Non Repudiation',
    'Key Encipherment',
    'Data Encipherment',
    'Key Agreement',
    'Certificate Sign',
    'CRL Sign',
  ]

  const extendedKeyUsageOptions = [
    'Server Authentication',
    'Client Authentication',
    'Code Signing',
    'Email Protection',
    'Time Stamping',
    'OCSP Signing',
  ]

  return (
    <>
      <ExplorerPanel
        title={selectedTemplate?.name || 'Select a template'}
        actions={selectedTemplate && canWrite('templates') && (
          <>
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
            <Button variant="secondary" size="sm" onClick={() => handleDuplicate(selectedTemplate.id)}>
              <Copy size={16} />
              Duplicate
            </Button>
            <Button variant="danger" size="sm" onClick={() => handleDelete(selectedTemplate.id)}>
              <Trash size={16} />
              Delete
            </Button>
          </>
        )}
      >
        {!selectedTemplate ? (
          <EmptyState
            title="No template selected"
            description="Select a template from the list to edit"
          />
        ) : (
          <div className="space-y-6">
            <HelpCard variant="info" title="Certificate Templates" compact>
              Templates define default values for certificate issuance. Use them to standardize certificate properties across your organization.
            </HelpCard>

            {/* Basic Info */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Basic Information</h3>
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
              <h3 className="text-sm font-semibold text-text-primary mb-4">Validity Period</h3>
              <div className="space-y-3">
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
              <h3 className="text-sm font-semibold text-text-primary mb-4">Subject Template</h3>
              <div className="space-y-3">
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
              <h3 className="text-sm font-semibold text-text-primary mb-4">Usage Summary</h3>
              <div className="space-y-2">
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
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'Templates' },
          { label: `${templates.length} templates` }
        ]}
        title="Certificate Templates"
        actions={selectedTemplate && (
          <Button variant="secondary" size="sm" onClick={() => handleExportTemplate(selectedTemplate.id)}>
            <Download size={16} />
            Export
          </Button>
        )}
      >
        <div className="p-4 space-y-3">
          {canWrite('templates') && (
            <>
              <Button onClick={handleCreate} className="w-full">
                <Plus size={18} />
                Create Template
              </Button>
              <Button variant="secondary" onClick={() => openModal('import')} className="w-full">
                <FileArrowUp size={18} />
                Import Template
              </Button>
            </>
          )}
        </div>

        <div className="flex-1 overflow-auto px-4 pb-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : templates.length === 0 ? (
            <EmptyState
              icon={List}
              title="No templates"
              description="Create your first certificate template"
            />
          ) : (
            <Table
              columns={templateColumns}
              data={templates}
              onRowClick={selectTemplate}
              selectedId={selectedTemplate?.id}
            />
          )}
        </div>
      </DetailsPanel>

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
