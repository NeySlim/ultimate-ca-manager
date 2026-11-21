/**
 * Certificats SSH: the mockup's ssh module, a simplePage() list (Type, Principaux, Expiration,
 * Autorité, État) with its one-object dock, on the server's pages of SSH certificates. What the
 * product has more (state chips with the server's counts, type and CA filters, server sort and
 * pages, issue by signing a key or generating a pair, import, export, revocation and removal)
 * takes the mockup's chips, toolbar, sortable headers, footer, dock actions and form dialogs.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Zone, Icon, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, FilterSelect, ListView, Dock, DockBody,
  Section, Props, EmptyBlock, NoMatch, Input, Select, Textarea, ChoiceField, AtelierDialog, Notice,
} from '../components/atelier'
import { sshCertificatesService, sshCasService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useWebSocket, useClipboard, usePersistedState } from '../hooks'
import { formatDate, downloadBlob } from '../lib/utils'
import { sanitizeDownloadName } from '../lib/filename'
import { SSH_EDDSA_KEY_TYPES, SSH_FIPS_DEFAULT_KEY_TYPE, sshEddsaRefused, sshKeyOptions, useKeyPlatform } from '../lib/policyAlgorithms'

// ============= CONSTANTS =============

const VALIDITY_PRESETS = [
  { value: '1h', seconds: 3600 },
  { value: '8h', seconds: 28800 },
  { value: '24h', seconds: 86400 },
  { value: '7d', seconds: 604800 },
  { value: '30d', seconds: 2592000 },
  { value: '90d', seconds: 7776000 },
  { value: '365d', seconds: 31536000 },
  { value: 'custom', seconds: 0 },
]

const KEY_ALGORITHMS = [
  { value: 'ed25519', label: 'Ed25519' },
  { value: 'rsa', label: 'RSA (4096)' },
  { value: 'ecdsa-p256', label: 'ECDSA P-256' },
]

const DEFAULT_EXTENSIONS = [
  'permit-pty',
  'permit-agent-forwarding',
  'permit-X11-forwarding',
  'permit-port-forwarding',
  'permit-user-rc',
]

// The columns the server sorts (the others ask nothing of it)
const SORTS = { name: 'key_id', type: 'cert_type', expires: 'valid_to' }

// ============= STATUS HELPER =============

function getStatus(cert, t) {
  if (cert.revoked || cert.status === 'revoked') return { key: 'revoked', label: t('sshCertificates.statusRevoked'), tone: 'bad', icon: 'block' }
  if (cert.status === 'expired') return { key: 'expired', label: t('sshCertificates.statusExpired'), tone: 'warn', icon: 'clock' }
  if (cert.valid_to) {
    const validTo = new Date(cert.valid_to).getTime()
    if (!isNaN(validTo) && Date.now() > validTo) return { key: 'expired', label: t('sshCertificates.statusExpired'), tone: 'warn', icon: 'clock' }
  }
  return { key: 'valid', label: t('sshCertificates.statusValid'), tone: 'good', icon: 'check' }
}

const listOf = (value) => (Array.isArray(value) ? value : value ? String(value).split(',') : []).map((v) => String(v).trim()).filter(Boolean)

// ============= MAIN COMPONENT =============

export default function SSHCertificatesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { id: urlCertId } = useParams()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canRead, canWrite, canDelete } = usePermission()
  // A boolean, not canRead itself: usePermission hands out a new function on every render
  const canListSshCas = canRead('ssh_cas')
  const { copy: clipboardCopy } = useClipboard()
  const { muteToasts } = useWebSocket()

  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  const [certStats, setCertStats] = useState({ valid: 0, expired: 0, revoked: 0, total: 0 })
  const [selectedCert, setSelectedCert] = useState(null)
  const [section, setSection] = useState('overview')

  const [dialog, setDialog] = useState(null)
  const [revokingCert, setRevokingCert] = useState(null)
  const [importCertData, setImportCertData] = useState('')

  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  const [sortBy, setSortBy] = useState('id')
  const [sortOrder, setSortOrder] = useState('desc')

  const [filterStatus, setFilterStatus] = usePersistedState('ucm-ssh-certs-state', '')
  const [filterType, setFilterType] = usePersistedState('ucm-ssh-certs-type', '')
  const [filterCA, setFilterCA] = usePersistedState('ucm-ssh-certs-ca', '')
  const [searchValue, setSearchValue] = useState('')

  // ============= DATA LOADING =============

  const requestSeq = useRef(0)
  const loadData = useCallback(async () => {
    // A reload started earlier must not overwrite a later one
    const seq = ++requestSeq.current
    try {
      setLoading(true)
      const params = { page, per_page: perPage, sort_by: sortBy, sort_order: sortOrder }
      if (filterStatus) params.status = [filterStatus]
      if (filterType) params.type = [filterType]
      if (filterCA) params.ca_id = [filterCA]
      if (searchValue) params.search = searchValue

      const [certsRes, casRes, statsRes] = await Promise.all([
        sshCertificatesService.getAll(params),
        // The CA list is behind read:ssh_cas; without it, only the CA filter and picker are empty
        canListSshCas ? sshCasService.getAll() : Promise.resolve({ data: [] }),
        sshCertificatesService.getStats(),
      ])

      if (seq !== requestSeq.current) return
      setCertificates(certsRes.data || [])
      setCas(casRes.data || [])
      setCertStats(statsRes.data?.certificates || { valid: 0, expired: 0, revoked: 0, total: 0 })
      const totalCount = certsRes.meta?.total || (certsRes.data || []).length
      setTotal(totalCount)
      // The last row of the last page went away: stay on a page that exists
      const lastPage = Math.max(1, Math.ceil(totalCount / perPage))
      if (page > lastPage) setPage(lastPage)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.sshCertificates'))
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
  }, [page, perPage, sortBy, sortOrder, filterStatus, filterType, filterCA, searchValue, canListSshCas, showError, t])

  useEffect(() => { loadData() }, [loadData])

  // Deep link: /ssh-certificates/:id opens that certificate once the page holds it
  useEffect(() => {
    if (urlCertId && !loading && certificates.length > 0) {
      const id = parseInt(urlCertId, 10)
      if (!isNaN(id)) {
        const found = certificates.find((c) => c.id === id)
        if (found) setSelectedCert(found)
        navigate('/ssh-certificates', { replace: true })
      }
    }
  }, [urlCertId, loading, certificates.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // ============= ACTIONS =============

  const handleSelectCert = useCallback(async (cert) => {
    try {
      const res = await sshCertificatesService.getById(cert.id)
      setSelectedCert(res.data || cert)
    } catch {
      setSelectedCert(cert)
    }
  }, [])
  const openCert = (cert) => { if (selectedCert?.id !== cert.id) setSection('overview'); handleSelectCert(cert) }

  const handleRevoke = (cert) => { setRevokingCert(cert); setDialog('revoke') }
  const closeRevoke = () => { setDialog(null); setRevokingCert(null) }

  const handleRevokeSubmit = async (reason) => {
    if (!revokingCert) return
    try {
      muteToasts()
      const res = await sshCertificatesService.revoke(revokingCert.id, reason)
      // The KRL revokes serial 0 by key ID under the CA, any other serial by number; a key ID
      // may take a numbered certificate, whose serial takes its other holders (revoked_by)
      showSuccess(!res?.data?.revoked_with?.length
        ? t('messages.success.revoke.sshCertificate')
        : (res.data.revoked_by || []).length > 1
          ? t('sshCertificates.revokedWithKeyIdAndSerials', { keyId: revokingCert.key_id })
          : revokingCert.serial
            ? t('sshCertificates.revokedWithShared', { serial: revokingCert.serial })
            : t('sshCertificates.revokedWithKeyId', { keyId: revokingCert.key_id }))
      if (selectedCert?.id === revokingCert.id) setSelectedCert(null)
      closeRevoke()
      loadData()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(t('sshCertificates.deleteConfirm'), {
      title: t('sshCertificates.deleteCertificate'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      muteToasts()
      await sshCertificatesService.delete(cert.id)
      showSuccess(t('messages.success.delete.sshCertificate'))
      if (selectedCert?.id === cert.id) setSelectedCert(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.sshCertificate'))
    }
  }

  const handleExport = async (cert) => {
    try {
      const res = await sshCertificatesService.export(cert.id)
      const text = typeof res === 'string' ? res : (res.data?.certificate || res.data || JSON.stringify(res))
      downloadBlob(new Blob([text], { type: 'text/plain' }), sanitizeDownloadName(cert.key_id || t('sshCertificates.export.filename'), '-cert.pub'))
      showSuccess(t('sshCertificates.export.success'))
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const handleCopyText = (text) => {
    clipboardCopy(text)
    showSuccess(t('common.copied'))
  }

  const handleIssueSubmit = async (data) => {
    try {
      muteToasts()
      const { mode, ...payload } = data
      const res = mode === 'generate' ? await sshCertificatesService.generate(payload) : await sshCertificatesService.sign(payload)
      showSuccess(t('messages.success.create.sshCertificate'))
      loadData()
      // Behind the dialog, which shows a generated key only once
      if (res?.data?.id) handleSelectCert(res.data)
      return res
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
      throw error
    }
  }

  const closeImport = () => { setDialog(null); setImportCertData('') }
  const handleImportCert = async (e) => {
    e.preventDefault()
    const formData = new FormData(e.target)
    try {
      muteToasts()
      const response = await sshCertificatesService.importCertificate({ certificate: importCertData, descr: formData.get('descr') })
      showSuccess(t('messages.success.create.sshCertificate'))
      closeImport()
      loadData()
      if (response?.data?.id) handleSelectCert(response.data)
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  // A header click sorts by that column, again reverses it
  const handleSort = (key) => {
    setPage(1)
    if (sortBy === key) setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
    else { setSortBy(key); setSortOrder('asc') }
  }

  // ============= LIST =============

  const typeLabel = (c) => (c.cert_type === 'host' ? t('sshCertificates.typeHost') : t('sshCertificates.typeUser'))
  const statusPill = (c) => { const s = getStatus(c, t); return <Pill label={s.label} tone={s.tone} icon={s.icon} /> }
  const principalsCell = (c) => {
    const list = listOf(c.principals)
    if (!list.length) return '—'
    return list.length > 2 ? `${list.slice(0, 2).join(', ')} +${list.length - 2}` : list.join(', ')
  }
  const views = [
    { id: '', label: t('common.all'), count: certStats.total || 0 },
    { id: 'valid', label: t('sshCertificates.statusValid'), count: certStats.valid || 0 },
    { id: 'expired', label: t('sshCertificates.statusExpired'), count: certStats.expired || 0, warn: (certStats.expired || 0) > 0 },
    { id: 'revoked', label: t('sshCertificates.statusRevoked'), count: certStats.revoked || 0 },
  ]
  const narrowed = Boolean(searchValue || filterStatus || filterType || filterCA)
  const pages = Math.max(1, Math.ceil(total / perPage))
  const issue = canWrite('ssh') ? { label: t('sshCertificates.issueCertificate'), icon: 'plus', onClick: () => setDialog('issue'), primary: true } : undefined
  const changeFilter = (set) => (v) => { set(v); setPage(1) }

  const open = selectedCert
  const openStatus = open && getStatus(open, t)
  const criticalOptions = open?.critical_options && typeof open.critical_options === 'object' ? Object.entries(open.critical_options) : []
  const extensions = open ? (Array.isArray(open.extensions) ? open.extensions : open.extensions ? Object.keys(open.extensions) : []) : []

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('sshCertificates.title') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.key_id || t('common.unnamed'), icon: 'terminal' }]} onClose={() => setSelectedCert(null)}>
      <DockBody icon="terminal" title={open.key_id || t('common.unnamed')} badge={statusPill(open)}
        section={section} onSection={setSection} sectionsLabel={t('atelier.sectionsOf', { name: open.key_id || '' })}
        sections={[['overview', t('atelier.overview')], ['grants', t('sshCertificates.grants')], ['certificate', t('sshCertificates.certificate')]]}
        actions={<>
          <Btn icon="download" id="ssh-cert-export" onClick={() => handleExport(open)}>{t('common.export')}</Btn>
          {canWrite('ssh') && openStatus.key === 'valid' && (
            <Btn tone="danger" icon="block" id="ssh-cert-revoke" onClick={() => handleRevoke(open)}>{t('sshCertificates.revokeCertificate')}</Btn>
          )}
          {canDelete('ssh') && <Btn tone="danger" icon="block" id="ssh-cert-delete" onClick={() => handleDelete(open)}>{t('common.delete')}</Btn>}
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            {/* Another certificate of the CA holds this serial: the KRL revokes by serial */}
            {open.serial_shared_with?.length > 0 && <Notice tone="warn">{t('sshCertificates.serialSharedDetail', { serial: open.serial })}</Notice>}
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('sshCertificates.certType'), typeLabel(open)],
                [t('sshCertificates.keyId'), open.key_id || '—'],
                [t('sshCertificates.serial'), <span key="s" className="mono">{open.serial ?? '—'}</span>],
                [t('common.keyType'), open.key_type || '—'],
                [t('sshCertificates.fingerprint'), open.fingerprint ? (
                  <button key="f" type="button" className="text-link mono" title={t('common.copy')} onClick={() => handleCopyText(open.fingerprint)}>{open.fingerprint}</button>
                ) : '—'],
                [t('sshCertificates.validFrom'), open.valid_from ? formatDate(open.valid_from) : '—'],
                [t('sshCertificates.validTo'), open.valid_to ? formatDate(open.valid_to) : '—'],
                [t('atelier.state'), statusPill(open)],
              ]} />
            </Section>
            <Section title={t('sshCertificates.caInfo')}>
              <Props items={[
                [t('sshCertificates.caName'), open.ca_name || '—'],
                open.ca_fingerprint && [t('sshCertificates.caFingerprint'), <span key="cf" className="mono">{open.ca_fingerprint}</span>],
              ]} />
            </Section>
          </div>
        )}
        {section === 'grants' && (
          <div className="module-detail">
            <Section title={t('sshCertificates.grants')}>
              <Props items={[
                [t('sshCertificates.principals'), listOf(open.principals).join(', ') || '—'],
                [t('sshCertificates.extensions'), extensions.join(', ') || '—'],
                ...criticalOptions.map(([key, value]) => [key, <span key={key} className="mono">{String(value)}</span>]),
              ]} />
            </Section>
          </div>
        )}
        {section === 'certificate' && (
          <div className="module-detail">
            <Section title={t('sshCertificates.certificateText')}>
              {open.certificate ? <>
                <pre className="mono public-key">{open.certificate}</pre>
                <p className="copy-url"><Btn icon="copy" onClick={() => handleCopyText(open.certificate)}>{t('common.copy')}</Btn></p>
              </> : <p className="muted small">—</p>}
            </Section>
          </div>
        )}
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} after={<>
      {dialog === 'issue' && (
        <AtelierDialog title={t('sshCertificates.issueCertificate')} size="wide" onClose={() => setDialog(null)} returnTo="ssh-cert-new">
          <IssueCertificateForm cas={cas} canListCas={canListSshCas} onSubmit={handleIssueSubmit} onCancel={() => setDialog(null)} />
        </AtelierDialog>
      )}
      {dialog === 'import' && (
        <AtelierDialog title={t('sshCertificates.importCertificate')} subtitle={t('sshCertificates.importCertDescription')} size="wide" onClose={closeImport}>
          <form onSubmit={handleImportCert}>
            <div className="form-fields">
              <Textarea label={t('sshCertificates.certificateText')} mono value={importCertData} onChange={(e) => setImportCertData(e.target.value)}
                placeholder={t('sshCertificates.certificateDataPlaceholder')} rows={8} required />
              <Input label={t('common.description')} name="descr" full />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeImport}>{t('common.cancel')}</button>
              <Btn type="submit" tone="primary" icon="upload">{t('common.import')}</Btn>
            </div>
          </form>
        </AtelierDialog>
      )}
      {dialog === 'revoke' && revokingCert && (
        <AtelierDialog title={t('sshCertificates.revokeCertificate')} subtitle={revokingCert.key_id} size="narrow" onClose={closeRevoke} returnTo="ssh-cert-revoke">
          <RevokeCertificateForm cert={revokingCert} onSubmit={handleRevokeSubmit} onCancel={closeRevoke} />
        </AtelierDialog>
      )}
    </>}>
      <PageHead title={t('sshCertificates.title')} total={t('sshCertificates.subtitle', { count: total })} intent={t('sshCertificates.intent')}
        actions={<>
          <Btn tone="quiet" icon="terminal" id="ssh-switch" to="/ssh-cas">{t('sshCas.title')}</Btn>
          {canWrite('ssh') && <Btn icon="upload" id="ssh-cert-import" write onClick={() => setDialog('import')}>{t('common.import')}</Btn>}
          {issue && <Btn tone="primary" icon="plus" id="ssh-cert-new" onClick={issue.onClick}>{issue.label}</Btn>}
        </>} />
      <ListView label={t('sshCertificates.title')} caption={t('sshCertificates.caption')} icon="terminal" rows={certificates} loading={loading && !certificates.length}
        filters={{ views, active: filterStatus, onChange: changeFilter(setFilterStatus), label: t('sshCertificates.filterByState') }}
        toolbar={(
          <Toolbar>
            <SearchField id="ssh-cert-search" name="q" label={t('sshCertificates.searchLabel')} placeholder={t('sshCertificates.searchLabel')} value={searchValue}
              onChange={changeFilter(setSearchValue)} />
            <FilterSelect id="ssh-cert-type" label={t('sshCertificates.certType')} value={filterType} onChange={changeFilter(setFilterType)}
              options={[{ value: '', label: t('common.allTypes') }, { value: 'user', label: t('sshCertificates.typeUser') }, { value: 'host', label: t('sshCertificates.typeHost') }]} />
            {cas.length > 0 && (
              <FilterSelect id="ssh-cert-ca" label={t('sshCertificates.caName')} value={filterCA} onChange={changeFilter(setFilterCA)}
                options={[{ value: '', label: t('common.allCAs') }, ...cas.map((ca) => ({ value: String(ca.id), label: ca.name || ca.descr }))]} />
            )}
          </Toolbar>
        )}
        title={(c) => c.key_id || t('common.unnamed')} status={statusPill} openedId={open?.id} onOpen={openCert}
        sort={{ key: sortBy, asc: sortOrder === 'asc' }} onSort={handleSort} nameSort={SORTS.name}
        nameExtra={(c) => (c.serial_shared_with?.length > 0 ? <> <Pill label={t('sshCertificates.serialShared')} tone="warn" icon="warning" /></> : null)}
        columns={[
          { id: 'type', label: t('sshCertificates.certType'), cell: typeLabel, sort: SORTS.type },
          { id: 'principals', label: t('sshCertificates.principals'), cell: principalsCell, grow: true },
          { id: 'expires', label: t('sshCertificates.validTo'), cell: (c) => (c.valid_to ? formatDate(c.valid_to) : '—'), fit: true, sort: SORTS.expires },
          { id: 'ca', label: t('sshCertificates.caName'), cell: (c) => c.ca_name || '—', muted: true },
          { status: true },
        ]}
        rowActions={(c) => [
          { icon: 'download', label: t('common.export'), onClick: handleExport },
          ...(canWrite('ssh') && getStatus(c, t).key === 'valid' ? [{ icon: 'block', label: t('sshCertificates.revokeCertificate'), write: true, onClick: handleRevoke }] : []),
          ...(canDelete('ssh') ? [{ icon: 'close', label: t('common.delete'), write: true, onClick: handleDelete }] : []),
        ]}
        empty={narrowed ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setSearchValue(''); setFilterStatus(''); setFilterType(''); setFilterCA(''); setPage(1) }} />
        ) : (
          <EmptyBlock id="ssh-certs" icon="terminal" title={t('sshCertificates.noData')} text={t('sshCertificates.noDataDescription')} action={issue} />
        )}
        footer={total > 0 ? {
          range: t('sshCertificates.pageRange', { start: (page - 1) * perPage + 1, end: Math.min(page * perPage, total), count: total }),
          pagination: { page, pages, perPage, sizes: [10, 25, 50, 100], onPage: setPage, onPerPage: (n) => { setPerPage(n); setPage(1) } },
        } : undefined} />
    </Zone>
  )
}

// ============= ISSUE CERTIFICATE FORM =============

function IssueCertificateForm({ cas, canListCas = true, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const [mode, setMode] = useState('sign')
  const [caId, setCaId] = useState('')
  const [certType, setCertType] = useState('user')
  const [keyId, setKeyId] = useState('')
  const [publicKey, setPublicKey] = useState('')
  const [keyAlgorithm, setKeyAlgorithm] = useState('ed25519')
  // FIPS mode on a module without Ed25519: generated keys then default to ECDSA P-256
  const { fips, fipsKeys } = useKeyPlatform()
  const eddsaRefused = sshEddsaRefused(fips, fipsKeys)
  useEffect(() => {
    if (eddsaRefused) setKeyAlgorithm((prev) => (SSH_EDDSA_KEY_TYPES.includes(prev) ? SSH_FIPS_DEFAULT_KEY_TYPE : prev))
  }, [eddsaRefused])
  const [principalsText, setPrincipalsText] = useState('')
  const [validityPreset, setValidityPreset] = useState('24h')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [extensions, setExtensions] = useState([...DEFAULT_EXTENSIONS])
  const [showCriticalOptions, setShowCriticalOptions] = useState(false)
  const [forceCommand, setForceCommand] = useState('')
  const [sourceAddress, setSourceAddress] = useState('')

  // The first CA by default
  useEffect(() => {
    if (cas.length > 0 && !caId) setCaId(String(cas[0].id))
  }, [cas]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedCa = cas.find((c) => String(c.id) === String(caId))
  const customKeyId = !!selectedCa?.allow_custom_key_id
  const principalNames = principalsText.split(',').map((p) => p.trim()).filter(Boolean)
  // What the CA writes when the requester sets nothing, as signing.py does
  const defaultKeyId = selectedCa && principalNames.length ? `${principalNames.join(',')}@${selectedCa.descr}` : ''

  // The certificate type follows the selected CA's ca_type
  useEffect(() => {
    if (!caId) return
    const ca = cas.find((c) => String(c.id) === String(caId))
    if (ca?.ca_type && ca.ca_type !== certType) setCertType(ca.ca_type)
  }, [caId, cas]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleExtension = (ext) => setExtensions((prev) => (prev.includes(ext) ? prev.filter((e) => e !== ext) : [...prev, ext]))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!caId) return
    if (mode === 'sign' && !publicKey.trim()) return
    setLoading(true)
    try {
      const preset = VALIDITY_PRESETS.find((p) => p.value === validityPreset)
      const data = {
        mode,
        ca_id: parseInt(caId, 10),
        cert_type: certType,
        principals: principalNames,
        extensions: certType === 'user' ? extensions : [],
      }
      if (customKeyId && keyId.trim()) data.key_id = keyId.trim()
      if (preset?.seconds) data.validity_seconds = preset.seconds
      if (mode === 'sign') data.public_key = publicKey.trim()
      else data.key_type = keyAlgorithm
      if (validityPreset === 'custom') {
        // The inputs hold local time without an offset: the server reads UTC
        if (customFrom) data.valid_from = new Date(customFrom).toISOString()
        if (customTo) data.valid_to = new Date(customTo).toISOString()
      }
      const critical = {}
      if (certType === 'user' && forceCommand.trim()) critical['force-command'] = forceCommand.trim()
      if (certType === 'user' && sourceAddress.trim()) critical['source-address'] = sourceAddress.trim()
      if (Object.keys(critical).length > 0) data.critical_options = critical

      const res = await onSubmit(data)
      if (res?.data) setResult({ ...res.data, _mode: mode })
      else onCancel()
    } catch {
      // the page has shown the error
    } finally {
      setLoading(false)
    }
  }

  if (result) return <GeneratedResultView result={result} onClose={onCancel} />

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <ChoiceField name="sshIssueMode" legend={t('sshCertificates.issueMode')} value={mode} onChange={setMode}
          options={[{ value: 'sign', label: t('sshCertificates.signPublicKey') }, { value: 'generate', label: t('sshCertificates.generateKeyPair') }]} />
        <Select label={t('sshCertificates.selectCa')} value={caId} onChange={setCaId} options={cas.map((ca) => ({ value: String(ca.id), label: ca.name }))}
          placeholder={t('sshCertificates.selectCa')} error={!canListCas ? t('sshCertificates.issueNeedsCaRead') : undefined} />
        <Select label={t('sshCertificates.certType')} value={certType} onChange={setCertType}
          options={[{ value: 'user', label: t('sshCertificates.typeUser') }, { value: 'host', label: t('sshCertificates.typeHost') }]} />

        {/* Key ID: chosen only where the CA allows it, else set by the CA */}
        {customKeyId ? (
          <Input label={t('sshCertificates.keyId')} value={keyId} onChange={(e) => setKeyId(e.target.value)}
            placeholder={defaultKeyId || t('sshCertificates.modal.keyIdPlaceholder')} full />
        ) : (
          <div className="field full">
            <span>{t('sshCertificates.keyId')}</span>
            <small data-testid="ssh-key-id-set-by-ca">
              {defaultKeyId ? t('sshCertificates.modal.keyIdSetByCa', { keyId: defaultKeyId }) : t('sshCertificates.modal.keyIdSetByCaPending')}
            </small>
          </div>
        )}

        {mode === 'sign' ? (
          <Textarea label={t('sshCertificates.publicKey')} mono value={publicKey} onChange={(e) => setPublicKey(e.target.value)}
            placeholder={t('sshCertificates.modal.publicKeyPlaceholder')} rows={3} required />
        ) : (
          <Select label={t('common.keyAlgorithm')} value={keyAlgorithm} onChange={setKeyAlgorithm} options={sshKeyOptions(KEY_ALGORITHMS, fips, fipsKeys)} />
        )}

        <Input label={t('sshCertificates.principals')} value={principalsText} onChange={(e) => setPrincipalsText(e.target.value)}
          placeholder={t('sshCertificates.modal.principalsPlaceholder')} />
        <Select label={t('sshCertificates.validityPreset')} value={validityPreset} onChange={setValidityPreset}
          options={VALIDITY_PRESETS.map((p) => ({ value: p.value, label: t(`sshCertificates.presets.${p.value}`) }))} />
        {validityPreset === 'custom' && <>
          <Input type="datetime-local" label={t('sshCertificates.validFrom')} value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
          <Input type="datetime-local" label={t('sshCertificates.validTo')} required value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
        </>}

        {/* Extensions: user certificates only */}
        {certType === 'user' && (
          <fieldset className="field full">
            <legend>{t('sshCertificates.extensions')}</legend>
            <div className="choice-grid">
              {DEFAULT_EXTENSIONS.map((ext) => (
                <label key={ext} className="checkbox-line">
                  <input type="checkbox" checked={extensions.includes(ext)} onChange={() => toggleExtension(ext)} />
                  <span className="mono">{ext}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        {/* Critical options, folded as the mockup's Avancé: OpenSSH defines none for host certificates */}
        {certType === 'user' && (
          <div className="field full advanced">
            <button type="button" className="advanced-toggle" id="ssh-critical-toggle" aria-expanded={showCriticalOptions} aria-controls="ssh-critical-panel"
              onClick={() => setShowCriticalOptions((v) => !v)}>
              <Icon name={showCriticalOptions ? 'down' : 'right'} /><span>{t('sshCertificates.criticalOptions')}</span>
            </button>
            <div className="advanced-panel" id="ssh-critical-panel" hidden={!showCriticalOptions}>
              <Input label={t('sshCertificates.forceCommand')} value={forceCommand} onChange={(e) => setForceCommand(e.target.value)} placeholder="e.g. /usr/bin/rsync" />
              <Input label={t('sshCertificates.sourceAddress')} value={sourceAddress} onChange={(e) => setSourceAddress(e.target.value)} placeholder="e.g. 10.0.0.0/8,192.168.1.0/24" />
            </div>
          </div>
        )}
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <Btn type="submit" tone="primary" icon="terminal" disabled={loading || !caId || (mode === 'sign' && !publicKey.trim()) || undefined}>
          {t('sshCertificates.issueCertificate')}
        </Btn>
      </div>
    </form>
  )
}

// ============= GENERATED RESULT VIEW =============

function GeneratedResultView({ result, onClose }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()
  const { copy: clipboardCopy } = useClipboard()
  const isGenerated = result._mode === 'generate'
  const keyId = result.key_id || 'ssh_cert'
  const copy = (text) => { clipboardCopy(text); showSuccess(t('common.copied')) }
  const download = (content, filename) => downloadBlob(new Blob([content], { type: 'text/plain' }), filename)

  const block = (label, text, filename, id) => (
    <section className="field full" aria-labelledby={id}>
      <span id={id}>{label}</span>
      <pre className="mono public-key">{text}</pre>
      <div className="copy-url">
        <Btn icon="download" onClick={() => download(text, filename)}>{t('common.download')}</Btn>{' '}
        <IconBtn icon="copy" label={t('common.copy')} onClick={() => copy(text)} />
      </div>
    </section>
  )

  return (
    <div>
      <div className="notice"><Icon name="check" /><span>{t('sshCertificates.certificateIssued')}</span></div>
      {isGenerated && result.private_key && <Notice tone="warn">{t('sshCertificates.privateKeyWarning')}</Notice>}
      <div className="form-fields">
        {isGenerated && result.private_key && block(t('sshCertificates.generatedPrivateKey'), result.private_key, sanitizeDownloadName(keyId, ''), 'ssh-result-key')}
        {result.certificate && block(t('sshCertificates.generatedCertificate'), result.certificate, sanitizeDownloadName(keyId, '-cert.pub'), 'ssh-result-cert')}
        {result.public_key && block(t('sshCertificates.publicKey'), result.public_key, sanitizeDownloadName(keyId, '.pub'), 'ssh-result-pub')}
      </div>
      <div className="modal-actions">
        <Btn tone="primary" write={false} data-action="close-modal" onClick={onClose}>{t('common.close')}</Btn>
      </div>
    </div>
  )
}

// ============= REVOKE CERTIFICATE FORM =============

function RevokeCertificateForm({ cert, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await onSubmit(reason)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="notice bad" role="alert">
        <Icon name="warning" />
        <span>
          <span>{t('sshCertificates.revokeConfirm')}</span>
          {cert?.serial_shared_with?.length > 0 && <>{' '}<span>{t('sshCertificates.revokeSharedSerial', { serial: cert.serial })}</span></>}
          {cert && cert.serial === 0 && <>{' '}<span>{t('sshCertificates.revokeSerialZero', { keyId: cert.key_id })}</span></>}
        </span>
      </div>
      <div className="form-fields">
        <Textarea label={t('sshCertificates.revokeReason')} value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder={t('sshCertificates.revokeReasonPlaceholder')} rows={3} data-autofocus />
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <Btn type="submit" tone="danger" icon="block" disabled={loading || undefined}>{t('sshCertificates.revokeCertificate')}</Btn>
      </div>
    </form>
  )
}
