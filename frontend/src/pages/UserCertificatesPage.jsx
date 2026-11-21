/**
 * User certificates (no screen in the mockup): the module list template of the mockup's
 * listView() (Description, Propriétaire, Expiration, État) with its one-object dock, on the
 * server's paged enrolments. The state chips filter on the server and count from its statistics;
 * the search, the sort, the list export and the certificate's actions (export, lint, key recovery,
 * revocation, deletion) take the toolbar, the page head and the dock. The certificate an enrolment
 * is bound to opens in the Certificates zone.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  Zone, Btn, IconBtn, Icon, Pill, PageHead, Toolbar, SearchField, ListView, Dock, DockBody, Section, Props,
  LoadError, LoadCause, EmptyBlock, NoMatch, AtelierDialog,
} from '../components/atelier'
import { userCertificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, usePersistedState } from '../hooks'
import { useEntityActions } from '../hooks/useEntityActions'
import { extractCN, isOnHold, downloadBlob, exportToJSON } from '../lib/utils'
import { fetchPages } from '../lib/fetchAllPages'
import { canExportPrivateKey } from '../lib/exportPermissions'
import { downloadExport } from '../lib/exportDownload'
import { localOnlyRevocationWarning } from '../lib/revocationOutcome'
import { certificateKeyLabel, serialHex } from '../lib/certificateDetail'
import { dateOf, dateTimeOf } from './admin/adminDates'
import { usersCsv } from './users/usersExport'
import { ExportDialog } from './certificates/dialogs/ExportDialog'
import { RevokeDialog } from './certificates/dialogs/RevokeDialog'
import { CertMenu } from './certificates/inspector/CertMenu'
import { STATES as CERT_STATES } from './certificates/certState'

// The states the server filters on, in the order of the chips (a certificate's states, as the Certificates zone draws them)
const STATES = { valid: CERT_STATES.valid, expiring: CERT_STATES.expiring, expired: CERT_STATES.expired, revoked: CERT_STATES.revoked }
const SERVER_SORT_KEYS = { name: 'name', valid_to: 'valid_until' }
const EXPORT_MAX = 10000
const MENU_ICONS = { lint: 'policy', keyRecovery: 'key' }

const userCertName = (row) => row?.name || extractCN(row?.cert_subject) || row?.common_name || '—'

/** The list export: CSV (formula cells neutralised) or JSON, of every page the filters keep. */
function ExportListDialog({ count, onExport, onClose }) {
  const { t } = useTranslation()
  const [format, setFormat] = useState('csv')
  const [busy, setBusy] = useState(false)
  const run = async () => { setBusy(true); try { await onExport(format) } finally { setBusy(false) } }
  return (
    <AtelierDialog title={t('userCertificates.module.exportList')} onClose={onClose} testId="user-certs-export-dialog">
      <p className="small muted">{t('userCertificates.module.exportScope', { count: Math.min(count, EXPORT_MAX) })}</p>
      <div className="format-grid">
        {['csv', 'json'].map((f) => (
          <label key={f} className="format-option">
            <input type="radio" name="format" value={f} checked={format === f} onChange={() => setFormat(f)} />
            <span>{f.toUpperCase()}<small>{t(`userCertificates.module.format_${f}`)}</small></span>
          </label>
        ))}
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
        <button type="button" className="btn primary" data-write="false" disabled={busy} onClick={run}><Icon name="download" />{t('audit.download')}</button>
      </div>
    </AtelierDialog>
  )
}

export default function UserCertificatesPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const navigate = useNavigate()
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()

  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [certStats, setCertStats] = useState({ total: 0, valid: 0, expiring: 0, expired: 0, revoked: 0 })
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  const [state, setState] = usePersistedState('ucm-usercerts-state', '')
  const [searchValue, setSearchValue] = useState('')
  // The server sorts the whole list; null keeps its default (newest first)
  const [sort, setSort] = useState(null)
  const [open, setOpen] = useState(null)
  const [section, setSection] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const [listExport, setListExport] = useState(false)
  // Export: the dialog owns the format, password and PKCS#12 profile (#331)
  const [exportCert, setExportCert] = useState(null)
  const [revokingCert, setRevokingCert] = useState(null)
  const [revoking, setRevoking] = useState(false)

  const filterParams = useCallback((params) => {
    if (STATES[state]) params.status = [state]
    if (searchValue) params.search = searchValue
    if (sort) {
      params.sort_by = sort.by
      params.sort_order = sort.order
    }
    return params
  }, [state, searchValue, sort])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [certRes, statsRes] = await Promise.all([
        userCertificatesService.getAll(filterParams({ page, per_page: perPage })),
        userCertificatesService.getStats(),
      ])
      setLoadError(null)
      setCertificates(certRes.data?.items || [])
      setTotal(certRes.data?.total || 0)
      setCertStats(statsRes.data || { total: 0, valid: 0, expiring: 0, expired: 0, revoked: 0 })
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.certificates'))
    } finally {
      setLoading(false)
    }
  }, [page, perPage, filterParams, showError, t])

  useEffect(() => { loadData() }, [loadData])

  // Reload when an action elsewhere changed an enrolment
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'user_certificate') loadData()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadData])

  // The list row first, then the enrolment's detail
  const openCert = async (row) => {
    if (row.id !== open?.id) setSection('overview')
    setOpen(row)
    try {
      const res = await userCertificatesService.getById(row.id)
      if (res?.data) setOpen((prev) => (prev?.id === row.id ? { ...prev, ...res.data } : prev))
    } catch { /* the row stays shown */ }
  }

  // Lint and key recovery come from the shared actions; export, revocation and deletion stay this page's
  const shared = useEntityActions({ type: 'user_certificate', entity: open, entityId: open?.id, onChanged: setOpen, onClose: () => setOpen(null) })

  const handleExport = async (format, options = {}) => {
    if (!exportCert) return
    try {
      await downloadExport(userCertificatesService.export(exportCert.id, format, options), { format, name: exportCert.name || 'certificate' })
      showSuccess(t('userCertificates.exportSuccess'))
    } catch (error) {
      showError(error.message || t('userCertificates.exportFailed'))
      throw error
    }
  }

  // Revocation asks for the RFC 5280 reason (#334)
  const handleRevoke = (cert) => setRevokingCert({ ...cert, name: cert.name || cert.cert_subject })
  const handleRevokeConfirm = async (reason) => {
    if (!revokingCert) return
    setRevoking(true)
    try {
      const res = await userCertificatesService.revoke(revokingCert.id, reason)
      const localOnly = localOnlyRevocationWarning(res, t)
      if (res?.data?.approval_required) showWarning(t('certificates.revocationApprovalRequired', { policy: res.data.policy_name }))
      else if (localOnly) showWarning(localOnly)
      else showSuccess(t('userCertificates.revokeSuccess'))
      setRevokingCert(null)
      setOpen(null)
      loadData()
    } catch (error) {
      showError(error.message || t('userCertificates.revokeFailed'))
    } finally {
      setRevoking(false)
    }
  }

  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(t('userCertificates.deleteDescription', { name: userCertName(cert) }),
      { title: t('userCertificates.deleteTitle'), variant: 'danger', confirmText: t('common.delete') })
    if (!confirmed) return
    try {
      // Its certificate is revoked first: the issuing CA may not have been told
      const localOnly = localOnlyRevocationWarning(await userCertificatesService.delete(cert.id), t)
      if (localOnly) showWarning(localOnly)
      else showSuccess(t('userCertificates.deleteSuccess'))
      setOpen(null)
      loadData()
    } catch (error) {
      showError(error.message || t('userCertificates.deleteFailed'))
    }
  }

  // Every page of the list as filtered and sorted on screen
  const exportList = async (format) => {
    const { rows, complete } = await fetchPages(async (paging) => {
      const res = await userCertificatesService.getAll(filterParams({ ...paging }))
      return { data: res.data?.items || [], meta: { total: res.data?.total || 0 } }
    }, { perPage: 100, max: EXPORT_MAX })
    if (!complete) { showError(t('table.exportFailed')); return }
    if (format === 'json') exportToJSON(rows, 'user-certificates')
    else {
      downloadBlob(usersCsv(rows, {
        head: [t('atelier.name'), t('userCertificates.module.description'), t('userCertificates.columns.owner'), t('userCertificates.module.expires'), t('atelier.state')],
        row: (r) => [userCertName(r), r.description || '', r.owner || '', r.valid_to || r.valid_until || '', r.status || ''],
      }), 'user-certificates.csv')
    }
    if (total > EXPORT_MAX) showWarning(t('table.exportTruncated', { count: EXPORT_MAX, total }))
    setListExport(false)
  }

  // An enrolment whose certificate is gone is an orphan; a state not known here stays neutral
  const ucPill = (row) => (row.status === 'orphan' ? <Pill label={t('userCertificates.module.orphan')} tone="muted" icon="block" />
    : !STATES[row.status] ? <Pill label={t('common.status')} tone="muted" />
    : <Pill label={t(STATES[row.status].key)} tone={STATES[row.status].tone} icon={STATES[row.status].icon} />)
  const ucExpires = (row) => dateOf(row.valid_to || row.valid_until, locale) || '—'
  const views = [
    { id: '', label: t('common.all'), count: certStats.total || 0 },
    ...Object.keys(STATES).map((s) => ({ id: s, label: t(`certificates.views.${s}`), count: certStats[s] || 0 })),
  ]
  const active = STATES[state] ? state : ''
  const chooseState = (s) => { setState(s); setPage(1) }
  const sortState = sort ? { key: Object.keys(SERVER_SORT_KEYS).find((k) => SERVER_SORT_KEYS[k] === sort.by), asc: sort.order === 'asc' } : null
  const onSort = (key) => {
    const by = SERVER_SORT_KEYS[key]
    setSort((s) => (s?.by === by ? (s.order === 'asc' ? { by, order: 'desc' } : null) : { by, order: 'asc' }))
    setPage(1)
  }
  const pages = Math.max(1, Math.ceil(total / perPage))
  const first = total ? (page - 1) * perPage + 1 : 0
  const last = Math.min(total, page * perPage)

  const revocable = open && canWrite('user_certificates') && (open.status !== 'revoked' || isOnHold(open))
  const menuItems = open ? [
    ...shared.actions.filter((a) => a.visible && MENU_ICONS[a.id]).map((a) => ({ id: a.id, icon: MENU_ICONS[a.id], label: a.label, onClick: a.onClick, write: a.id !== 'lint' })),
    revocable && { id: 'revoke', icon: 'block', label: t('userCertificates.actions.revoke'), danger: true, write: true, onClick: () => handleRevoke(open) },
    canDelete('user_certificates') && { id: 'delete', icon: 'close', label: t('common.delete'), danger: true, write: true, onClick: () => handleDelete(open) },
  ].filter(Boolean) : []

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('userCertificates.title') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: userCertName(open), icon: 'cert' }]} onClose={() => setOpen(null)}>
      <DockBody icon="cert" title={userCertName(open)} badge={ucPill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: userCertName(open) })} sections={[['overview', t('atelier.overview')]]}
        actions={<>
          <Btn tone="primary" write={false} icon="download" id="user-cert-export" onClick={() => setExportCert(open)}>{t('common.export')}</Btn>
          {open.cert_id && hasPermission('read:certificates') && (
            <Btn icon="cert" id="user-cert-inspect" onClick={() => navigate(`/certificates?id=${open.cert_id}`)}>{t('userCertificates.module.inspect')}</Btn>
          )}
          {menuItems.length > 0 && (
            <IconBtn quiet icon="more" title={false} label={t('userCertificates.module.moreActions', { name: userCertName(open) })} data-user-cert-menu={open.id} onClick={() => setMenuOpen(true)} />
          )}
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('userCertificates.module.description'), open.description || '—'],
              [t('userCertificates.detail.owner'), open.owner || '—'],
              [t('userCertificates.module.expires'), ucExpires(open)],
              [t('atelier.state'), ucPill(open)],
              [t('userCertificates.detail.subject'), <span key="subject" className="mono">{open.cert_subject || open.subject || '—'}</span>],
              [t('userCertificates.detail.issuer'), <span key="issuer" className="mono">{open.cert_issuer || open.issuer || '—'}</span>],
              [t('userCertificates.detail.serial'), <span key="serial" className="mono">{serialHex(open.serial_number || open.cert_serial) || '—'}</span>],
              [t('userCertificates.detail.fingerprint'), <span key="fp" className="mono">{open.cert_fingerprint || '—'}</span>],
              [t('common.keyType'), certificateKeyLabel(open) || '—'],
            ]} />
          </Section>
          <Section title={t('userCertificates.module.usage')}>
            <Props items={[
              [t('userCertificates.detail.validFrom'), dateOf(open.valid_from, locale) || '—'],
              [t('userCertificates.detail.validTo'), ucExpires(open)],
              [t('userCertificates.detail.lastUsed'), open.last_used_at ? dateTimeOf(open.last_used_at, locale) : t('common.never')],
              [t('userCertificates.detail.created'), dateTimeOf(open.created_at, locale) || '—'],
              [t('userCertificates.detail.privateKey'), open.has_private_key ? t('common.yes') : t('common.no')],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} testId="user-certificates-zone" after={<>
      {menuOpen && open && <CertMenu title={t('userCertificates.module.actionsTitle')} name={userCertName(open)} items={menuItems} onClose={() => setMenuOpen(false)} />}
      {listExport && <ExportListDialog count={total} onExport={exportList} onClose={() => setListExport(false)} />}
      <ExportDialog
        open={!!exportCert}
        onClose={() => setExportCert(null)}
        entityType="certificate"
        entityName={exportCert?.name || exportCert?.cert_subject || ''}
        hasPrivateKey={!!exportCert?.has_private_key}
        canExportKey={canExportPrivateKey('user_certificate', { hasPermission, canWrite })}
        keyAlgorithm={exportCert?.key_algorithm}
        onExport={handleExport}
      />
      <RevokeDialog
        allowHold={!isOnHold(revokingCert)}
        open={!!revokingCert}
        onClose={() => setRevokingCert(null)}
        onConfirm={handleRevokeConfirm}
        certificate={revokingCert}
        loading={revoking}
      />
      {shared.modals}
    </>}>
      <PageHead title={t('userCertificates.title')} total={t('userCertificates.module.unit', { count: certStats.total || 0 })} intent={t('shell.moduleDesc.userCertificates')}
        actions={<Btn icon="download" data-action="user-certs-export" disabled={!total || undefined} onClick={() => setListExport(true)}>{t('userCertificates.module.exportList')}</Btn>} />
      <ListView label={t('userCertificates.title')} caption={t('userCertificates.module.caption')} icon="cert" rows={certificates} loading={loading}
        filters={{ views, active, onChange: chooseState, label: t('userCertificates.module.filterByState') }}
        toolbar={(
          <Toolbar>
            <SearchField id="user-certs-search" name="q" label={t('userCertificates.searchPlaceholder')} placeholder={t('userCertificates.searchPlaceholder')}
              value={searchValue} onChange={(v) => { setSearchValue(v); setPage(1) }} />
          </Toolbar>
        )}
        title={userCertName} status={ucPill} openedId={open?.id} onOpen={openCert}
        sort={sortState} onSort={onSort} nameSort="name"
        columns={[
          { id: 'description', label: t('userCertificates.module.description'), cell: (r) => r.description || '—', grow: true },
          { id: 'owner', label: t('userCertificates.columns.owner'), cell: (r) => r.owner || '—' },
          { id: 'expires', label: t('userCertificates.module.expires'), cell: ucExpires, sort: 'valid_to' },
          { status: true },
        ]}
        error={loadError && (
          <LoadError id="user-certificates" title={t('messages.errors.loadFailed.certificates')} onRetry={loadData}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/user-certificates', message: loadError.message }} />} />
        )}
        empty={(searchValue || active) && certStats.total ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setSearchValue(''); chooseState('') }} />
        ) : (
          <EmptyBlock id="user-certificates" icon="cert" title={t('userCertificates.empty.title')} text={t('userCertificates.empty.description')} />
        )}
        footer={{
          range: t('userCertificates.module.range', { start: first, end: last, count: total }),
          pagination: { page, pages, perPage, onPage: setPage, onPerPage: (v) => { setPerPage(v); setPage(1) } },
        }} />
    </Zone>
  )
}
