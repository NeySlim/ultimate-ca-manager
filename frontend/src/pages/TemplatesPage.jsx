/**
 * Templates Page
 */
import { useState, useEffect } from 'react'
import { List, Plus, Copy, Trash, FloppyDisk } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Table, Button, Badge,
  Input, Select, Textarea,
  LoadingSpinner, EmptyState
} from '../components'
import { templatesService } from '../services'
import { useNotification } from '../contexts'
import { extractData } from '../lib/utils'

export default function TemplatesPage() {
  const { showSuccess, showError } = useNotification()
  
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({})

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
      console.log('Template loaded:', data)
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
    if (!confirm('Are you sure you want to delete this template?')) return
    
    try {
      await templatesService.delete(id)
      showSuccess('Template deleted')
      setSelectedTemplate(null)
      loadTemplates()
    } catch (error) {
      showError(error.message || 'Failed to delete template')
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
      render: (val) => new Date(val).toLocaleDateString()
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
        title="Templates"
        footer={
          <div className="text-xs text-text-secondary">
            {templates.length} templates
          </div>
        }
      >
        <div className="p-4">
          <Button onClick={handleCreate} className="w-full mb-3">
            <Plus size={18} />
            Create Template
          </Button>
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : templates.length === 0 ? (
            <EmptyState
              icon={List}
              title="No templates"
              description="Create your first certificate template"
              action={{
                label: 'Create Template',
                onClick: handleCreate
              }}
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
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'Templates' },
          { label: selectedTemplate?.name || '...' }
        ]}
        title={selectedTemplate?.name || 'Select a template'}
        actions={selectedTemplate && (
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
              <h3 className="text-sm font-semibold text-text-primary mb-4">Subject Template</h3>
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
                  label="Locality (L)"
                  value={formData.subject?.L || ''}
                  onChange={(e) => updateSubject('L', e.target.value)}
                  disabled={!editing}
                  placeholder="San Francisco"
                />
                <Input
                  label="Organization (O)"
                  value={formData.subject?.O || ''}
                  onChange={(e) => updateSubject('O', e.target.value)}
                  disabled={!editing}
                  placeholder="Example Corp"
                />
                <Input
                  label="Organizational Unit (OU)"
                  value={formData.subject?.OU || ''}
                  onChange={(e) => updateSubject('OU', e.target.value)}
                  disabled={!editing}
                  placeholder="IT Department"
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

            {/* Key Usage */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Key Usage</h3>
              <div className="space-y-2">
                {keyUsageOptions.map(usage => (
                  <label key={usage} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.key_usage?.includes(usage) || false}
                      onChange={(e) => {
                        const newUsage = e.target.checked
                          ? [...(formData.key_usage || []), usage]
                          : (formData.key_usage || []).filter(u => u !== usage)
                        updateFormData('key_usage', newUsage)
                      }}
                      disabled={!editing}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{usage}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Extended Key Usage */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Extended Key Usage</h3>
              <div className="space-y-2">
                {extendedKeyUsageOptions.map(usage => (
                  <label key={usage} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.extended_key_usage?.includes(usage) || false}
                      onChange={(e) => {
                        const newUsage = e.target.checked
                          ? [...(formData.extended_key_usage || []), usage]
                          : (formData.extended_key_usage || []).filter(u => u !== usage)
                        updateFormData('extended_key_usage', newUsage)
                      }}
                      disabled={!editing}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{usage}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </DetailsPanel>
    </>
  )
}
