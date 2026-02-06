/**
 * TemplatesPage - Certificate template management
 * Pattern: ResponsiveLayout + ResponsiveDataTable + Modal actions
 * 
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { 
  FileText, Plus, Copy, Trash, Download, FileArrowUp, PencilSimple,
  Certificate, ShieldCheck, Clock, Eye
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Input, Select, Textarea,
  HelpCard, LoadingSpinner, TemplatePreviewModal,
  CompactSection, CompactGrid, CompactField, CompactHeader
} from '../components'
import { templatesService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'

export default function TemplatesPage() {
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const fileRef = useRef(null)
  
  // Data
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  
  // Selection
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  
  // Modals
  const [showTemplateModal, setShowTemplateModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState(null)
  
  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // Filters
  const [filterType, setFilterType] = useState('')
  
  // Import state
  const [importFile, setImportFile] = useState(null)
  const [importJson, setImportJson] = useState('')
  const [importing, setImporting] = useState(false)

  // Load data
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const res = await templatesService.getAll()
      setTemplates(res.data || [])
    } catch (error) {
      showError(ERRORS.LOAD_FAILED.TEMPLATES)
    } finally {
      setLoading(false)
    }
  }

  // Get template type
  const getTemplateType = useCallback((t) => {
    if (t.type) return t.type
    const name = (t.name || '').toLowerCase()
    if (name.includes('ca') || name.includes('authority') || t.is_ca || t.basic_constraints?.ca) {
      return 'ca'
    }
    return 'certificate'
  }, [])

  // ============= ACTIONS =============
  
  const handleCreateTemplate = async (data) => {
    try {
      const created = await templatesService.create(data)
      showSuccess(SUCCESS.CREATE.TEMPLATE)
      setShowTemplateModal(false)
      setEditingTemplate(null)
      loadData()
      setSelectedTemplate(created)
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.TEMPLATE)
    }
  }

  const handleUpdateTemplate = async (data) => {
    try {
      await templatesService.update(editingTemplate.id, data)
      showSuccess(SUCCESS.UPDATE.TEMPLATE)
      setShowTemplateModal(false)
      setEditingTemplate(null)
      loadData()
      if (selectedTemplate?.id === editingTemplate.id) {
        setSelectedTemplate({ ...selectedTemplate, ...data })
      }
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.TEMPLATE)
    }
  }

  const handleDeleteTemplate = async (template) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.TEMPLATE, {
      title: CONFIRM.DELETE.TITLE,
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await templatesService.delete(template.id)
      showSuccess(SUCCESS.DELETE.TEMPLATE)
      if (selectedTemplate?.id === template.id) setSelectedTemplate(null)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.TEMPLATE)
    }
  }

  const handleDuplicateTemplate = async (template) => {
    try {
      const duplicated = await templatesService.duplicate(template.id)
      showSuccess(SUCCESS.DUPLICATE.TEMPLATE)
      loadData()
      setSelectedTemplate(duplicated)
    } catch (error) {
      showError(error.message || ERRORS.DUPLICATE_FAILED.TEMPLATE)
    }
  }

  const handleExportTemplate = async (template) => {
    try {
      const data = await templatesService.export(template.id)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${template.name || 'template'}.json`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(SUCCESS.EXPORT.TEMPLATE)
    } catch (error) {
      showError(error.message || ERRORS.EXPORT_FAILED.TEMPLATE)
    }
  }

  const handleImportTemplate = async () => {
    if (!importFile && !importJson.trim()) return
    setImporting(true)
    try {
      let templateData
      if (importFile) {
        const text = await importFile.text()
        templateData = JSON.parse(text)
      } else {
        templateData = JSON.parse(importJson)
      }
      await templatesService.create(templateData)
      showSuccess(SUCCESS.IMPORT.TEMPLATE)
      setShowImportModal(false)
      setImportFile(null)
      setImportJson('')
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.IMPORT_FAILED.TEMPLATE)
    } finally {
      setImporting(false)
    }
  }

  // ============= FILTERED DATA =============
  
  const filteredTemplates = useMemo(() => {
    let result = templates.map(t => ({
      ...t,
      type: getTemplateType(t)
    }))
    if (filterType) {
      result = result.filter(t => t.type === filterType)
    }
    return result
  }, [templates, filterType, getTemplateType])

  // ============= STATS =============
  
  const stats = useMemo(() => {
    const certTemplates = templates.filter(t => getTemplateType(t) === 'certificate').length
    const caTemplates = templates.filter(t => getTemplateType(t) === 'ca').length
    return [
      { icon: Certificate, label: 'Certificate', value: certTemplates, variant: 'primary' },
      { icon: ShieldCheck, label: 'CA', value: caTemplates, variant: 'violet' },
      { icon: FileText, label: 'Total', value: templates.length, variant: 'default' }
    ]
  }, [templates, getTemplateType])

  // ============= COLUMNS =============
  
  const columns = useMemo(() => [
    {
      key: 'name',
      header: 'Template',
      priority: 1,
      sortable: true,
      render: (val, row) => {
        const type = getTemplateType(row)
        const iconClass = type === 'ca' 
          ? 'icon-bg-amber' 
          : 'icon-bg-blue'
        return (
          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${iconClass}`}>
              {type === 'ca' ? <ShieldCheck size={14} weight="duotone" /> : <FileText size={14} weight="duotone" />}
            </div>
            <span className="font-medium truncate">{val || 'Unnamed'}</span>
          </div>
        )
      },
      mobileRender: (val, row) => {
        const type = getTemplateType(row)
        const iconClass = type === 'ca' ? 'icon-bg-amber' : 'icon-bg-blue'
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${iconClass}`}>
                {type === 'ca' ? <ShieldCheck size={14} weight="duotone" /> : <FileText size={14} weight="duotone" />}
              </div>
              <span className="font-medium truncate">{val || 'Unnamed'}</span>
            </div>
            <Badge variant={type === 'ca' ? 'amber' : 'primary'} size="sm" dot>
              {type === 'ca' ? 'CA' : 'Cert'}
            </Badge>
          </div>
        )
      }
    },
    {
      key: 'type',
      header: 'Type',
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val === 'ca' ? 'amber' : 'primary'} size="sm" dot>
          {val === 'ca' ? 'CA' : 'Certificate'}
        </Badge>
      )
    },
    {
      key: 'validity_days',
      header: 'Validity',
      priority: 3,
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <span className="text-sm text-text-secondary">
          {val || 365} days
        </span>
      ),
      mobileRender: (val) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">Validity:</span>
          <span className="text-text-secondary">{val || 365}d</span>
        </div>
      )
    },
    {
      key: 'usage_count',
      header: 'Used',
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <Badge variant="outline" size="sm">
          {val || 0} certs
        </Badge>
      )
    },
    {
      key: 'description',
      header: 'Description',
      hideOnMobile: true,
      render: (val) => (
        <span className="text-xs text-text-secondary truncate max-w-[200px]">
          {val || '—'}
        </span>
      )
    }
  ], [])

  // ============= ROW ACTIONS =============
  
  const rowActions = useCallback((row) => [
    { label: 'Edit', icon: PencilSimple, onClick: () => { setEditingTemplate(row); setShowTemplateModal(true) } },
    { label: 'Duplicate', icon: Copy, onClick: () => handleDuplicateTemplate(row) },
    { label: 'Export', icon: Download, onClick: () => handleExportTemplate(row) },
    ...(canDelete('templates') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDeleteTemplate(row) }
    ] : [])
  ], [canDelete])

  // ============= HELP CONTENT =============
  
  const helpContent = (
    <div className="space-y-3">
      <HelpCard title="About Templates" variant="info">
        Certificate templates define default values for certificate issuance.
        Use them to standardize certificate properties across your organization.
      </HelpCard>
      <HelpCard title="Template Types" variant="tip">
        <div className="space-y-1 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="primary" size="sm">Certificate</Badge>
            <span className="text-xs">End-entity certs (servers, users)</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm">CA</Badge>
            <span className="text-xs">Intermediate CAs</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title="Key Usage" variant="warning">
        Ensure Key Usage and Extended Key Usage match your certificate's intended purpose.
      </HelpCard>
    </div>
  )

  // ============= DETAIL PANEL =============
  
  const detailContent = selectedTemplate && (
    <div className="p-3 space-y-4">
      <CompactHeader
        icon={FileText}
        iconClass={selectedTemplate.type === 'ca' ? "bg-accent-warning/20" : "bg-accent-primary/20"}
        title={selectedTemplate.name}
        subtitle={`${selectedTemplate.usage_count || 0} certificates issued`}
        badge={
          <Badge variant={selectedTemplate.type === 'ca' ? 'warning' : 'primary'} size="sm">
            {selectedTemplate.type === 'ca' ? 'CA' : 'Certificate'}
          </Badge>
        }
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => setShowPreviewModal(true)}>
          <Eye size={14} /> Preview
        </Button>
        {canWrite('templates') && (
          <>
            <Button size="sm" variant="secondary" onClick={() => { setEditingTemplate(selectedTemplate); setShowTemplateModal(true) }}>
              <PencilSimple size={14} /> Edit
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleDuplicateTemplate(selectedTemplate)}>
              <Copy size={14} /> Duplicate
            </Button>
          </>
        )}
        <Button size="sm" variant="secondary" onClick={() => handleExportTemplate(selectedTemplate)}>
          <Download size={14} /> Export
        </Button>
        {canDelete('templates') && (
          <Button size="sm" variant="danger" onClick={() => handleDeleteTemplate(selectedTemplate)}>
            <Trash size={14} /> Delete
          </Button>
        )}
      </div>

      <CompactSection title="Basic Information">
        <CompactGrid columns={1}>
          <CompactField label="Name" value={selectedTemplate.name} />
          <CompactField label="Type" value={selectedTemplate.type === 'ca' ? 'Certificate Authority' : 'Certificate'} />
          <CompactField label="Description" value={selectedTemplate.description || '—'} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title="Validity Period" icon={Clock}>
        <CompactGrid columns={2}>
          <CompactField label="Default" value={`${selectedTemplate.validity_days || 365} days`} />
          <CompactField label="Maximum" value={`${selectedTemplate.max_validity_days || 3650} days`} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title="Subject Template" collapsible>
        <CompactGrid columns={2}>
          <CompactField label="Country (C)" value={selectedTemplate.subject?.C || '—'} />
          <CompactField label="State (ST)" value={selectedTemplate.subject?.ST || '—'} />
          <CompactField label="Organization (O)" value={selectedTemplate.subject?.O || '—'} />
          <CompactField label="Common Name (CN)" value={selectedTemplate.subject?.CN || '—'} />
        </CompactGrid>
      </CompactSection>

      {(selectedTemplate.key_usage?.length > 0 || selectedTemplate.extended_key_usage?.length > 0) && (
        <CompactSection title="Key Usage" collapsible defaultOpen={false}>
          <CompactGrid columns={1}>
            {selectedTemplate.key_usage?.length > 0 && (
              <CompactField label="Key Usage" value={selectedTemplate.key_usage.join(', ')} />
            )}
            {selectedTemplate.extended_key_usage?.length > 0 && (
              <CompactField label="Extended Key Usage" value={selectedTemplate.extended_key_usage.join(', ')} />
            )}
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )

  // ============= RENDER =============

  return (
    <>
      <ResponsiveLayout
        title="Templates"
        subtitle={`${templates.length} template${templates.length !== 1 ? 's' : ''}`}
        icon={FileText}
        stats={stats}
        helpPageKey="templates"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <FileText size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">Select a template to view details</p>
          </div>
        }
        slideOverOpen={!!selectedTemplate}
        slideOverTitle={selectedTemplate?.name || 'Template Details'}
        slideOverContent={detailContent}
        slideOverWidth="lg"
        onSlideOverClose={() => setSelectedTemplate(null)}
      >
        <ResponsiveDataTable
          data={filteredTemplates}
          columns={columns}
          loading={loading}
          onRowClick={setSelectedTemplate}
          selectedId={selectedTemplate?.id}
          rowActions={rowActions}
          searchable
          searchPlaceholder="Search templates..."
          searchKeys={['name', 'description', 'type']}
          toolbarFilters={[
            {
              key: 'type',
              value: filterType,
              onChange: setFilterType,
              placeholder: LABELS.FILTERS.ALL_TYPES,
              options: [
                { value: 'certificate', label: 'Certificate' },
                { value: 'ca', label: 'CA' }
              ]
            }
          ]}
          toolbarActions={canWrite('templates') && (
            isMobile ? (
              <Button size="lg" onClick={() => { setEditingTemplate(null); setShowTemplateModal(true) }} className="w-11 h-11 p-0">
                <Plus size={22} weight="bold" />
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => { setEditingTemplate(null); setShowTemplateModal(true) }}>
                  <Plus size={14} weight="bold" />
                  New
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
                  <FileArrowUp size={14} />
                  Import
                </Button>
              </div>
            )
          )}
          sortable
          defaultSort={{ key: 'name', direction: 'asc' }}
          pagination={{
            page,
            total: filteredTemplates.length,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={FileText}
          emptyTitle="No templates"
          emptyDescription="Create your first template to get started"
          emptyAction={canWrite('templates') && (
            <Button onClick={() => { setEditingTemplate(null); setShowTemplateModal(true) }}>
              <Plus size={16} /> New Template
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Template Modal */}
      <Modal
        open={showTemplateModal}
        onOpenChange={(open) => { setShowTemplateModal(open); if (!open) setEditingTemplate(null) }}
        title={editingTemplate ? 'Edit Template' : 'Create Template'}
        size="lg"
      >
        <TemplateForm
          template={editingTemplate}
          onSubmit={editingTemplate ? handleUpdateTemplate : handleCreateTemplate}
          onCancel={() => { setShowTemplateModal(false); setEditingTemplate(null) }}
        />
      </Modal>

      {/* Import Modal */}
      <Modal
        open={showImportModal}
        onOpenChange={setShowImportModal}
        title="Import Template"
        size="md"
      >
        <div className="p-4 space-y-4">
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
          
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>Cancel</Button>
            <Button onClick={handleImportTemplate} disabled={importing || (!importFile && !importJson.trim())}>
              {importing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
              Import Template
            </Button>
          </div>
        </div>
      </Modal>
      
      {/* Template Preview Modal */}
      <TemplatePreviewModal
        open={showPreviewModal}
        onClose={() => setShowPreviewModal(false)}
        template={selectedTemplate}
      />
    </>
  )
}

// ============= TEMPLATE FORM =============

function TemplateForm({ template, onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'certificate',
    validity_days: 365,
    max_validity_days: 3650,
    subject: { C: '', ST: '', L: '', O: '', OU: '', CN: '' },
    key_usage: [],
    extended_key_usage: []
  })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (template) {
      setFormData({
        name: template.name || '',
        description: template.description || '',
        type: template.type || 'certificate',
        validity_days: template.validity_days || 365,
        max_validity_days: template.max_validity_days || 3650,
        subject: template.subject || { C: '', ST: '', L: '', O: '', OU: '', CN: '' },
        key_usage: template.key_usage || [],
        extended_key_usage: template.extended_key_usage || []
      })
    } else {
      setFormData({
        name: '',
        description: '',
        type: 'certificate',
        validity_days: 365,
        max_validity_days: 3650,
        subject: { C: '', ST: '', L: '', O: '', OU: '', CN: '' },
        key_usage: [],
        extended_key_usage: []
      })
    }
  }, [template])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.name.trim()) return
    setLoading(true)
    try {
      await onSubmit(formData)
    } finally {
      setLoading(false)
    }
  }

  const updateSubject = (field, value) => {
    setFormData(prev => ({
      ...prev,
      subject: { ...prev.subject, [field]: value }
    }))
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      {/* Basic Info */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Template Name"
          value={formData.name}
          onChange={(e) => setFormData(p => ({ ...p, name: e.target.value }))}
          placeholder="e.g., Web Server Certificate"
          required
        />
        <Select
          label="Type"
          value={formData.type}
          onChange={(val) => setFormData(p => ({ ...p, type: val }))}
          options={[
            { value: 'certificate', label: 'Certificate' },
            { value: 'ca', label: 'Certificate Authority' }
          ]}
        />
      </div>

      <Textarea
        label="Description"
        value={formData.description}
        onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))}
        placeholder="Brief description of this template"
        rows={2}
      />

      {/* Validity */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Default Validity (days)"
          type="number"
          value={formData.validity_days}
          onChange={(e) => setFormData(p => ({ ...p, validity_days: parseInt(e.target.value) || 365 }))}
        />
        <Input
          label="Maximum Validity (days)"
          type="number"
          value={formData.max_validity_days}
          onChange={(e) => setFormData(p => ({ ...p, max_validity_days: parseInt(e.target.value) || 3650 }))}
        />
      </div>

      {/* Subject Template */}
      <div className="border-t border-border pt-4">
        <h4 className="text-sm font-medium text-text-primary mb-3">Subject Template</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Country (C)"
            value={formData.subject.C}
            onChange={(e) => updateSubject('C', e.target.value)}
            placeholder="US"
          />
          <Input
            label="State (ST)"
            value={formData.subject.ST}
            onChange={(e) => updateSubject('ST', e.target.value)}
            placeholder="California"
          />
          <Input
            label="Organization (O)"
            value={formData.subject.O}
            onChange={(e) => updateSubject('O', e.target.value)}
            placeholder="Example Corp"
          />
          <Input
            label="Common Name (CN)"
            value={formData.subject.CN}
            onChange={(e) => updateSubject('CN', e.target.value)}
            placeholder="*.example.com"
          />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading || !formData.name.trim()}>
          {loading ? <LoadingSpinner size="sm" /> : (template ? 'Update' : 'Create')}
        </Button>
      </div>
    </form>
  )
}
