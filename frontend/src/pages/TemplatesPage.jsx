/**
 * TemplatesPage - Certificate template management
 * Pattern: ResponsiveLayout + ResponsiveDataTable + Modal actions
 * 
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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
      title: t('templates.deleteTemplate'),
      confirmText: t('common.delete'),
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
      { icon: Certificate, label: t('common.certificate'), value: certTemplates, variant: 'primary' },
      { icon: ShieldCheck, label: t('common.ca'), value: caTemplates, variant: 'violet' },
      { icon: FileText, label: t('common.total'), value: templates.length, variant: 'default' }
    ]
  }, [templates, getTemplateType, t])

  // ============= COLUMNS =============
  
  const columns = useMemo(() => [
    {
      key: 'name',
      header: t('templates.template'),
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
            <span className="font-medium truncate">{val || t('common.unnamed')}</span>
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
              <span className="font-medium truncate">{val || t('common.unnamed')}</span>
            </div>
            <Badge variant={type === 'ca' ? 'amber' : 'primary'} size="sm" dot>
              {type === 'ca' ? t('common.ca') : t('templates.cert')}
            </Badge>
          </div>
        )
      }
    },
    {
      key: 'type',
      header: t('common.type'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val === 'ca' ? 'amber' : 'primary'} size="sm" dot>
          {val === 'ca' ? t('common.ca') : t('common.certificate')}
        </Badge>
      )
    },
    {
      key: 'validity_days',
      header: t('common.validity'),
      priority: 3,
      hideOnMobile: true,
      sortable: true,
      mono: true,
      render: (val) => (
        <span className="text-sm text-text-secondary">
          {t('templates.validityDays', { count: val || 365 })}
        </span>
      ),
      mobileRender: (val) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">{t('common.validity')}:</span>
          <span className="text-text-secondary">{val || 365}d</span>
        </div>
      )
    },
    {
      key: 'usage_count',
      header: t('common.used'),
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <Badge variant="outline" size="sm">
          {t('templates.certsIssued', { count: val || 0 })}
        </Badge>
      )
    },
    {
      key: 'description',
      header: t('common.description'),
      hideOnMobile: true,
      render: (val) => (
        <span className="text-xs text-text-secondary truncate max-w-[200px]">
          {val || '—'}
        </span>
      )
    }
  ], [t])

  // ============= ROW ACTIONS =============
  
  const rowActions = useCallback((row) => [
    { label: t('common.edit'), icon: PencilSimple, onClick: () => { setEditingTemplate(row); setShowTemplateModal(true) } },
    { label: t('templates.duplicateTemplate'), icon: Copy, onClick: () => handleDuplicateTemplate(row) },
    { label: t('common.export'), icon: Download, onClick: () => handleExportTemplate(row) },
    ...(canDelete('templates') ? [
      { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDeleteTemplate(row) }
    ] : [])
  ], [canDelete, t])

  // ============= HELP CONTENT =============
  
  const helpContent = (
    <div className="space-y-3">
      <HelpCard title={t('common.aboutTemplates')} variant="info">
        {t('templates.aboutTemplatesDescription')}
      </HelpCard>
      <HelpCard title={t('templates.templateTypes')} variant="tip">
        <div className="space-y-1 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="primary" size="sm">{t('common.certificate')}</Badge>
            <span className="text-xs">{t('templates.endEntityCerts')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm">{t('common.ca')}</Badge>
            <span className="text-xs">{t('templates.intermediateCAs')}</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title={t('common.keyUsage')} variant="warning">
        {t('templates.keyUsageWarning')}
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
        subtitle={t('templates.certificatesIssued', { count: selectedTemplate.usage_count || 0 })}
        badge={
          <Badge variant={selectedTemplate.type === 'ca' ? 'warning' : 'primary'} size="sm">
            {selectedTemplate.type === 'ca' ? t('common.ca') : t('common.certificate')}
          </Badge>
        }
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => setShowPreviewModal(true)}>
          <Eye size={14} /> {t('common.details')}
        </Button>
        {canWrite('templates') && (
          <>
            <Button size="sm" variant="secondary" onClick={() => { setEditingTemplate(selectedTemplate); setShowTemplateModal(true) }}>
              <PencilSimple size={14} /> {t('common.edit')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleDuplicateTemplate(selectedTemplate)}>
              <Copy size={14} /> {t('common.copy')}
            </Button>
          </>
        )}
        <Button size="sm" variant="secondary" onClick={() => handleExportTemplate(selectedTemplate)}>
          <Download size={14} /> {t('common.export')}
        </Button>
        {canDelete('templates') && (
          <Button size="sm" variant="danger" onClick={() => handleDeleteTemplate(selectedTemplate)}>
            <Trash size={14} /> {t('common.delete')}
          </Button>
        )}
      </div>

      <CompactSection title={t('templates.basicInfo')}>
        <CompactGrid columns={1}>
          <CompactField autoIcon="name" label={t('common.name')} value={selectedTemplate.name} />
          <CompactField autoIcon="type" label={t('common.type')} value={selectedTemplate.type === 'ca' ? t('common.certificateAuthority') : t('common.certificate')} />
          <CompactField autoIcon="description" label={t('common.description')} value={selectedTemplate.description || '—'} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.validityPeriod')} icon={Clock}>
        <CompactGrid columns={2}>
          <CompactField autoIcon="default" label={t('common.default')} value={t('templates.validityDays', { count: selectedTemplate.validity_days || 365 })} />
          <CompactField autoIcon="maximum" label={t('templates.maximum')} value={t('templates.validityDays', { count: selectedTemplate.max_validity_days || 3650 })} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('templates.subjectTemplate')} collapsible>
        <CompactGrid columns={2}>
          <CompactField autoIcon="country" label={t('templates.country')} value={selectedTemplate.subject?.C || '—'} />
          <CompactField autoIcon="state" label={t('templates.state')} value={selectedTemplate.subject?.ST || '—'} />
          <CompactField autoIcon="organization" label={t('templates.organization')} value={selectedTemplate.subject?.O || '—'} />
          <CompactField autoIcon="commonName" label={t('templates.commonName')} value={selectedTemplate.subject?.CN || '—'} />
        </CompactGrid>
      </CompactSection>

      {(selectedTemplate.key_usage?.length > 0 || selectedTemplate.extended_key_usage?.length > 0) && (
        <CompactSection title={t('common.keyUsage')} collapsible defaultOpen={false}>
          <CompactGrid columns={1}>
            {selectedTemplate.key_usage?.length > 0 && (
              <CompactField autoIcon="keyUsage" label={t('common.keyUsage')} value={selectedTemplate.key_usage.join(', ')} />
            )}
            {selectedTemplate.extended_key_usage?.length > 0 && (
              <CompactField autoIcon="extKeyUsage" label={t('common.extKeyUsage')} value={selectedTemplate.extended_key_usage.join(', ')} />
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
        title={t('common.templates')}
        subtitle={t('templates.subtitle', { count: templates.length })}
        icon={FileText}
        stats={stats}
        helpPageKey="templates"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <FileText size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('templates.selectTemplate')}</p>
          </div>
        }
        slideOverOpen={!!selectedTemplate}
        slideOverTitle={selectedTemplate?.name || t('common.details')}
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
          searchable
          searchPlaceholder={t('templates.searchPlaceholder')}
          searchKeys={['name', 'description', 'type']}
          toolbarFilters={[
            {
              key: 'type',
              value: filterType,
              onChange: setFilterType,
              placeholder: t('common.allTypes'),
              options: [
                { value: 'certificate', label: t('common.certificate') },
                { value: 'ca', label: t('common.ca') }
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
                  {t('templates.new')}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
                  <FileArrowUp size={14} />
                  {t('common.import')}
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
          emptyTitle={t('templates.noTemplates')}
          emptyDescription={t('templates.noTemplatesDescription')}
          emptyAction={canWrite('templates') && (
            <Button onClick={() => { setEditingTemplate(null); setShowTemplateModal(true) }}>
              <Plus size={16} /> {t('templates.createTemplate')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Template Modal */}
      <Modal
        open={showTemplateModal}
        onOpenChange={(open) => { setShowTemplateModal(open); if (!open) setEditingTemplate(null) }}
        title={editingTemplate ? t('templates.editTemplate') : t('templates.createTemplate')}
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
        title={t('templates.importTemplate')}
        size="md"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('templates.importDescription')}
          </p>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">{t('templates.templateFile')}</label>
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
            <span className="text-xs text-text-secondary">{t('templates.orPasteJson')}</span>
            <div className="flex-1 border-t border-border"></div>
          </div>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">{t('templates.pasteJsonContent')}</label>
            <textarea
              value={importJson}
              onChange={(e) => { setImportJson(e.target.value); setImportFile(null); if (fileRef.current) fileRef.current.value = '' }}
              placeholder='{"name": "My Template", "validity_days": 365, ...}'
              rows={6}
              className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-sm text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
            />
          </div>
          
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleImportTemplate} disabled={importing || (!importFile && !importJson.trim())}>
              {importing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
              {t('templates.importTemplate')}
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
  const { t } = useTranslation()
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
          label={t('templates.templateName')}
          value={formData.name}
          onChange={(e) => setFormData(p => ({ ...p, name: e.target.value }))}
          placeholder={t('templates.namePlaceholder')}
          required
        />
        <Select
          label={t('common.type')}
          value={formData.type}
          onChange={(val) => setFormData(p => ({ ...p, type: val }))}
          options={[
            { value: 'certificate', label: t('common.certificate') },
            { value: 'ca', label: t('common.certificateAuthority') }
          ]}
        />
      </div>

      <Textarea
        label={t('common.description')}
        value={formData.description}
        onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))}
        placeholder={t('templates.descriptionPlaceholder')}
        rows={2}
      />

      {/* Validity */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label={t('templates.defaultValidity')}
          type="number"
          value={formData.validity_days}
          onChange={(e) => setFormData(p => ({ ...p, validity_days: parseInt(e.target.value) || 365 }))}
        />
        <Input
          label={t('templates.maxValidity')}
          type="number"
          value={formData.max_validity_days}
          onChange={(e) => setFormData(p => ({ ...p, max_validity_days: parseInt(e.target.value) || 3650 }))}
        />
      </div>

      {/* Subject Template */}
      <div className="border-t border-border pt-4">
        <h4 className="text-sm font-medium text-text-primary mb-3">{t('templates.subjectTemplate')}</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('templates.country')}
            value={formData.subject.C}
            onChange={(e) => updateSubject('C', e.target.value)}
            placeholder={t('common.countryPlaceholder')}
          />
          <Input
            label={t('templates.state')}
            value={formData.subject.ST}
            onChange={(e) => updateSubject('ST', e.target.value)}
            placeholder={t('common.statePlaceholder')}
          />
          <Input
            label={t('templates.organization')}
            value={formData.subject.O}
            onChange={(e) => updateSubject('O', e.target.value)}
            placeholder={t('templates.orgPlaceholder')}
          />
          <Input
            label={t('templates.commonName')}
            value={formData.subject.CN}
            onChange={(e) => updateSubject('CN', e.target.value)}
            placeholder={t('templates.cnPlaceholder')}
          />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={loading || !formData.name.trim()}>
          {loading ? <LoadingSpinner size="sm" /> : (template ? t('common.update') : t('common.create'))}
        </Button>
      </div>
    </form>
  )
}
