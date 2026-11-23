/**
 * Autorités SSH: the mockup's ssh module, a simplePage() list (Type, Clé, then the product's
 * certificate count and creation date) with its one-object dock, on the server's SSH CAs. What
 * the product has more (type chips, search, creation on a key or an HSM key, import, edit,
 * removal, the public key, the KRL, the setup scripts and commands) takes the mockup's head
 * actions, row actions, dock actions, record rows, further dock tabs and form dialog.
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  Zone, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, ListView, Dock, DockBody,
  Section, Facts, EmptyBlock, NoMatch, Input, Select, Textarea, ChoiceField, FormModal, Notice,
  useClientList, useSortParam,
} from '../components/atelier'
import { sshCasService, hsmService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useClipboard, useCRUDPage } from '../hooks'
import { useDockSelection } from '../components/atelier/useDockParam'
import { copyRow, fact } from '../components/atelier/facts'
import { PhoneMoreActions } from './pki/PhoneMoreActions'
import { CertMenu } from './certificates/inspector/CertMenu'
import { formatDate, downloadBlob, extractData } from '../lib/utils'
import { SSH_EDDSA_KEY_TYPES, SSH_FIPS_DEFAULT_KEY_TYPE, sshEddsaRefused, sshKeyOptions, useKeyPlatform } from '../lib/policyAlgorithms'
import { findAlgorithm, isUsable, GROUP_RSA, GROUP_NIST } from '../lib/keyAlgorithms'
import { sanitizeFilename } from '../lib/exportDownload'

const KEY_ALGORITHM_OPTIONS = [
  { value: 'ed25519', label: 'Ed25519' },
  { value: 'rsa', label: 'RSA 4096' },
  { value: 'ecdsa-p256', label: 'ECDSA P-256' },
  { value: 'ecdsa-p384', label: 'ECDSA P-384' },
  { value: 'ecdsa-p521', label: 'ECDSA P-521' },
]

const DEFAULT_EXTENSIONS = [
  { value: 'permit-pty', labelKey: 'sshCas.extensions.permitPty' },
  { value: 'permit-agent-forwarding', labelKey: 'sshCas.extensions.permitAgentForwarding' },
  { value: 'permit-X11-forwarding', labelKey: 'sshCas.extensions.permitX11Forwarding' },
  { value: 'permit-port-forwarding', labelKey: 'sshCas.extensions.permitPortForwarding' },
  { value: 'permit-user-rc', labelKey: 'sshCas.extensions.permitUserRc' },
]

const BY_NAME = { key: 'name', asc: true }
const SSH_CA_SORT_KEYS = ['name', 'type', 'key', 'certs', 'created']

// An HSM key decides the SSH key type it signs with: 'EC-P384' -> 'ecdsa-p384', 'RSA-3072' -> 'rsa'.
// Only RSA and NIST ECDSA: the HSM wrappers do not sign Ed25519, and OpenSSH has no Brainpool or ML-DSA type.
function hsmSshKeyType(algorithm) {
  const row = findAlgorithm(algorithm)
  if (row?.group === GROUP_RSA) return 'rsa'
  if (row?.group === GROUP_NIST) return `ecdsa-p${row.bits}`
  return null
}

function principalList(ca) {
  const listed = ca?.allowed_principals
  if (Array.isArray(listed)) return listed
  return (listed || '').split(',').map((p) => p.trim()).filter(Boolean)
}

const SSH_CA_SECTIONS = ['overview', 'install', 'config', 'key']

export default function SSHCAsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { copy: clipboardCopy, isCopied } = useClipboard()

  const loadFn = useCallback(async () => {
    const res = await sshCasService.getAll()
    return res.data || []
  }, [])
  const {
    items: sshCas, loading,
    showModal, setShowModal,
    editing: editingCA, setEditing: setEditingCA,
    loadData,
  } = useCRUDPage({ loadFn, loadErrorMsg: t('messages.errors.loadFailed.sshCas') })

  const [showImportModal, setShowImportModal] = useState(false)
  const [importCaType, setImportCaType] = useState('user')
  const [importPrivateKey, setImportPrivateKey] = useState('')
  const [query, setQuery] = useState('')
  const [typeView, setTypeView] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  // The open authority and its section live in the URL (`item`, `section`); found in the full list, not the page
  const { selected: selectedCA, select: setSelectedCA, section, setSection } = useDockSelection(sshCas, { ready: !loading, sections: SSH_CA_SECTIONS })

  // ============= ACTIONS =============

  const handleCreate = async (data) => {
    try {
      const response = await sshCasService.create(data)
      showSuccess(t('messages.success.create.sshCa'))
      setShowModal(false)
      setEditingCA(null)
      loadData()
      if (response?.data?.id) { setSelectedCA(response.data); setSection('overview') }
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.sshCa'))
      // The dialog puts the message under the field it belongs to
      throw error
    }
  }

  const handleUpdate = async (data) => {
    try {
      await sshCasService.update(editingCA.id, data)
      showSuccess(t('messages.success.update.sshCa'))
      setShowModal(false)
      setEditingCA(null)
      loadData()
      if (selectedCA?.id === editingCA.id) setSelectedCA({ ...selectedCA, ...data })
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.sshCa'))
      throw error
    }
  }

  const closeImport = () => { setShowImportModal(false); setImportCaType('user'); setImportPrivateKey('') }
  const handleImportCA = async (data) => {
    try {
      const response = await sshCasService.importCA({
        descr: data.descr, ca_type: importCaType, private_key: importPrivateKey, comment: data.comment,
      })
      showSuccess(t('messages.success.create.sshCa'))
      closeImport()
      loadData()
      if (response?.data?.id) { setSelectedCA(response.data); setSection('overview') }
    } catch (error) {
      setImportPrivateKey('')
      showError(error.message || t('messages.errors.createFailed.sshCa'))
    }
  }

  const handleDelete = async (ca) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.sshCa'), {
      title: t('sshCas.deleteCA'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      await sshCasService.delete(ca.id)
      showSuccess(t('messages.success.delete.sshCa'))
      if (selectedCA?.id === ca.id) setSelectedCA(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.sshCa'))
    }
  }

  const handleDownloadPublicKey = async (ca) => {
    try {
      // getPublicKey already returns the raw key text
      const publicKey = await sshCasService.getPublicKey(ca.id)
      downloadBlob(new Blob([publicKey], { type: 'text/plain' }), `${ca.descr || 'ssh-ca'}_key.pub`)
    } catch (error) {
      showError(error.message || t('messages.errors.downloadFailed.publicKey'))
    }
  }

  const handleDownloadKRL = async (ca) => {
    try {
      downloadBlob(await sshCasService.getKRL(ca.id), `${ca.descr || 'ssh-ca'}_krl.bin`)
    } catch (error) {
      showError(error.message || t('messages.errors.downloadFailed.krl'))
    }
  }

  const handleDownloadSetupScript = async (ca, platform = 'unix') => {
    try {
      const blob = await sshCasService.getSetupScript(ca.id, platform)
      downloadBlob(blob, `ssh_ca_setup_${sanitizeFilename(ca.descr || 'ca')}.${platform === 'windows' ? 'ps1' : 'sh'}`)
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const handleCopyPublicKey = async (ca) => {
    try {
      await clipboardCopy(await sshCasService.getPublicKey(ca.id), 'publicKey')
      showSuccess(t('sshCas.publicKeyCopied'))
    } catch (error) {
      showError(error.message || t('messages.errors.copyFailed.publicKey'))
    }
  }

  const getCurlCommand = (ca) => `curl -sSL ${window.location.origin}/ssh/setup/${ca.refid} | sudo bash`
  // Self-elevating one-liner: a new admin PowerShell window that stays open, the script run through iex
  const getPowershellCommand = (ca) => {
    const url = `${window.location.origin}/ssh/setup/${ca.refid}?platform=windows`
    return `Start-Process powershell -Verb RunAs "-NoExit -ExecutionPolicy Bypass -Command iwr '${url}' -UseBasicParsing|iex"`
  }
  const copyCommand = async (text, key, done) => {
    try {
      await clipboardCopy(text, key)
      showSuccess(t(done))
    } catch (error) {
      showError(error.message || t('messages.errors.copyFailed.publicKey'))
    }
  }

  // ============= LIST =============

  const typeLabel = (ca) => (ca.ca_type === 'user' ? t('sshCas.typeUser') : t('sshCas.typeHost'))
  const hsmPill = (ca) => (ca.key_source === 'hsm' || ca.uses_hsm ? <Pill label="HSM" icon="chip" /> : null)
  const keyCell = (ca) => <><span className="mono">{ca.key_type || '—'}</span>{hsmPill(ca) && <> {hsmPill(ca)}</>}</>

  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return sshCas.filter((ca) => !q || ['descr', 'ca_type', 'key_type', 'fingerprint', 'hsm_key_label'].some((k) => String(ca[k] || '').toLowerCase().includes(q)))
  }, [sshCas, query])
  const shown = searched.filter((ca) => !typeView || ca.ca_type === typeView)
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    { id: 'user', label: t('sshCas.typeUser'), count: searched.filter((ca) => ca.ca_type === 'user').length },
    { id: 'host', label: t('sshCas.typeHost'), count: searched.filter((ca) => ca.ca_type === 'host').length },
  ]
  // Sorted in memory (the API sends every authority), the sort in the address
  const sortParam = useSortParam(BY_NAME, SSH_CA_SORT_KEYS)
  const list = useClientList(shown, {
    sortParam,
    resetKey: `${query}|${typeView}`,
    sorts: { name: (ca) => ca.descr, type: typeLabel, key: (ca) => ca.key_type, certs: (ca) => ca.cert_count || 0, created: (ca) => ca.created_at && Date.parse(ca.created_at) },
  })
  const narrowed = Boolean(query.trim() || typeView)
  const openCreate = () => { setEditingCA(null); setShowModal(true) }
  const openEdit = (ca) => { setEditingCA(ca); setShowModal(true) }
  const create = canWrite('ssh_cas') ? { label: t('sshCas.createCA'), icon: 'plus', onClick: openCreate, primary: true } : undefined

  const footer = list.paged
    ? { range: t('sshCas.pageRange', { start: list.start, end: list.end, count: list.total }) }
    : { range: t('sshCas.range', { shown: list.total, count: sshCas.length }) }

  const open = selectedCA
  const openCA = (ca) => { if (open?.id !== ca.id) setSection('overview'); setSelectedCA(ca) }
  const principals = open ? principalList(open) : []
  // A value the authority has, else the absence in grey

  // The panel keeps its two everyday actions; the others, deletion last, in its « ⋯ » menu (CSR, templates)
  const menuItems = open ? [
    { id: 'krl', icon: 'download', label: t('sshCas.downloadKrl'), onClick: () => handleDownloadKRL(open) },
    canWrite('ssh_cas') && { id: 'edit', icon: 'settings', label: t('common.edit'), write: true, onClick: () => openEdit(open) },
    canDelete('ssh_cas') && { id: 'delete', icon: 'close', label: t('common.delete'), danger: true, write: true, onClick: () => handleDelete(open) },
  ].filter(Boolean) : []

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('sshCas.title') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.descr || t('common.unnamed'), icon: 'terminal' }]} onClose={() => setSelectedCA(null)}>
      <DockBody icon="terminal" title={open.descr || t('common.unnamed')} badge={<Pill label={typeLabel(open)} icon={open.ca_type === 'user' ? 'users' : 'server'} />}
        section={section} onSection={setSection} sectionsLabel={t('atelier.sectionsOf', { name: open.descr || '' })}
        sections={[['overview', t('atelier.overview')], ['install', t('sshCas.quickInstall')], ['config', t('sshCas.configuration')], ['key', t('sshCas.publicKey')]]}
        actions={<>
          <Btn icon="download" id="ssh-ca-pubkey" onClick={() => handleDownloadPublicKey(open)}>{t('sshCas.downloadPublicKey')}</Btn>
          <Btn icon={isCopied('publicKey') ? 'check' : 'copy'} id="ssh-ca-copy" onClick={() => handleCopyPublicKey(open)}>
            {isCopied('publicKey') ? t('sshCas.publicKeyCopied') : t('sshCas.copyPublicKey')}
          </Btn>
          <IconBtn quiet icon="more" title={false} label={t('sshCas.moreActions', { name: open.descr || '' })} data-ssh-ca-menu={open.id} onClick={() => setMenuOpen(true)} />
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Facts items={[
                [t('sshCas.caType'), typeLabel(open)],
                [t('sshCas.keyType'), keyCell(open)],
                open.key_source === 'hsm' && fact(t('cas.detail.hsmKey'), open.hsm_key_label && <span className="mono">{open.hsm_key_label}</span>),
                // An SSH fingerprint is base64, not colon-separated bytes: it wraps in the chip instead of running under its copy button
                open.fingerprint ? copyRow(t('sshCas.fingerprint'), open.fingerprint, undefined, { long: true }) : fact(t('sshCas.fingerprint'), null),
                fact(t('sshCas.serialCounter'), open.serial_counter),
                [t('sshCas.stats.certificates'), open.cert_count || 0],
                fact(t('common.created'), open.created_at && formatDate(open.created_at)),
                fact(t('common.createdBy'), open.created_by),
              ]} />
            </Section>
            <Section title={t('atelier.summary')}>
              <p className="summary">{open.allow_custom_key_id ? t('sshCas.keyIdChosenByRequester') : t('sshCas.keyIdSetByCa')}</p>
            </Section>
          </div>
        )}
        {section === 'install' && (
          <div className="module-detail">
            <Section title={t('sshCas.quickInstall')}>
              <p className="muted small">{t('sshCas.quickInstallLinuxDescription')}</p>
              <div className="command-line">
                <code className="mono">{getCurlCommand(open)}</code>
                <IconBtn icon={isCopied('curl') ? 'check' : 'copy'} label={t('common.copy')} onClick={() => copyCommand(getCurlCommand(open), 'curl', 'sshCas.curlCopied')} />
              </div>
              <p className="muted small">{t('sshCas.quickInstallWindowsDescription')}</p>
              <div className="command-line">
                <code className="mono">{getPowershellCommand(open)}</code>
                <IconBtn icon={isCopied('powershell') ? 'check' : 'copy'} label={t('common.copy')} onClick={() => copyCommand(getPowershellCommand(open), 'powershell', 'sshCas.powershellCopied')} />
              </div>
            </Section>
            <Section title={t('sshCas.downloadSetupScript')}>
              <p className="muted small">{t('sshCas.setupScriptDescription')}</p>
              <div className="copy-url">
                <Btn icon="terminal" onClick={() => handleDownloadSetupScript(open, 'unix')}>{t('sshCas.downloadSetupScriptLinux')}</Btn>
                <Btn icon="monitor" onClick={() => handleDownloadSetupScript(open, 'windows')}>{t('sshCas.downloadSetupScriptWindows')}</Btn>
              </div>
            </Section>
          </div>
        )}
        {section === 'config' && (
          <div className="module-detail">
            <Section title={t('sshCas.configuration')}>
              <Facts items={[
                // A lifetime of 0 is no lifetime set
                fact(t('sshCas.defaultTtl'), open.default_ttl || null),
                fact(t('sshCas.maxTtl'), open.max_ttl || null),
                // A list or a sentence goes under its term in a narrow panel
                open.default_extensions?.length ? { label: t('sshCas.defaultExtensions'), value: open.default_extensions.join(', '), long: true } : { label: t('sshCas.defaultExtensions'), absent: t('sshCas.noExtensions') },
                // The principal rule is a state: any principal a warning, none a CA that signs nothing
                principals.length ? { label: t('sshCas.allowedPrincipals'), value: principals.join(', '), long: true }
                  : { label: t('sshCas.allowedPrincipals'), state: open.allow_any_principal ? ['warn', t('sshCas.anyPrincipal')] : ['bad', t('sshCas.noPrincipalSignsNothing')] },
                { label: t('sshCertificates.keyId'), value: open.allow_custom_key_id ? t('sshCas.keyIdChosenByRequester') : t('sshCas.keyIdSetByCa'), long: true },
              ]} />
            </Section>
          </div>
        )}
        {section === 'key' && (
          <div className="module-detail">
            <Section title={t('sshCas.publicKey')}>
              {open.public_key ? <pre className="mono public-key">{open.public_key}</pre> : <p className="muted small">—</p>}
            </Section>
          </div>
        )}
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} after={<>
      {menuOpen && open && <CertMenu title={t('sshCas.actionsTitle')} name={open.descr || t('common.unnamed')} items={menuItems} onClose={() => setMenuOpen(false)} />}
      {showModal && (
        <SSHCAModal ca={editingCA} onSave={editingCA ? handleUpdate : handleCreate} onClose={() => { setShowModal(false); setEditingCA(null) }} />
      )}
      <FormModal open={showImportModal} onClose={closeImport} title={t('sshCas.importCA')} subtitle={t('sshCas.importCADescription')} size="lg"
        onSubmit={handleImportCA} submitLabel={t('common.import')} submitIcon="upload">
        <Input label={t('sshCas.description')} name="descr" required />
        <Select label={t('sshCas.caType')} value={importCaType} onChange={setImportCaType}
          options={[{ value: 'user', label: t('sshCas.typeUser') }, { value: 'host', label: t('sshCas.typeHost') }]} />
        <Textarea label={t('sshCas.privateKey')} mono value={importPrivateKey} onChange={(e) => setImportPrivateKey(e.target.value)}
          placeholder={t('sshCas.privateKeyPlaceholder')} rows={8} required />
        <Input label={t('common.notes')} name="comment" full />
      </FormModal>
    </>}>
      <PageHead title={t('sshCas.title')} total={t('sshCas.subtitle', { count: sshCas.length })} intent={t('sshCas.intent')}
        actions={<>
          <Btn tone="quiet" icon="terminal" id="ssh-switch" to="/ssh/certificates">{t('sshCertificates.title')}</Btn>
          {canWrite('ssh_cas') && <Btn tone="quiet" icon="upload" id="ssh-ca-import" write onClick={() => setShowImportModal(true)}>{t('common.import')}</Btn>}
          <PhoneMoreActions title={t('sshCas.title')} items={[
            { id: 'ssh-switch', icon: 'terminal', label: t('sshCertificates.title'), onClick: () => navigate('/ssh/certificates') },
            canWrite('ssh_cas') && { id: 'import', icon: 'upload', label: t('common.import'), write: true, onClick: () => setShowImportModal(true) },
          ]} />
          {create && <Btn tone="primary" icon="plus" id="ssh-ca-new" onClick={create.onClick}>{create.label}</Btn>}
        </>} />
      <ListView label={t('sshCas.title')} caption={t('sshCas.caption')} icon="terminal" list={list} nameSort="name" loading={loading && !sshCas.length}
        filters={{ views, active: typeView, onChange: setTypeView, label: t('sshCas.filterByType'),
          aside: <span id="ssh-cert-total" className="phone-aside">{t('sshCas.certTotal')} {sshCas.reduce((n, ca) => n + (ca.cert_count || 0), 0)}</span> }}
        toolbar={(
          <Toolbar>
            <SearchField id="ssh-ca-search" name="q" label={t('sshCas.searchPlaceholder')} placeholder={t('sshCas.searchPlaceholder')} value={query}
              onChange={setQuery} />
          </Toolbar>
        )}
        title={(ca) => ca.descr || t('common.unnamed')} status={() => null} openedId={open?.id} onOpen={openCA}
        // No long free text: the name takes the room left
        columns={[
          { id: 'type', label: t('sshCas.caType'), cell: typeLabel, kind: 'fit', priority: 3, sort: 'type' },
          { id: 'key', label: t('sshCas.keyType'), cell: keyCell, kind: 'fit', priority: 3, sort: 'key' },
          { id: 'certs', label: t('sshCas.stats.certificates'), cell: (ca) => ca.cert_count || 0, kind: 'number', priority: 3, sort: 'certs' },
          { id: 'created', label: t('certificates.creationColumn'), cell: (ca) => formatDate(ca.created_at), kind: 'fit', priority: 3, labelled: true, muted: true, sort: 'created' },
        ]}
        rowActions={(ca) => [
          ...(canWrite('ssh_cas') ? [{ icon: 'settings', label: t('common.edit'), write: true, onClick: openEdit }] : []),
          { icon: 'download', label: t('sshCas.downloadPublicKey'), onClick: handleDownloadPublicKey },
          ...(canDelete('ssh_cas') ? [{ icon: 'close', label: t('common.delete'), write: true, onClick: () => handleDelete(ca) }] : []),
        ]}
        empty={narrowed && sshCas.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => { setQuery(''); setTypeView('') }} />
        ) : (
          <EmptyBlock id="ssh-cas" icon="terminal" title={t('sshCas.noData')} text={t('sshCas.noDataDescription')} action={create} />
        )}
        footer={footer} />
    </Zone>
  )
}

// ============= SSH CA FORM DIALOG =============

function SSHCAModal({ ca, onSave, onClose }) {
  const { t } = useTranslation()
  // Binding a key takes the right to see the HSM inventory (the server answers 403 otherwise)
  const hsmAllowed = usePermission().canRead('hsm')
  const [loading, setLoading] = useState(false)
  // An existing CA keeps the key it was created with: only a new one chooses
  const [keySource, setKeySource] = useState(ca?.key_source === 'hsm' ? 'hsm' : 'software')
  const [hsmProviders, setHsmProviders] = useState([])
  const [hsmKeys, setHsmKeys] = useState([])
  const [hsmProviderId, setHsmProviderId] = useState('')
  const [hsmKeyId, setHsmKeyId] = useState('')
  const [hsmProvidersLoading, setHsmProvidersLoading] = useState(false)
  const [hsmKeysLoading, setHsmKeysLoading] = useState(false)
  const [fieldErrors, setFieldErrors] = useState({})
  const [formData, setFormData] = useState({
    description: ca?.descr || '',
    ca_type: ca?.ca_type || 'user',
    key_algorithm: ca?.key_algorithm || 'ed25519',
    default_ttl: ca?.default_ttl || '',
    max_ttl: ca?.max_ttl || '',
    default_extensions: ca?.default_extensions || ['permit-pty', 'permit-agent-forwarding'],
    allowed_principals: Array.isArray(ca?.allowed_principals) ? ca.allowed_principals.join(', ') : (ca?.allowed_principals || ''),
    allow_any_principal: !!ca?.allow_any_principal,
    allow_custom_key_id: !!ca?.allow_custom_key_id,
  })

  const handleChange = (field, value) => setFormData((prev) => ({ ...prev, [field]: value }))

  // FIPS mode on a module without Ed25519: a new CA then defaults to ECDSA P-256
  const { fips, fipsKeys } = useKeyPlatform()
  const eddsaRefused = sshEddsaRefused(fips, fipsKeys)
  useEffect(() => {
    if (!eddsaRefused || ca) return
    setFormData((prev) => (SSH_EDDSA_KEY_TYPES.includes(prev.key_algorithm) ? { ...prev, key_algorithm: SSH_FIPS_DEFAULT_KEY_TYPE } : prev))
  }, [eddsaRefused, ca])

  // Providers and keys exist only to pick a key for a NEW CA: an existing one already names its key
  useEffect(() => {
    if (ca || keySource !== 'hsm') return undefined
    let live = true
    setHsmProvidersLoading(true)
    hsmService.getProviders()
      .then((res) => { if (live) setHsmProviders((extractData(res) || []).filter((p) => p.enabled)) })
      .catch(() => { if (live) setHsmProviders([]) })
      .finally(() => { if (live) setHsmProvidersLoading(false) })
    return () => { live = false }
  }, [ca, keySource])

  useEffect(() => {
    if (ca || keySource !== 'hsm' || !hsmProviderId) return undefined
    let live = true
    setHsmKeysLoading(true)
    // An HSM key backs one authority, X.509 or SSH: only the free ones are offered
    hsmService.getSigningKeys({ providerId: parseInt(hsmProviderId, 10), unused: true })
      .then((res) => { if (live) setHsmKeys(extractData(res) || []) })
      .catch(() => { if (live) setHsmKeys([]) })
      .finally(() => { if (live) setHsmKeysLoading(false) })
    return () => { live = false }
  }, [ca, keySource, hsmProviderId])

  const usableHsmKeys = useMemo(() => hsmKeys.filter((k) => k.key_type === 'asymmetric' && ['signing', 'all'].includes(k.purpose)
    && isUsable(findAlgorithm(k.algorithm), { fips, fipsKeys }) && hsmSshKeyType(k.algorithm) !== null), [hsmKeys, fips, fipsKeys])
  const selectedHsmKey = usableHsmKeys.find((k) => String(k.id) === hsmKeyId)

  const toggleExtension = (ext) => setFormData((prev) => ({
    ...prev,
    default_extensions: prev.default_extensions.includes(ext) ? prev.default_extensions.filter((e) => e !== ext) : [...prev.default_extensions, ext],
  }))

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const principals = formData.allowed_principals.split(',').map((p) => p.trim()).filter(Boolean)
      const payload = {
        descr: formData.description,
        ca_type: formData.ca_type,
        // On edit an emptied field is sent as null so the server clears it
        default_ttl: formData.default_ttl || (ca ? null : undefined),
        max_ttl: formData.max_ttl || (ca ? null : undefined),
        default_extensions: formData.ca_type === 'user' ? formData.default_extensions : [],
        // An empty list is sent too: on edit, clearing the field must clear it
        allowed_principals: principals,
        allow_any_principal: formData.allow_any_principal,
        allow_custom_key_id: formData.allow_custom_key_id,
      }
      if (ca || keySource === 'software') payload.key_type = formData.key_algorithm
      // An HSM CA: the server reads the key type off the token itself
      else payload.hsm_key_id = parseInt(hsmKeyId, 10)
      setFieldErrors({})
      await onSave(payload)
    } catch (error) {
      // The page has shown the message as a toast; it also belongs under the field it is about
      if (keySource === 'hsm' && error?.message) setFieldErrors({ hsm_key: error.message })
    } finally {
      setLoading(false)
    }
  }

  const storageHint = ca ? t('sshCas.modal.keyStorageLockedHelp') : !hsmAllowed ? t('sshCas.modal.hsmNeedsRead') : undefined
  return (
    <FormModal open onClose={onClose} title={ca ? t('sshCas.editCA') : t('sshCas.createCA')} size="lg" onSubmit={handleSubmit}
      submitLabel={ca ? t('common.save') : t('common.create')} loading={loading}
      disabled={loading || !formData.description.trim() || (!ca && keySource === 'hsm' && (hsmProvidersLoading || hsmKeysLoading || !hsmProviderId || !hsmKeyId))}>
      <Input label={t('sshCas.description')} value={formData.description} onChange={(e) => handleChange('description', e.target.value)}
        placeholder={t('sshCas.modal.descriptionPlaceholder')} required full data-autofocus />

      <ChoiceField name="sshCaKeyStorage" legend={t('cas.create.keyStorage')} value={keySource} hint={storageHint}
        onChange={(mode) => { setKeySource(mode); setFieldErrors({}) }} disabled={!!ca}
        options={[
          { value: 'software', label: t('cas.create.keyStorageLocal') },
          { value: 'hsm', label: t('cas.create.keyStorageHsm'), disabled: !hsmAllowed },
        ]} />

      <Select label={t('sshCas.caType')} value={formData.ca_type} onChange={(value) => { handleChange('ca_type', value); setFieldErrors({}) }}
        options={[{ value: 'user', label: t('sshCas.typeUser') }, { value: 'host', label: t('sshCas.typeHost') }]} disabled={!!ca} />
      {keySource === 'hsm' && !ca ? (
        <Select label={t('cas.create.hsmProvider')} value={hsmProviderId} onChange={(value) => { setHsmProviderId(value); setHsmKeyId(''); setFieldErrors({}) }}
          options={hsmProviders.map((p) => ({ value: String(p.id), label: `${p.name} (${p.provider_type})` }))}
          placeholder={hsmProvidersLoading ? t('common.loading') : undefined} disabled={hsmProvidersLoading} />
      ) : (
        <Select label={t('sshCas.keyAlgorithm')} value={formData.key_algorithm} onChange={(value) => handleChange('key_algorithm', value)}
          options={ca ? KEY_ALGORITHM_OPTIONS : sshKeyOptions(KEY_ALGORITHM_OPTIONS, fips, fipsKeys)} disabled={!!ca} />
      )}

      {/* An HSM-backed CA names the key it signs with; nothing here generates one */}
      {keySource === 'hsm' && !ca && (
        !hsmProvidersLoading && hsmProviders.length === 0 ? (
          <div className="field full"><Notice tone="warn">{t('cas.create.hsmNoProviders')}</Notice></div>
        ) : hsmProviderId && !hsmKeysLoading && usableHsmKeys.length === 0 ? (
          <div className="field full"><Notice tone="warn">{t('sshCas.modal.hsmNoUsableKeys')}</Notice></div>
        ) : (
          <Select label={t('cas.create.hsmExistingKey')} value={hsmKeyId} onChange={(value) => { setHsmKeyId(value); setFieldErrors({}) }} full
            options={usableHsmKeys.map((k) => ({ value: String(k.id), label: `${k.label} (${k.algorithm})` }))}
            placeholder={hsmKeysLoading ? t('common.loading') : undefined} disabled={!hsmProviderId || hsmKeysLoading}
            error={fieldErrors.hsm_key}
            helperText={selectedHsmKey ? t('sshCas.modal.hsmDerivedKey', { keyType: hsmSshKeyType(selectedHsmKey.algorithm) }) : t('sshCas.modal.hsmKeyHelper')} />
        )
      )}

      {ca?.key_source === 'hsm' && <Input label={t('cas.detail.hsmKey')} value={ca.hsm_key_label || '—'} disabled full />}

      <Input label={t('sshCas.defaultTtl')} value={formData.default_ttl} onChange={(e) => handleChange('default_ttl', e.target.value)} placeholder={t('sshCas.modal.ttlPlaceholder')} />
      <Input label={t('sshCas.maxTtl')} value={formData.max_ttl} onChange={(e) => handleChange('max_ttl', e.target.value)} placeholder={t('sshCas.modal.ttlPlaceholder')} />

      {/* Default extensions: only for user CAs */}
      {formData.ca_type === 'user' && (
        <fieldset className="field full">
          <legend>{t('sshCas.defaultExtensions')}</legend>
          <div className="choice-grid">
            {DEFAULT_EXTENSIONS.map((ext) => (
              <label key={ext.value} className="checkbox-line">
                <input type="checkbox" checked={formData.default_extensions.includes(ext.value)} onChange={() => toggleExtension(ext.value)} />
                {t(ext.labelKey)}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <Input label={t('sshCas.allowedPrincipals')} value={formData.allowed_principals} onChange={(e) => handleChange('allowed_principals', e.target.value)}
        placeholder={t('sshCas.modal.principalsPlaceholder')} helperText={t('sshCas.modal.principalsHelperText')} full />
      <div className="field full">
        <label className="checkbox-line">
          <input type="checkbox" checked={formData.allow_any_principal} aria-describedby="hint-ssh-any" onChange={(e) => handleChange('allow_any_principal', e.target.checked)} />
          {t('sshCas.modal.allowAnyPrincipal')}
        </label>
        <small id="hint-ssh-any">{t('sshCas.modal.allowAnyPrincipalHelp')}</small>
      </div>
      <div className="field full">
        <label className="checkbox-line">
          <input type="checkbox" checked={formData.allow_custom_key_id} aria-describedby="hint-ssh-keyid" onChange={(e) => handleChange('allow_custom_key_id', e.target.checked)} />
          {t('sshCas.modal.allowCustomKeyId')}
        </label>
        <small id="hint-ssh-keyid">{t('sshCas.modal.allowCustomKeyIdHelp')}</small>
      </div>
    </FormModal>
  )
}
