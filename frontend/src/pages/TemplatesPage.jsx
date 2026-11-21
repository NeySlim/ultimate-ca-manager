/**
 * Templates: the mockup's templates module, a simplePage() list (here Source, Validité, Clé par
 * défaut, Utilisations, État) with its one-object dock. What the product has more (search, the
 * source filter, sort, create, import, edit, duplicate, activate, export, delete, the preview and
 * the subject, extensions and enrollment of a template) takes the page head, the toolbar, the dock
 * actions with their « ⋯ » menu, and further dock tabs.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { FileArrowUp, Warning } from '@phosphor-icons/react'
import {
  Button, Modal, Input, Select, Textarea, LoadingSpinner, TemplatePreviewModal,
} from '../components'
import {
  Zone, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, FilterSelect, ListView, Dock, DockBody, Section, Props,
  LoadError, LoadCause, EmptyBlock, NoMatch,
} from '../components/atelier'
import { templatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, usePersistedState, useCRUDPage } from '../hooks'
import { downloadBlob } from '../lib/utils'
import { VALIDITY } from '../constants/config'
import { KEY_ALGORITHMS, isUsable, groupedOptions } from '../lib/keyAlgorithms'
import { keyLabel } from '../lib/certificateDetail'
import { useKeyPlatform } from '../lib/policyAlgorithms'
import { BrainpoolNotice } from '../components/BrainpoolNotice'
import { ekuService } from '../services/eku.service'
import {
  buildExtensionsTemplate, qcFormFromStored, emptyQcForm, parsePolicyOids,
  QC_TYPES, QC_SEMANTICS, ETSI_POLICY_PRESETS
} from '../lib/templateExtensions'
import { customExtensionsPayload, rowsFromStored, truncateHex } from '../lib/customExtensions'
import { CustomExtensionsEditor } from '../components/CustomExtensionsEditor'
import { CN_PATTERN_VARIABLES, cnPatternNonUnique, cnPatternSource } from '../lib/cnPattern'
import { CertMenu } from './certificates/inspector/CertMenu'
import { PhoneMoreActions } from './pki/PhoneMoreActions'

export default function TemplatesPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning, showConfirm } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()
  const fileRef = useRef(null)
  
  // Hook: CRUD state
  const loadFn = useCallback(async () => {
    setLoadError(null)
    try {
      const res = await templatesService.getAll()
      return res.data || []
    } catch (error) {
      setLoadError(error)
      throw error
    }
  }, [])
  const {
    items: templates,
    loading,
    selectedItem: selectedTemplate, setSelectedItem: setSelectedTemplate,
    showModal: showTemplateModal, setShowModal: setShowTemplateModal,
    editing: editingTemplate, setEditing: setEditingTemplate,
    loadData,
  } = useCRUDPage({ loadFn, loadErrorMsg: t('messages.errors.loadFailed.templates') })

  // Modals (page-specific)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showPreviewModal, setShowPreviewModal] = useState(false)

  // List: the search, the source and state filters (kept), the sort, the open tab and the menu
  const [query, setQuery] = useState('')
  const [source, setSource] = usePersistedState('ucm-templates-source', '')
  const [state, setState] = usePersistedState('ucm-templates-state', '')
  const [sort, setSort] = useState({ key: 'name', asc: true })
  const [section, setSection] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const [loadError, setLoadError] = useState(null)

  // Import state
  const [importFile, setImportFile] = useState(null)
  const [importJson, setImportJson] = useState('')
  const [importing, setImporting] = useState(false)

  // ============= ACTIONS =============
  
  const handleCreateTemplate = async (data) => {
    try {
      const created = await templatesService.create(data)
      showSuccess(t('messages.success.create.template'))
      setShowTemplateModal(false)
      setEditingTemplate(null)
      loadData()
      setSelectedTemplate(created)
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.template'))
    }
  }

  const handleUpdateTemplate = async (data) => {
    try {
      await templatesService.update(editingTemplate.id, data)
      showSuccess(t('messages.success.update.template'))
      setShowTemplateModal(false)
      setEditingTemplate(null)
      loadData()
      if (selectedTemplate?.id === editingTemplate.id) {
        setSelectedTemplate({ ...selectedTemplate, ...data })
      }
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.template'))
    }
  }

  const handleDeleteTemplate = async (template) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.template'), {
      title: t('templates.deleteTemplate'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await templatesService.delete(template.id)
      showSuccess(t('messages.success.delete.template'))
      if (selectedTemplate?.id === template.id) setSelectedTemplate(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.template'))
    }
  }

  const handleDuplicateTemplate = async (template) => {
    try {
      const duplicated = await templatesService.duplicate(template.id)
      showSuccess(t('messages.success.duplicate.template'))
      loadData()
      setSelectedTemplate(duplicated)
    } catch (error) {
      showError(error.message || t('messages.errors.duplicateFailed.template'))
    }
  }

  const handleToggleActive = async (template) => {
    const active = template.is_active === false
    try {
      const res = await templatesService.update(template.id, { is_active: active })
      const updated = res?.data || res
      showSuccess(t(active ? 'templates.activated' : 'templates.deactivated'))
      loadData()
      if (updated?.id) setSelectedTemplate({ ...template, ...updated })
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.template'))
    }
  }

  const handleExportTemplate = async (template) => {
    try {
      const data = await templatesService.export(template.id)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      downloadBlob(blob, `${template.name || 'template'}.json`)
      showSuccess(t('messages.success.export.template'))
    } catch (error) {
      showError(error.message || t('messages.errors.exportFailed.template'))
    }
  }

  const handleImportTemplate = async () => {
    if (!importFile && !importJson.trim()) return
    setImporting(true)
    try {
      // The import endpoint reads the export format, one template or an array
      const formData = new FormData()
      if (importFile) {
        formData.append('file', importFile)
      } else {
        formData.append('json_content', importJson)
      }
      const res = await templatesService.import(formData)
      const { imported = 0, updated = 0, skipped = 0, skipped_items: items = [] } = res?.data || {}
      if (skipped > 0 || imported + updated === 0) {
        const summary = t('templates.importSummary', { imported, updated, skipped })
        // One skipped template per line, under the translated counts
        showWarning([summary, ...items].join('\n'))
      } else {
        showSuccess(t('messages.success.import.template'))
      }
      if (imported + updated > 0) {
        setShowImportModal(false)
        setImportFile(null)
        setImportJson('')
        loadData()
      }
    } catch (error) {
      showError(error.message || t('messages.errors.importFailed.template'))
    } finally {
      setImporting(false)
    }
  }

  const dialogs = (
    <>
      {/* Template Modal */}
      <Modal
        open={showTemplateModal}
        onOpenChange={(open) => { setShowTemplateModal(open); if (!open) setEditingTemplate(null) }}
        title={editingTemplate ? t('templates.editTemplate') : t('templates.createTemplate')}
        size="xl"
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
              className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-on-accent hover:file:bg-accent-primary-op80"
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
            <Button type="button" variant="secondary" onClick={() => setShowImportModal(false)}>{t('common.cancel')}</Button>
            <Button type="button" onClick={handleImportTemplate} disabled={importing || (!importFile && !importJson.trim())}>
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

  // ============= LIST =============

  const tplState = (tpl) => (tpl.is_active === false ? 'inactive' : 'active')
  const tplPill = (tpl) => (tplState(tpl) === 'active'
    ? <Pill label={t('templates.module.states.active')} tone="good" />
    : <Pill label={t('templates.module.states.inactive')} tone="muted" />)
  const tplSource = (tpl) => (tpl.is_system ? t('templates.system') : t('templates.custom'))
  const tplValidity = (tpl) => t('templates.module.validity', { count: tpl.validity_days || VALIDITY.TEMPLATE_DEFAULT_DAYS })
  const tplKey = (tpl) => keyLabel(tpl.key_type) || '—'
  const tplUses = (tpl) => t('templates.module.usesCount', { count: tpl.usage_count || 0 })
  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return templates.filter((tpl) => (!source || (source === 'system') === !!tpl.is_system)
      && (!q || [tpl.name, tpl.description, tplSource(tpl)].some((v) => String(v || '').toLowerCase().includes(q))))
  }, [templates, source, query]) // eslint-disable-line react-hooks/exhaustive-deps
  const present = ['active', 'inactive'].filter((s) => templates.some((tpl) => tplState(tpl) === s))
  const active = present.includes(state) ? state : ''
  const rows = useMemo(() => {
    const list = searched.filter((tpl) => !active || tplState(tpl) === active)
    const value = { name: (x) => String(x.name || '').toLowerCase(), validity_days: (x) => x.validity_days || 0, usage_count: (x) => x.usage_count || 0 }[sort.key]
    return [...list].sort((a, b) => {
      const va = value(a)
      const vb = value(b)
      return (va < vb ? -1 : va > vb ? 1 : 0) * (sort.asc ? 1 : -1)
    })
  }, [searched, active, sort])
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    ...present.map((s) => ({ id: s, label: t(`templates.module.states.${s}`), count: searched.filter((tpl) => tplState(tpl) === s).length })),
  ]
  const narrowed = Boolean(query.trim() || source || active)
  const write = canWrite('templates')
  const create = write ? { label: t('templates.createTemplate'), icon: 'plus', onClick: () => { setEditingTemplate(null); setShowTemplateModal(true) }, primary: true } : undefined

  // An open system template leaves the dock when the system templates are filtered out
  useEffect(() => {
    if (selectedTemplate && source === 'custom' && selectedTemplate.is_system) setSelectedTemplate(null)
  }, [source, selectedTemplate, setSelectedTemplate])

  // ============= DOCK =============

  const open = selectedTemplate ? (templates.find((x) => x.id === selectedTemplate.id) ? { ...templates.find((x) => x.id === selectedTemplate.id), ...selectedTemplate } : selectedTemplate) : null
  const openTemplate = (tpl) => {
    if (tpl.id !== selectedTemplate?.id) setSection('overview')
    setSelectedTemplate(tpl)
  }
  const ext = open?.extensions_template || {}
  const pinned = Object.entries(open?.pinned_subject_fields || {})
  const onOff = (v) => (v ? t('common.enabled') : t('common.disabled'))
  const markers = open ? [
    open.ad_derived_subject && t('templates.adDerivedBadge'),
    open.autoenroll_enabled && t('templates.autoenrollBadge'),
    open.allowed_ad_group && t('templates.enrollAclBadge'),
    pinned.length > 0 && t('templates.pinnedSubjectBadge'),
  ].filter(Boolean) : []
  const menuItems = open ? [
    { id: 'preview', icon: 'eye', label: t('templates.module.preview'), onClick: () => setShowPreviewModal(true) },
    write && { id: 'duplicate', icon: 'copy', label: t('common.copy'), write: true, onClick: () => handleDuplicateTemplate(open) },
    write && { id: 'toggle', icon: open.is_active === false ? 'check' : 'block', label: open.is_active === false ? t('templates.activate') : t('common.deactivate'), write: true, onClick: () => handleToggleActive(open) },
    canDelete('templates') && !open.is_system && { id: 'delete', icon: 'close', label: t('common.delete'), danger: true, write: true, onClick: () => handleDeleteTemplate(open) },
  ].filter(Boolean) : []
  const list = (items, empty) => (items?.length
    ? <ul className="record-list">{items.map((x) => <li key={x}><div className="rl-main"><span className="mono">{x}</span></div></li>)}</ul>
    : <p className="muted small">{empty}</p>)

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('common.templates') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.name, icon: 'template' }]} onClose={() => setSelectedTemplate(null)}>
      <DockBody icon="template" title={open.name} badge={tplPill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: open.name })}
        sections={[['overview', t('atelier.overview')], ['subject', t('templates.module.sections.subject')], ['extensions', t('templates.module.sections.extensions')], ['enrollment', t('templates.enrollment')]]}
        actions={<>
          <Btn icon="download" id="template-export" onClick={() => handleExportTemplate(open)}>{t('common.export')}</Btn>
          {write && (
            <Btn icon="settings" id="template-edit" write disabled={open.is_system || undefined}
              title={open.is_system ? t('templates.systemNotEditable') : undefined}
              onClick={() => { setEditingTemplate(open); setShowTemplateModal(true) }}>{t('common.edit')}</Btn>
          )}
          <IconBtn quiet icon="more" title={false} label={t('templates.module.moreActions', { name: open.name })} data-template-menu={open.id} onClick={() => setMenuOpen(true)} />
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('templates.source'), tplSource(open)],
                [t('common.validity'), tplValidity(open)],
                [t('templates.module.defaultKey'), tplKey(open)],
                [t('common.digest'), open.digest || '—'],
                [t('templates.module.uses'), tplUses(open)],
                [t('atelier.state'), tplPill(open)],
                markers.length > 0 && [t('templates.module.markers'), markers.join(', ')],
              ]} />
            </Section>
            <Section title={t('atelier.summary')}><p className="summary">{open.description || t('templates.module.noDescription')}</p></Section>
          </div>
        )}
        {section === 'subject' && (
          <div className="module-detail">
            <Section title={t('templates.subjectTemplate')}>
              <Props items={[
                [t('templates.commonName'), open.dn_template?.CN || '—'],
                [t('templates.organization'), open.dn_template?.O || '—'],
                [t('common.orgUnit'), open.dn_template?.OU || '—'],
                [t('templates.country'), open.dn_template?.C || '—'],
                [t('templates.state'), open.dn_template?.ST || '—'],
                [t('common.locality'), open.dn_template?.L || '—'],
                [t('common.email'), open.dn_template?.emailAddress || '—'],
              ]} />
            </Section>
            <Section title={t('templates.module.sections.rules')}>
              <Props items={[
                [t('templates.adDerivedSubject'), onOff(open.ad_derived_subject)],
                [t('templates.cnPattern'), open.subject_cn_pattern
                  ? `${open.subject_cn_pattern}${open.subject_cn_keep_path ? ` (${t('templates.cnPatternKeepPath')})` : ''}` : '—'],
                [t('templates.enforceSanTypes'), onOff(open.enforce_san_types)],
                [t('templates.module.sanTypes'), (ext.san_types || []).join(', ') || '—'],
              ]} />
            </Section>
          </div>
        )}
        {section === 'extensions' && (
          <div className="module-detail">
            <Section title={t('details.ext.keyUsage')}>{list(ext.key_usage, t('templates.module.none'))}</Section>
            <Section title={t('details.ext.extKeyUsage')}>{list(ext.extended_key_usage, t('templates.module.none'))}</Section>
            {(ext.qc_statements || ext.certificate_policies?.length > 0) && (
              <Section title={t('templates.qc.title')}>{list([...Object.keys(ext.qc_statements || {}), ...(ext.certificate_policies || [])], t('templates.module.none'))}</Section>
            )}
            {(open.custom_extensions?.length > 0 || open.custom_extensions_error) && (
              <Section title={t('customExtensions.title')}>
                <StoredExtensionsError error={open.custom_extensions_error} />
                <ul className="record-list">
                  {(open.custom_extensions || []).map((e) => (
                    <li key={e.oid}>
                      <div className="rl-main"><strong className="mono">{e.oid}</strong><span className="rl-meta mono" title={e.value}>{truncateHex(e.value)}</span></div>
                      {e.critical && <Pill label={t('customExtensions.critical')} tone="warn" icon="warning" />}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
          </div>
        )}
        {section === 'enrollment' && (
          <div className="module-detail">
            <Section title={t('templates.enrollment')}>
              <Props items={[
                [t('templates.autoenrollEnabled'), onOff(open.autoenroll_enabled)],
                [t('templates.allowedAdGroup'), open.allowed_ad_group || t('templates.allowedAdGroupUnset')],
                [t('templates.pinnedSubjectFields'), pinned.length ? pinned.map(([k, v]) => `${k}=${v}`).join(', ') : t('templates.pinnedSubjectFieldsUnset')],
              ]} />
            </Section>
          </div>
        )}
      </DockBody>
    </Dock>
  )

  // ============= RENDER =============

  return (
    <Zone dock={dock} testId="templates-zone" after={<>
      {menuOpen && open && <CertMenu title={t('templates.module.actionsTitle')} name={open.name} items={menuItems} onClose={() => setMenuOpen(false)} />}
      {dialogs}
    </>}>
      <PageHead title={t('common.templates')} total={t('templates.module.unit', { count: templates.length })} intent={t('shell.moduleDesc.templates')}
        actions={write && <>
          <Btn icon="upload" id="template-import" write onClick={() => setShowImportModal(true)}>{t('common.import')}</Btn>
          <PhoneMoreActions title={t('common.templates')} items={[{ id: 'import', icon: 'upload', label: t('common.import'), write: true, onClick: () => setShowImportModal(true) }]} />
          <Btn tone="primary" icon="plus" id="template-new" onClick={create.onClick}>{create.label}</Btn>
        </>} />
      <ListView label={t('common.templates')} caption={t('templates.module.caption')} icon="template" rows={rows} loading={loading}
        filters={{ views, active, onChange: setState, label: t('templates.module.filterByState') }}
        toolbar={(
          <Toolbar>
            <SearchField id="template-search" name="q" label={t('templates.searchPlaceholder')} placeholder={t('templates.searchPlaceholder')} value={query} onChange={setQuery} />
            <FilterSelect id="template-source" label={t('templates.source')} value={source} onChange={setSource}
              options={[{ value: '', label: t('templates.allSources') }, { value: 'system', label: t('templates.system') }, { value: 'custom', label: t('templates.custom') }]} />
          </Toolbar>
        )}
        title={(tpl) => tpl.name || t('common.unnamed')} status={tplPill} openedId={open?.id} onOpen={openTemplate}
        sort={sort} onSort={(key) => setSort((s) => ({ key, asc: s.key === key ? !s.asc : true }))} nameSort="name"
        columns={[
          { id: 'source', label: t('templates.source'), cell: tplSource, grow: true },
          { id: 'validity', label: t('common.validity'), cell: tplValidity, sort: 'validity_days' },
          { id: 'key', label: t('templates.module.defaultKey'), cell: tplKey },
          { id: 'uses', label: t('templates.module.uses'), cell: tplUses, sort: 'usage_count' },
          { status: true },
        ]}
        error={loadError && (
          <LoadError id="templates" title={t('messages.errors.loadFailed.templates')} onRetry={loadData} journal={hasPermission?.('read:audit') ? '/audit' : undefined}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/templates', message: loadError.message }} />} />
        )}
        empty={narrowed && templates.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setQuery(''); setSource(''); setState('') }} />
        ) : (
          <EmptyBlock id="templates" icon="template" title={t('templates.noTemplates')} text={t('templates.noTemplatesDescription')} action={create} />
        )}
        footer={{ range: t('templates.module.range', { shown: rows.length, count: templates.length }) }} />
    </Zone>
  )
}

// ============= TEMPLATE FORM =============

const TEMPLATE_TYPE_OPTIONS = [
  'web_server', 'email', 'vpn_server', 'vpn_client',
  'code_signing', 'client_auth', 'ocsp_signing', 'smartcard_logon', 'custom'
]
const DIGEST_OPTIONS = ['sha256', 'sha384', 'sha512']
// The digest is the issuing CA's signing hash, whatever the leaf key: it stays editable even for an ML-DSA or EdDSA leaf.
const DEFAULT_DIGEST = 'sha256'
const KEY_USAGE_OPTIONS = [
  'digitalSignature', 'keyEncipherment', 'contentCommitment',
  'dataEncipherment', 'keyAgreement'
]
// Eight of the twenty-six purposes the backend resolves by name
// (utils/cert_extensions.EKU_NAMES, served at /api/v2/eku/known, which the
// issue form and the CSR page already read). Hard-coded here, this list made
// timeStamping, msEFS, msDocumentSigning, msRemoteDesktop, the code-signing
// purposes and the rest unreachable from the template editor although the
// server accepts every one of them. Kept only as the answer for a browser
// that cannot reach the catalog.
const EXT_KEY_USAGE_FALLBACK = [
  'serverAuth', 'clientAuth', 'codeSigning',
  'emailProtection', 'ipsecEndSystem', 'ipsecUser', 'OCSPSigning',
  'msSmartcardLogin'
]
const SAN_TYPE_OPTIONS = ['dns', 'ip', 'email', 'uri', 'upn']
// Reuse the Issue Certificate form's SAN type labels (already in every locale)
const SAN_TYPE_LABEL_KEYS = {
  dns: 'certificates.sanDns',
  ip: 'certificates.sanIp',
  email: 'certificates.sanEmail',
  uri: 'certificates.sanUri',
  upn: 'certificates.sanUpn',
}

// KU/EKU/SAN presets applied when the template type changes (mirrors system templates)
const TYPE_EXTENSION_DEFAULTS = {
  web_server:   { key_usage: ['digitalSignature', 'keyEncipherment'], extended_key_usage: ['serverAuth'], san_types: ['dns', 'ip'] },
  email:        { key_usage: ['digitalSignature', 'keyEncipherment', 'dataEncipherment'], extended_key_usage: ['emailProtection'], san_types: ['email'] },
  vpn_server:   { key_usage: ['digitalSignature', 'keyEncipherment'], extended_key_usage: ['serverAuth', 'ipsecEndSystem'], san_types: ['dns', 'ip'] },
  vpn_client:   { key_usage: ['digitalSignature', 'keyEncipherment'], extended_key_usage: ['clientAuth', 'ipsecUser'], san_types: ['dns', 'email', 'upn'] },
  code_signing: { key_usage: ['digitalSignature'], extended_key_usage: ['codeSigning'], san_types: [] },
  client_auth:  { key_usage: ['digitalSignature', 'keyEncipherment'], extended_key_usage: ['clientAuth'], san_types: ['dns', 'email', 'upn'] },
  ocsp_signing: { key_usage: ['digitalSignature'], extended_key_usage: ['OCSPSigning'], san_types: [] },
  smartcard_logon: { key_usage: ['digitalSignature', 'keyEncipherment'], extended_key_usage: ['clientAuth', 'msSmartcardLogin'], san_types: ['upn', 'email'] },
}

function buildInitialState(template) {
  if (!template) {
    return {
      name: '', description: '', template_type: 'web_server',
      key_type: '', digest: DEFAULT_DIGEST,
      validity_days: VALIDITY.TEMPLATE_DEFAULT_DAYS,
      subject: { C: '', ST: '', L: '', O: '', OU: '', CN: '', emailAddress: '' },
      key_usage: ['digitalSignature', 'keyEncipherment'],
      extended_key_usage: ['serverAuth'],
      san_types: ['dns', 'ip'],
      enforce_san_types: true,
      ad_derived_subject: false,
      autoenroll_enabled: false,
      allowed_ad_group: '',
      pinned_subject_fields: { O: '', OU: '', C: '', ST: '', L: '' },
      subject_cn_pattern: '',
      subject_cn_keep_path: false,
      qc: emptyQcForm(),
      policy_oids: '',
      custom_extensions: []
    }
  }
  const dn = template.dn_template || {}
  const ext = template.extensions_template || {}
  const pinned = template.pinned_subject_fields || {}
  return {
    name: template.name || '',
    description: template.description || '',
    template_type: template.template_type || 'web_server',
    key_type: template.key_type || '',
    digest: template.digest || DEFAULT_DIGEST,
    validity_days: template.validity_days || VALIDITY.TEMPLATE_DEFAULT_DAYS,
    subject: {
      C: dn.C || '', ST: dn.ST || '', L: dn.L || '',
      O: dn.O || '', OU: dn.OU || '', CN: dn.CN || '',
      emailAddress: dn.emailAddress || ''
    },
    key_usage: ext.key_usage || [],
    extended_key_usage: ext.extended_key_usage || [],
    san_types: ext.san_types || [],
    // Off for templates older than the switch: a duplicate or an edit keeps it
    enforce_san_types: template.enforce_san_types ?? true,
    ad_derived_subject: template.ad_derived_subject || false,
    autoenroll_enabled: template.autoenroll_enabled || false,
    allowed_ad_group: template.allowed_ad_group || '',
    pinned_subject_fields: {
      O: pinned.O || '', OU: pinned.OU || '', C: pinned.C || '',
      ST: pinned.ST || '', L: pinned.L || ''
    },
    subject_cn_pattern: template.subject_cn_pattern || '',
    subject_cn_keep_path: template.subject_cn_keep_path || false,
    qc: qcFormFromStored(ext.qc_statements),
    policy_oids: Array.isArray(ext.certificate_policies) ? ext.certificate_policies.join('\n') : '',
    custom_extensions: rowsFromStored(template.custom_extensions)
  }
}

function StoredExtensionsError({ error }) {
  const { t } = useTranslation()
  if (!error) return null
  return (
    <div className="p-3 rounded-lg border border-status-danger-op30 bg-status-danger-op10 text-xs text-text-secondary" role="alert"
      data-testid="custom-extensions-stored-error">
      <div>{t('customExtensions.storedInvalid')}</div>
      <div className="font-mono mt-1 break-all">{error}</div>
    </div>
  )
}

function CnPatternFields({ formData, set, checkboxCls }) {
  const { t } = useTranslation()
  const source = cnPatternSource(formData.template_type, formData.ad_derived_subject)
  const nonUnique = cnPatternNonUnique(formData.subject_cn_pattern)
  return (
    <div className="mt-4" data-testid="cn-pattern">
      <Input
        label={t('templates.cnPattern')}
        value={formData.subject_cn_pattern}
        onChange={(e) => set('subject_cn_pattern', e.target.value)}
        placeholder="{hostname}-WiFi"
        maxLength={255}
      />
      {/* Braces go in as values: i18next reads {{x}} in a string as its own variable */}
      <p className="text-xs text-text-secondary mt-1">
        {t('templates.cnPatternDescription', { open: '{{', close: '}}' })}
      </p>
      {source === 'request' ? (
        <p className="text-xs text-text-tertiary mt-1" data-testid="cn-pattern-unavailable">{t('templates.cnPatternUnavailable')}</p>
      ) : (
        <p className="text-xs text-text-secondary mt-1" data-testid="cn-pattern-variables">
          {t('templates.cnPatternVariables')}{' '}
          <span className="font-mono">{CN_PATTERN_VARIABLES[source].map(v => `{${v}}`).join(' ')}</span>
        </p>
      )}
      {nonUnique.length > 0 && (
        <p className="text-xs text-status-warning mt-1" role="note" data-testid="cn-pattern-non-unique">
          {t('templates.cnPatternNotUnique', { variables: nonUnique.join(', ') })}
        </p>
      )}
      <label className={`${checkboxCls} mt-2`}>
        <input
          type="checkbox"
          checked={formData.subject_cn_keep_path}
          onChange={(e) => set('subject_cn_keep_path', e.target.checked)}
          className="accent-accent-primary"
        />
        {t('templates.cnPatternKeepPath')}
      </label>
      <p className="text-xs text-text-secondary mt-1">{t('templates.cnPatternKeepPathDescription')}</p>
    </div>
  )
}

export function TemplateForm({ template, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState(() => buildInitialState(template))
  const [loading, setLoading] = useState(false)
  const [ekuOptions, setEkuOptions] = useState(EXT_KEY_USAGE_FALLBACK)
  const platform = useKeyPlatform()
  // The key already on the template stays listed, so FIPS mode or a key not generated yet never blanks the field.
  // ML-DSA is offered: the digest is the issuing CA's signing hash, not the leaf key's.
  // An empty key type means the server default, which the backend resolves and stores when the template is created
  const keyTypeOptions = useMemo(() => [
    // Only a template without a key can stay on the default: an update cannot unset a stored key
    ...(template?.key_type ? [] : [{ value: '', label: t('templates.keyServerDefault') }]),
    ...groupedOptions(
      KEY_ALGORITHMS.filter(a => (a.generate && isUsable(a, platform)) || a.label === formData.key_type),
      t, a => a.label),
  ], [platform, t, formData.key_type, template?.key_type])

  useEffect(() => {
    let cancelled = false
    ekuService.getKnown()
      .then((resp) => {
        const names = (resp?.data?.ekus || resp?.ekus || [])
          .map((e) => e.name)
          .filter(Boolean)
        if (!cancelled && names.length) setEkuOptions(names)
      })
      .catch(() => { /* the fallback list still lets a template be saved */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    setFormData(buildInitialState(template))
  }, [template])

  const set = (field, value) => setFormData(p => ({ ...p, [field]: value }))
  const updateSubject = (field, value) =>
    setFormData(p => ({ ...p, subject: { ...p.subject, [field]: value } }))
  const updatePinned = (field, value) =>
    setFormData(p => ({ ...p, pinned_subject_fields: { ...p.pinned_subject_fields, [field]: value } }))

  const setQc = (field, value) => setFormData(p => ({ ...p, qc: { ...p.qc, [field]: value } }))
  const updatePds = (i, field, value) => setFormData(p => ({
    ...p, qc: { ...p.qc, pds: p.qc.pds.map((e, j) => (j === i ? { ...e, [field]: value } : e)) }
  }))
  const addPolicyPreset = (oid) => setFormData(p => ({
    ...p, policy_oids: parsePolicyOids(p.policy_oids).includes(oid) ? p.policy_oids : [...parsePolicyOids(p.policy_oids), oid].join('\n')
  }))

  const toggleCheckbox = (field, item) => {
    setFormData(p => {
      const arr = p[field]
      return { ...p, [field]: arr.includes(item) ? arr.filter(v => v !== item) : [...arr, item] }
    })
  }

  const customExt = customExtensionsPayload(formData.custom_extensions)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.name.trim() || !customExt.valid) return
    setLoading(true)
    try {
      await onSubmit({
        name: formData.name,
        description: formData.description,
        template_type: formData.template_type,
        ...(formData.key_type ? { key_type: formData.key_type } : {}),
        digest: formData.digest,
        validity_days: formData.validity_days,
        dn_template: { ...formData.subject },
        extensions_template: buildExtensionsTemplate(template?.extensions_template, formData),
        enforce_san_types: formData.enforce_san_types,
        ad_derived_subject: formData.ad_derived_subject,
        autoenroll_enabled: formData.autoenroll_enabled,
        allowed_ad_group: formData.allowed_ad_group.trim(),
        pinned_subject_fields: Object.fromEntries(
          Object.entries(formData.pinned_subject_fields)
            .map(([k, v]) => [k, v.trim()])
            .filter(([, v]) => v)
        ),
        subject_cn_pattern: formData.subject_cn_pattern.trim() || null,
        subject_cn_keep_path: formData.subject_cn_keep_path,
        custom_extensions: customExt.entries
      })
    } finally {
      setLoading(false)
    }
  }

  const checkboxCls = 'flex items-center gap-1.5 text-sm text-text-primary cursor-pointer select-none'
  const sectionTitle = 'text-sm font-medium text-text-primary mb-3'

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      {/* Basic Info */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label={t('templates.templateName')}
          value={formData.name}
          onChange={(e) => set('name', e.target.value)}
          placeholder={t('templates.namePlaceholder')}
          required
        />
        <Select
          label={t('templates.templateType')}
          value={formData.template_type}
          onChange={(val) => setFormData(p => ({ ...p, template_type: val, ...(TYPE_EXTENSION_DEFAULTS[val] || {}) }))}
          options={TEMPLATE_TYPE_OPTIONS.map(v => ({ value: v, label: v.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }))}
        />
      </div>

      <Textarea
        label={t('common.description')}
        value={formData.description}
        onChange={(e) => set('description', e.target.value)}
        placeholder={t('templates.descriptionPlaceholder')}
        rows={2}
      />

      {/* Key Settings */}
      <div className="border-t border-border pt-4">
        <h4 className={sectionTitle}>{t('templates.keySettings')}</h4>
        <div className="grid grid-cols-2 gap-4">
          <Select
            label={t('common.keyType')}
            value={formData.key_type}
            onChange={(val) => set('key_type', val)}
            options={keyTypeOptions}
          />
          <Select
            label={t('common.digest')}
            value={formData.digest}
            onChange={(val) => set('digest', val)}
            options={DIGEST_OPTIONS.map(v => ({ value: v, label: v.toUpperCase() }))}
          />
        </div>
        <div className="mt-2"><BrainpoolNotice label={formData.key_type} /></div>
      </div>

      {/* Validity */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label={t('templates.defaultValidity')}
          type="number"
          value={formData.validity_days}
          onChange={(e) => set('validity_days', parseInt(e.target.value) || VALIDITY.TEMPLATE_DEFAULT_DAYS)}
        />
        <p className="text-xs text-text-tertiary self-end">{t('templates.maxValidityHint')}</p>
      </div>

      {/* Subject Template */}
      <div className="border-t border-border pt-4">
        <h4 className={sectionTitle}>{t('templates.subjectTemplate')}</h4>
        <div className="grid grid-cols-3 gap-4">
          <Input label={t('templates.country')} value={formData.subject.C} onChange={(e) => updateSubject('C', e.target.value)} placeholder="US" />
          <Input label={t('templates.state')} value={formData.subject.ST} onChange={(e) => updateSubject('ST', e.target.value)} placeholder="California" />
          <Input label={t('common.locality')} value={formData.subject.L} onChange={(e) => updateSubject('L', e.target.value)} placeholder="San Francisco" />
          <Input label={t('templates.organization')} value={formData.subject.O} onChange={(e) => updateSubject('O', e.target.value)} placeholder={t('templates.orgPlaceholder')} />
          <Input label="OU" value={formData.subject.OU} onChange={(e) => updateSubject('OU', e.target.value)} placeholder="IT Department" />
          <Input label={t('templates.commonName')} value={formData.subject.CN} onChange={(e) => updateSubject('CN', e.target.value)} placeholder={t('templates.cnPlaceholder')} />
          <div className="col-span-3">
            {/* Not type="email": copies of built-in templates hold the {email} placeholder */}
            <Input label={t('common.email')} value={formData.subject.emailAddress} onChange={(e) => updateSubject('emailAddress', e.target.value)} placeholder={t('certificates.emailPlaceholder')} />
          </div>
        </div>
        <label className={`${checkboxCls} mt-3`}>
          <input
            type="checkbox"
            checked={formData.ad_derived_subject}
            onChange={(e) => set('ad_derived_subject', e.target.checked)}
            className="accent-accent-primary"
          />
          {t('templates.adDerivedSubject')}
        </label>
        <p className="text-xs text-text-secondary mt-1">{t('templates.adDerivedSubjectDescription')}</p>
        <CnPatternFields formData={formData} set={set} checkboxCls={checkboxCls} />
      </div>

      {/* Enrollment */}
      <div className="border-t border-border pt-4">
        <h4 className={sectionTitle}>{t('templates.enrollment')}</h4>
        <label className={checkboxCls}>
          <input
            type="checkbox"
            checked={formData.autoenroll_enabled}
            onChange={(e) => set('autoenroll_enabled', e.target.checked)}
            className="accent-accent-primary"
          />
          {t('templates.autoenrollEnabled')}
        </label>
        <p className="text-xs text-text-secondary mt-1">{t('templates.autoenrollEnabledDescription')}</p>

        <Input
          label={t('templates.allowedAdGroup')}
          value={formData.allowed_ad_group}
          onChange={(e) => set('allowed_ad_group', e.target.value)}
          placeholder={t('templates.allowedAdGroupPlaceholder')}
          className="mt-3"
        />
        <p className="text-xs text-text-secondary mt-1">{t('templates.allowedAdGroupDescription')}</p>

        <div className="mt-4">
          <p className="text-xs font-medium text-text-primary">{t('templates.pinnedSubjectFields')}</p>
          <p className="text-xs text-text-secondary mt-1 mb-2">{t('templates.pinnedSubjectFieldsDescription')}</p>
          <div className="grid grid-cols-3 gap-4">
            <Input label={t('templates.pinnedCountry')} value={formData.pinned_subject_fields.C} onChange={(e) => updatePinned('C', e.target.value)} placeholder="US" />
            <Input label={t('templates.pinnedState')} value={formData.pinned_subject_fields.ST} onChange={(e) => updatePinned('ST', e.target.value)} placeholder="California" />
            <Input label={t('templates.pinnedLocality')} value={formData.pinned_subject_fields.L} onChange={(e) => updatePinned('L', e.target.value)} placeholder="San Francisco" />
            <Input label={t('templates.pinnedOrganization')} value={formData.pinned_subject_fields.O} onChange={(e) => updatePinned('O', e.target.value)} placeholder={t('templates.orgPlaceholder')} />
            <Input label={t('templates.pinnedOrganizationalUnit')} value={formData.pinned_subject_fields.OU} onChange={(e) => updatePinned('OU', e.target.value)} placeholder="IT Department" />
          </div>
        </div>
      </div>

      {/* Extensions */}
      <div className="border-t border-border pt-4 space-y-4">
        <h4 className={sectionTitle}>{t('templates.extensions')}</h4>

        {/* Key Usage */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-2">{t('common.keyUsage')}</label>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {KEY_USAGE_OPTIONS.map(ku => (
              <label key={ku} className={checkboxCls}>
                <input type="checkbox" checked={formData.key_usage.includes(ku)} onChange={() => toggleCheckbox('key_usage', ku)} className="accent-accent-primary" />
                {ku}
              </label>
            ))}
          </div>
        </div>

        {/* Extended Key Usage */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-2">{t('common.extKeyUsage')}</label>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {ekuOptions.map(eku => (
              <label key={eku} className={checkboxCls}>
                <input type="checkbox" checked={formData.extended_key_usage.includes(eku)} onChange={() => toggleCheckbox('extended_key_usage', eku)} className="accent-accent-primary" />
                {eku}
              </label>
            ))}
          </div>
        </div>

        {/* SAN Types */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-2">{t('common.subjectAltNames')}</label>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {SAN_TYPE_OPTIONS.map(st => (
              <label key={st} className={checkboxCls}>
                <input type="checkbox" checked={formData.san_types.includes(st)} onChange={() => toggleCheckbox('san_types', st)} className="accent-accent-primary" />
                {t(SAN_TYPE_LABEL_KEYS[st], st.toUpperCase())}
              </label>
            ))}
          </div>
          <p className="text-xs text-text-secondary mt-1">{t('templates.sanTypesHint')}</p>
          <label className={`${checkboxCls} mt-2`}>
            <input
              type="checkbox"
              checked={formData.enforce_san_types}
              onChange={(e) => set('enforce_san_types', e.target.checked)}
              className="accent-accent-primary"
            />
            {t('templates.enforceSanTypes')}
          </label>
          <p className="text-xs text-text-secondary mt-1">{t('templates.enforceSanTypesDescription')}</p>
        </div>
      </div>

      {/* qcStatements + policy OIDs */}
      <div className="border-t border-border pt-4 space-y-4">
        <h4 className={sectionTitle}>{t('templates.qc.title')}</h4>
        <p className="text-xs text-text-secondary">{t('templates.qc.hint')}</p>
        <div className="p-3 rounded-lg border border-status-warning-op30 bg-status-warning-op10 flex items-start gap-2 text-xs text-text-secondary">
          <Warning size={16} className="text-status-warning shrink-0 mt-0.5" weight="bold" />
          <span>{t('templates.qc.legalWarning')}</span>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <label className={checkboxCls}>
            <input type="checkbox" checked={formData.qc.compliance} onChange={(e) => setQc('compliance', e.target.checked)} className="accent-accent-primary" />
            {t('templates.qc.compliance')}
          </label>
          <label className={checkboxCls}>
            <input type="checkbox" checked={formData.qc.sscd} onChange={(e) => setQc('sscd', e.target.checked)} className="accent-accent-primary" />
            {t('templates.qc.sscd')}
          </label>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Select
            label={t('templates.qc.type')}
            value={formData.qc.type}
            onChange={(val) => setQc('type', val)}
            options={[{ value: '', label: t('templates.qc.none') }, ...QC_TYPES.map(v => ({ value: v, label: t(`templates.qc.types.${v}`) }))]}
          />
          <Select
            label={t('templates.qc.semantics')}
            value={formData.qc.semantics}
            onChange={(val) => setQc('semantics', val)}
            options={[{ value: '', label: t('templates.qc.none') }, ...QC_SEMANTICS.map(v => ({ value: v, label: t(`templates.qc.semanticsValues.${v}`) }))]}
          />
          <Input
            label={t('templates.qc.ccLegislation')}
            value={formData.qc.cc_legislation}
            onChange={(e) => setQc('cc_legislation', e.target.value)}
            placeholder="FR, DE"
            helperText={t('templates.qc.ccLegislationHint')}
          />
          <Input
            label={t('templates.qc.retentionPeriod')}
            type="number"
            min="1"
            value={formData.qc.retention_period}
            onChange={(e) => setQc('retention_period', e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-text-secondary mb-2">{t('templates.qc.limitValue')}</label>
          <div className="grid grid-cols-3 gap-4">
            <Input label={t('templates.qc.limitCurrency')} value={formData.qc.limit_currency} onChange={(e) => setQc('limit_currency', e.target.value)} placeholder="EUR" />
            <Input label={t('templates.qc.limitAmount')} type="number" value={formData.qc.limit_amount} onChange={(e) => setQc('limit_amount', e.target.value)} />
            <Input label={t('templates.qc.limitExponent')} type="number" value={formData.qc.limit_exponent} onChange={(e) => setQc('limit_exponent', e.target.value)} />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-text-secondary mb-2">{t('templates.qc.pds')}</label>
          <p className="text-xs text-text-secondary mb-2">{t('templates.qc.pdsHint')}</p>
          <div className="space-y-2">
            {formData.qc.pds.map((entry, i) => (
              <div key={i} className="grid grid-cols-[1fr_6rem_auto] gap-2 items-end">
                <Input label={t('templates.qc.pdsUrl')} value={entry.url} onChange={(e) => updatePds(i, 'url', e.target.value)} placeholder="https://example.com/pds_en.pdf" />
                <Input label={t('templates.qc.pdsLanguage')} value={entry.language} onChange={(e) => updatePds(i, 'language', e.target.value)} placeholder="en" maxLength={2} />
                <Button type="button" size="sm" variant="secondary" onClick={() => setQc('pds', formData.qc.pds.filter((_, j) => j !== i))}>
                  {t('common.remove')}
                </Button>
              </div>
            ))}
          </div>
          <Button type="button" size="sm" variant="secondary" className="mt-2"
            onClick={() => setQc('pds', [...formData.qc.pds, { url: '', language: 'en' }])}>
            {t('templates.qc.addPds')}
          </Button>
        </div>

        <div>
          <Textarea
            label={t('templates.qc.policyOids')}
            value={formData.policy_oids}
            onChange={(e) => set('policy_oids', e.target.value)}
            placeholder="0.4.0.194112.1.2"
            rows={2}
            helperText={t('templates.qc.policyOidsHint')}
          />
          <div className="flex flex-wrap gap-2 mt-2">
            {ETSI_POLICY_PRESETS.map(pr => (
              <Button key={pr.oid} type="button" size="sm" variant="secondary" onClick={() => addPolicyPreset(pr.oid)} title={pr.oid}>
                {pr.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {/* Custom extensions (#437) */}
      <div className="border-t border-border pt-4 space-y-2">
        <h4 className={sectionTitle}>{t('customExtensions.title')}</h4>
        <StoredExtensionsError error={template?.custom_extensions_error} />
        <CustomExtensionsEditor rows={formData.custom_extensions} onChange={(rows) => set('custom_extensions', rows)} />
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={loading || !formData.name.trim() || !customExt.valid}>
          {loading ? <LoadingSpinner size="sm" /> : (template ? t('common.update') : t('common.create'))}
        </Button>
      </div>
    </form>
  )
}
