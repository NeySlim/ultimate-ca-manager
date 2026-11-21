/**
 * Trust Store: the mockup's truststore module, a simplePage() list (Sujet, Usage, Expiration, État)
 * with its one-object dock, on the server's trust anchors; the usage is the anchor's description.
 * What the product has more (its type, search and type filter, sort, the selection and its bulk
 * deletion, the bundle export, the system sync, import, adding managed CAs, export and deletion,
 * the technical details and the PEM) takes the page head, the toolbar, the batch bar, the dock
 * actions and further dock tabs.
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { Input } from '../components/atelier/Form'
import {
  Zone, AtelierDialog, Icon, Btn, Pill, PageHead, Toolbar, SearchField, FilterSelect, BatchBar, ListView, Dock, DockBody, Section, Props,
  LoadError, LoadCause, EmptyBlock, NoMatch,
} from '../components/atelier'
import { SmartImportModal } from '../components/SmartImport'
import { truststoreService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals, usePersistedState } from '../hooks'
import { downloadBlob, warnSkippedExport } from '../lib/utils'
import { soleImported } from '../lib/importResult'
import { trustStoreExpiryStatus } from '../lib/expiry'
import { runInBatches } from '../lib/bulkChunks'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { certificateKeyLabel, serialHex } from '../lib/certificateDetail'
import { dateOf, dateTimeOf } from './admin/adminDates'
import { PemPanel } from './certificates/inspector/PemPanel'
import { PhoneMoreActions } from './pki/PhoneMoreActions'

// The anchor types the server stores (purpose), in the order of the type filter
const PURPOSES = ['root_ca', 'intermediate_ca', 'client_auth', 'code_signing', 'system', 'custom']
const PURPOSE_LABELS = {
  root_ca: 'common.rootCA', intermediate_ca: 'common.intermediate', client_auth: 'trustStore.clientAuth',
  code_signing: 'common.codeSigning', system: 'common.system', custom: 'common.custom',
}

export default function TrustStorePage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { id: urlCertId } = useParams()
  const navigate = useNavigate()
  const openEntity = useOpenEntity()
  const { showSuccess, showError, showWarning, showConfirm } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()
  const { modals, open: openModal, close: closeModal } = useModals(['add', 'sync'])
  
  const [loading, setLoading] = useState(true)
  const [certificates, setCertificates] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [selectedCert, setSelectedCert] = useState(null)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncLimit, setSyncLimit] = useState(500)
  const [showImportModal, setShowImportModal] = useState(false)
  // The search, the type and state filters (kept), the sort and the open dock tab
  const [query, setQuery] = useState('')
  const [purpose, setPurpose] = usePersistedState('ucm-truststore-type', '')
  const [state, setState] = usePersistedState('ucm-truststore-state', '')
  const [sort, setSort] = useState({ key: 'name', asc: true })
  const [section, setSection] = useState('overview')
  
  // Add from managed CAs modal state
  const [managedCAs, setManagedCAs] = useState([])
  const [selectedCAIds, setSelectedCAIds] = useState([])
  const [adding, setAdding] = useState(false)
  const [loadingCAs, setLoadingCAs] = useState(false)

  // Memoised so the 'ucm:data-changed' listener below can depend on it without
  // re-subscribing on every render.
  const loadCertificates = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const certsRes = await truststoreService.getAll()
      const rawCerts = certsRes.data || []
      // Same buckets as the export's expiry filter (api/v2/truststore)
      const enrichedCerts = rawCerts.map(c => ({
        ...c,
        _expiry_status: trustStoreExpiryStatus(c.not_after)
      }))
      setCertificates(enrichedCerts)
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.truststore'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => {
    loadCertificates()
  }, [])

  // Reload when inspector actions change data. loadCertificates must be
  // in the dependencies: a listener registered once keeps the loader captured
  // at mount and reloads with the state of that moment (#345).
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'truststore') loadCertificates()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadCertificates])

  // The search and the type filter, then the state chip and the sort
  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return certificates.filter((c) => (!purpose || c.purpose === purpose)
      && (!q || [c.name, c.subject, c.issuer, c.purpose, c.description].some((v) => String(v || '').toLowerCase().includes(q))))
  }, [certificates, purpose, query])
  const filteredCertificates = useMemo(() => {
    const value = { name: (c) => String(c.name || '').toLowerCase(), not_after: (c) => c.not_after || '' }[sort.key]
    return searched.filter((c) => !state || (c._expiry_status || 'valid') === state).sort((a, b) => {
      const va = value(a)
      const vb = value(b)
      return (va < vb ? -1 : va > vb ? 1 : 0) * (sort.asc ? 1 : -1)
    })
  }, [searched, state, sort])

  // The list row holds the anchor; its detail completes it once read
  const handleSelectCert = async (cert) => {
    if (cert.id !== selectedCert?.id) setSection('overview')
    if (cert.name) setSelectedCert(cert)
    try {
      const response = await truststoreService.getById(cert.id)
      setSelectedCert((prev) => ({ ...(prev?.id === cert.id ? prev : {}), ...(response.data || cert) }))
    } catch {
      if (!cert.name) setSelectedCert(null)
    }
  }

  // Deep-link: /truststore/:id opens that anchor, even one the filters hide
  useEffect(() => {
    if (urlCertId && !loading) {
      const id = parseInt(urlCertId, 10)
      if (!isNaN(id)) handleSelectCert(certificates.find((c) => c.id === id) || { id })
      navigate('/truststore', { replace: true })
    }
  }, [urlCertId, loading]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadManagedCAs = async () => {
    setLoadingCAs(true)
    try {
      const res = await casService.getAll()
      const cas = res.data || []
      // Filter out CAs already in truststore (by fingerprint match via subject)
      const existingSubjects = new Set(certificates.map(c => c.subject))
      setManagedCAs(cas.map(ca => ({ ...ca, alreadyInTruststore: existingSubjects.has(ca.subject) })))
    } catch (error) {
      showError(error.message)
    } finally {
      setLoadingCAs(false)
    }
  }

  const handleOpenAddModal = () => {
    setSelectedCAIds([])
    loadManagedCAs()
    openModal('add')
  }

  const handleAddFromCAs = async () => {
    if (selectedCAIds.length === 0) return
    setAdding(true)
    let added = 0
    let lastAdded = null
    try {
      for (const caId of selectedCAIds) {
        try {
          const exportRes = await casService.export(caId, 'pem')
          const pemText = typeof exportRes === 'string' ? exportRes : 
            exportRes instanceof Blob ? await exportRes.text() :
            exportRes?.data instanceof Blob ? await exportRes.data.text() :
            typeof exportRes?.data === 'string' ? exportRes.data : ''
          const ca = managedCAs.find(c => c.id === caId)
          const response = await truststoreService.add({
            name: ca?.descr || ca?.common_name || `CA-${caId}`,
            description: ca?.organization || '',
            certificate_pem: pemText,
            purpose: ca?.is_root ? 'root_ca' : 'intermediate_ca',
            notes: t('trustStore.addedFromManaged')
          })
          added++
          lastAdded = response?.data
        } catch (err) {
          // Skip duplicates (409)
          if (!err.message?.includes('already')) {
            showError(`${managedCAs.find(c => c.id === caId)?.descr}: ${err.message}`)
          }
        }
      }
      if (added > 0) {
        showSuccess(t('trustStore.addedCount', { count: added }))
        loadCertificates()
      }
      closeModal('add')
      // Several entries at once leave the list to show them
      if (added === 1 && lastAdded?.id) handleSelectCert(lastAdded)
    } finally {
      setAdding(false)
    }
  }

  const handleSyncFromSystem = async () => {
    setSyncing(true)
    try {
      const limit = Math.max(1, Math.min(1000, parseInt(syncLimit, 10) || 500))
      const response = await truststoreService.syncFromSystem(limit)
      showSuccess(response.message || t('trustStore.syncedCerts', { count: response.data?.new_count || 0 }))
      loadCertificates()
      closeModal('sync')
    } catch (error) {
      showError(error.message || t('trustStore.syncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.truststore'), {
      title: t('trustStore.confirmRemove'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await truststoreService.delete(cert.id)
      showSuccess(t('messages.success.delete.truststore'))
      loadCertificates()
      if (selectedCert?.id === cert.id) {
        setSelectedCert(null)
      }
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.truststore'))
    }
  }

  // Only rows the current filters show: a selection made before narrowing
  // them never removes what is no longer on screen (#388)
  const handleBulkDelete = async () => {
    const visible = new Set(filteredCertificates.map(c => c.id))
    const ids = [...selectedIds].filter(id => visible.has(id))
    if (ids.length === 0) return
    const confirmed = await showConfirm(t('trustStore.confirmBulkRemove', { count: ids.length }), {
      title: t('trustStore.confirmRemove'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return

    setBulkDeleting(true)
    try {
      const result = await runInBatches(ids, batch => truststoreService.bulkDelete(batch))
      const removed = result?.data?.success || []
      const failed = result?.data?.failed || []
      if (removed.length) showSuccess(t('trustStore.bulkRemoved', { count: removed.length }))
      if (failed.length) showError(t('trustStore.bulkRemoveFailed', { count: failed.length }))
      if (selectedCert && removed.includes(selectedCert.id)) setSelectedCert(null)
      setSelectedIds(new Set())
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.truststore'))
    } finally {
      setBulkDeleting(false)
      loadCertificates()
    }
  }

  const handleExport = (cert) => {
    if (!cert?.certificate_pem) return
    
    const blob = new Blob([cert.certificate_pem], { type: 'application/x-pem-file' })
    downloadBlob(blob, `${cert.name}.pem`)
  }

  const handleExportBundle = async (format = 'pem') => {
    try {
      const response = await truststoreService.exportBundle(format, purpose ? [purpose] : 'all', state ? [state] : [])
      const blob = response instanceof Blob ? response : response?.data instanceof Blob ? response.data : new Blob([response?.data || response], { type: 'application/x-pem-file' })
      downloadBlob(blob, `truststore-bundle.${format}`)
      showSuccess(t('trustStore.bundleExported'))
      warnSkippedExport(response, t, showWarning)
    } catch (error) {
      showError(error.message || t('trustStore.exportFailed'))
    }
  }

  const addable = managedCAs.filter(ca => !ca.alreadyInTruststore)
  const dialogs = (
    <>
      {/* Add from managed CAs: tick the CAs to trust, those already in the store stay ticked off */}
      {modals.add && (
        <AtelierDialog title={t('trustStore.addFromManagedCAs')} size="narrow" onClose={() => closeModal('add')} testId="truststore-add-dialog">
          {loadingCAs ? (
            <p className="small muted" role="status">{t('common.loading')}</p>
          ) : managedCAs.length === 0 ? (
            <p className="event-detail">{t('trustStore.noManagedCAs')}</p>
          ) : (
            <>
              <p className="muted" style={{ marginBottom: 14 }}>{t('trustStore.selectCAsToAdd')}</p>
              <div className="columns-list" style={{ maxHeight: '45dvh', overflow: 'auto' }}>
                <label className="checkbox-line">
                  <input type="checkbox"
                    checked={selectedCAIds.length === addable.length && selectedCAIds.length > 0}
                    onChange={(e) => setSelectedCAIds(e.target.checked ? addable.map(ca => ca.id) : [])} />
                  {t('common.selectAll')} ({selectedCAIds.length}/{addable.length})
                </label>
                {managedCAs.map(ca => (
                  <label key={ca.id} className="checkbox-line">
                    <input type="checkbox" checked={selectedCAIds.includes(ca.id)} disabled={ca.alreadyInTruststore}
                      onChange={() => {
                        if (ca.alreadyInTruststore) return
                        setSelectedCAIds(prev => prev.includes(ca.id) ? prev.filter(id => id !== ca.id) : [...prev, ca.id])
                      }} />
                    <span style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
                      {ca.descr || ca.common_name}{ca.organization && <span className="muted"> · {ca.organization}</span>}
                    </span>
                    <Pill tone="muted" icon="shield" label={ca.is_root ? 'Root' : 'Inter'} />
                    {ca.alreadyInTruststore && <Pill tone="good" label={t('trustStore.alreadyInTruststore')} />}
                  </label>
                ))}
              </div>
            </>
          )}
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={() => closeModal('add')}>{t('common.cancel')}</button>
            <button type="button" className="btn primary" data-write="" onClick={handleAddFromCAs} disabled={adding || selectedCAIds.length === 0 || undefined}>
              {adding ? t('trustStore.adding') : t('trustStore.addSelected', { count: selectedCAIds.length })}
            </button>
          </div>
        </AtelierDialog>
      )}

      {/* Sync from the system store: how many CAs to take at most */}
      {modals.sync && (
        <AtelierDialog title={t('trustStore.syncTitle')} subtitle={t('trustStore.syncDescription')} size="narrow" onClose={() => closeModal('sync')} testId="truststore-sync-dialog">
          <form onSubmit={(e) => { e.preventDefault(); handleSyncFromSystem() }}>
            <div className="form-fields">
              <Input id="truststore-sync-limit" label={t('trustStore.syncLimitLabel')} type="number" min={1} max={1000} short value={syncLimit}
                onChange={(e) => setSyncLimit(e.target.value)} helperText={t('trustStore.syncLimitHelp')} data-autofocus="" />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={() => closeModal('sync')}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary" disabled={syncing || undefined}><Icon name="refresh" />{syncing ? t('trustStore.syncing') : t('trustStore.sync')}</button>
            </div>
          </form>
        </AtelierDialog>
      )}

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={(result) => {
          setShowImportModal(false)
          loadCertificates()
          // Smart Import adds CAs and certificates, not trust store entries
          const sole = soleImported(result)
          if (sole) openEntity(sole.type, sole.id)
        }}
      />
    </>
  )

  // ============= LIST =============

  const tsState = (c) => c._expiry_status || 'valid'
  const TONES = { valid: 'good', expiring: 'warn', expired: 'bad' }
  const tsPill = (c) => <Pill label={t(`trustStore.module.states.${tsState(c)}`)} tone={TONES[tsState(c)] || 'muted'} />
  const tsUsage = (c) => c.description || '—'
  const tsType = (c) => (PURPOSES.includes(c.purpose) ? t(PURPOSE_LABELS[c.purpose]) : (c.purpose || '—'))
  const tsExpires = (c) => dateOf(c.not_after, locale) || '—'
  const present = ['valid', 'expiring', 'expired'].filter((s) => certificates.some((c) => tsState(c) === s))
  const active = present.includes(state) ? state : ''
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    ...present.map((s) => ({ id: s, label: t(`trustStore.module.states.${s}`), count: searched.filter((c) => tsState(c) === s).length })),
  ]
  const rows = filteredCertificates
  const narrowed = Boolean(query.trim() || purpose || active)
  const write = canWrite('truststore')
  const add = write ? { label: t('trustStore.addCertificate'), icon: 'plus', onClick: handleOpenAddModal, write: true } : undefined
  const selection = canDelete('truststore') ? {
    selected: selectedIds,
    onToggle: (id) => setSelectedIds((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next }),
    onTogglePage: (on) => setSelectedIds(on ? new Set(rows.map((c) => c.id)) : new Set()),
  } : undefined
  const ticked = rows.filter((c) => selectedIds.has(c.id)).length

  // ============= DOCK =============

  const open = selectedCert
  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('shell.moduleLabel.truststore') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.name, icon: 'anchor' }]} onClose={() => setSelectedCert(null)}>
      <DockBody icon="anchor" title={open.name} badge={tsPill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: open.name })}
        sections={[['overview', t('atelier.overview')], ['details', t('trustStore.module.sections.details')], ['pem', 'PEM']]}
        actions={<>
          <Btn icon="download" id="truststore-export" onClick={() => handleExport(open)}>{t('common.export')}</Btn>
          {canDelete('truststore') && <Btn tone="danger" icon="block" id="truststore-delete" onClick={() => handleDelete(open)}>{t('common.delete')}</Btn>}
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('trustStore.module.subject'), open.subject || '—'],
                [t('trustStore.module.usage'), tsUsage(open)],
                [t('common.type'), tsType(open)],
                [t('trustStore.module.expires'), tsExpires(open)],
                [t('atelier.state'), tsPill(open)],
              ]} />
            </Section>
            <Section title={t('atelier.summary')}><p className="summary">{open.notes || t('trustStore.module.noNotes')}</p></Section>
          </div>
        )}
        {section === 'details' && (
          <div className="module-detail">
            <Section title={t('common.technicalDetails')}>
              <Props items={[
                [t('common.issuer'), <span key="issuer" className="mono">{open.issuer || '—'}</span>],
                [t('common.serialNumber'), open.serial_number ? <span key="serial" className="mono">{serialHex(open.serial_number)}</span> : '—'],
                [t('common.keyType'), certificateKeyLabel(open) || '—'],
                [t('common.issuerSignatureAlgorithm'), open.signature_algorithm || '—'],
                [t('common.validFrom'), dateOf(open.not_before, locale) || '—'],
                [t('common.validUntil'), tsExpires(open)],
              ]} />
            </Section>
            <Section title={t('common.fingerprints')}>
              <Props items={[
                ['SHA-256', <span key="sha256" className="mono">{open.fingerprint_sha256 || '—'}</span>],
                ['SHA-1', <span key="sha1" className="mono">{open.fingerprint_sha1 || '—'}</span>],
              ]} />
            </Section>
            <Section title={t('details.metadata')}>
              <Props items={[
                [t('details.addedAt'), dateTimeOf(open.added_at, locale) || '—'],
                [t('details.addedBy'), open.added_by || '—'],
              ]} />
            </Section>
          </div>
        )}
        {section === 'pem' && <PemPanel cert={{ pem: open.certificate_pem }} />}
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} testId="truststore-zone" after={dialogs}>
      <PageHead title={t('shell.moduleLabel.truststore')} total={t('trustStore.module.unit', { count: certificates.length })} intent={t('shell.moduleDesc.truststore')}
        actions={<>
          {certificates.length > 0 && <Btn icon="download" id="truststore-bundle" onClick={() => handleExportBundle('pem')}>{t('trustStore.exportBundle')}</Btn>}
          {write && <Btn icon="refresh" id="truststore-sync" write disabled={syncing || undefined} onClick={() => openModal('sync')}>{syncing ? t('trustStore.syncing') : t('trustStore.sync')}</Btn>}
          {write && <Btn icon="upload" id="truststore-import" write onClick={() => setShowImportModal(true)}>{t('common.import')}</Btn>}
          <PhoneMoreActions title={t('shell.moduleLabel.truststore')} items={[
            certificates.length > 0 && { id: 'bundle', icon: 'download', label: t('trustStore.exportBundle'), onClick: () => handleExportBundle('pem') },
            write && { id: 'sync', icon: 'refresh', label: t('trustStore.sync'), write: true, disabled: syncing, onClick: () => openModal('sync') },
            write && { id: 'import', icon: 'upload', label: t('common.import'), write: true, onClick: () => setShowImportModal(true) },
          ]} />
          {write && <Btn tone="primary" icon="plus" id="truststore-add" onClick={handleOpenAddModal}>{t('trustStore.add')}</Btn>}
        </>} />
      <ListView label={t('shell.moduleLabel.truststore')} caption={t('trustStore.module.caption')} icon="anchor" rows={rows} loading={loading}
        filters={{ views, active, onChange: setState, label: t('trustStore.module.filterByState') }}
        toolbar={<>
          <Toolbar>
            <SearchField id="truststore-search" name="q" label={t('common.searchCertificates')} placeholder={t('common.searchCertificates')} value={query} onChange={setQuery} />
            <FilterSelect id="truststore-type" label={t('trustStore.module.filterByType')} value={purpose} onChange={setPurpose}
              options={[{ value: '', label: t('trustStore.allPurposes') }, ...PURPOSES.map((p) => ({ value: p, label: t(PURPOSE_LABELS[p]) }))]} />
          </Toolbar>
          {ticked > 0 && (
            <BatchBar count={t('trustStore.module.selected', { count: ticked })} onClear={() => setSelectedIds(new Set())}>
              <Btn tone="danger" icon="block" id="truststore-bulk-delete" disabled={bulkDeleting || undefined} onClick={handleBulkDelete}>{t('trustStore.deleteSelected')}</Btn>
            </BatchBar>
          )}
        </>}
        title={(c) => c.name || '—'} status={tsPill} openedId={open?.id} onOpen={handleSelectCert} selection={selection}
        sort={sort} onSort={(key) => setSort((s) => ({ key, asc: s.key === key ? !s.asc : true }))} nameSort="name"
        columns={[
          { id: 'subject', label: t('trustStore.module.subject'), cell: (c) => c.subject || '—', grow: true },
          { id: 'usage', label: t('trustStore.module.usage'), cell: tsUsage },
          { id: 'type', label: t('common.type'), cell: tsType },
          { id: 'expires', label: t('trustStore.module.expires'), cell: tsExpires, sort: 'not_after' },
          { status: true },
        ]}
        error={loadError && (
          <LoadError id="truststore" title={t('messages.errors.loadFailed.truststore')} onRetry={loadCertificates} journal={hasPermission?.('read:audit') ? '/audit' : undefined}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/truststore', message: loadError.message }} />} />
        )}
        empty={narrowed && certificates.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setQuery(''); setPurpose(''); setState('') }} />
        ) : (
          <EmptyBlock id="truststore" icon="anchor" title={t('trustStore.module.emptyTitle')} text={t('trustStore.addCertificatesForChain')} action={add} />
        )}
        footer={{ range: t('trustStore.module.range', { shown: rows.length, count: certificates.length }) }} />
    </Zone>
  )
}
