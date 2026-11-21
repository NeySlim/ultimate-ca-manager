/**
 * HSM: the mockup's hsm module, a simplePage() list (Type, Clés, Dernier contrôle, État) with its
 * one-object dock, on the server's providers. What the product has more (search and type filter,
 * test, key sync, the keys and the configuration of a provider, creation, edit and removal) takes
 * the mockup's toolbar, dock actions, record rows and further dock tabs.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Zone, Icon, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, FilterSelect, ListView, Dock, DockBody,
  Section, Props, RecordList, RecordRow, LoadError, LoadCause, EmptyBlock, NoMatch,
} from '../components/atelier'
import { FormModal, Input, SecretInput, Select, Textarea, ToggleSwitch } from '../components/atelier/Form'
import { useNotification } from '../contexts'
import { usePermission, useClipboard, usePersistedState } from '../hooks'
import { hsmService } from '../services'
import { secretInputProps } from '../lib/secretTarget'
import { KEY_GROUPS, listAlgorithms } from '../lib/keyAlgorithms'
import { useFipsMode, useKeyPlatform } from '../lib/policyAlgorithms'
import { BrainpoolNotice, UntestedKeyNotice } from '../components/BrainpoolNotice'
import { dateTimeOf } from './admin/adminDates'

const PROVIDER_TYPES = [
  { value: 'pkcs11', label: 'PKCS#11 (Local HSM)' },
  { value: 'aws-cloudhsm', label: 'AWS CloudHSM' },
  { value: 'azure-keyvault', label: 'Azure Key Vault' },
  { value: 'google-kms', label: 'Google Cloud KMS' },
  { value: 'openbao', label: 'OpenBao / Vault Transit' },
]

// The provider's status as the server records it after a test; the state chips keep this order
const STATES = { connected: 'good', error: 'bad', disconnected: 'muted', unknown: 'muted' }
const stateOf = (p) => (STATES[p.status] ? p.status : 'unknown')
const typeLabel = (p) => PROVIDER_TYPES.find((x) => x.value === p.provider_type)?.label || p.provider_type

// Everything the sync route reports: counts, then what was kept or changed and why
export function syncKeysMessage(t, d) {
  const parts = [t('messages.success.hsm.keysSynced', {
    added: d.added || 0, removed: d.removed || 0, unchanged: d.unchanged || 0,
  })]
  if (d.listing_errors > 0) {
    parts.push(t('messages.success.hsm.keysSyncedUnreadable', { count: d.listing_errors }))
    // A partial listing keeps every missing key, not only those an authority holds
    if (d.missing_kept > 0) parts.push(t('messages.success.hsm.keysSyncedMissingKept', { count: d.missing_kept }))
  } else if (d.missing_kept > 0) {
    parts.push(t('messages.success.hsm.keysSyncedKept', { count: d.missing_kept }))
  }
  const changed = (d.changed_referenced_key_ids || []).length
  if (changed > 0) parts.push(t('messages.success.hsm.keysSyncedChanged', { count: changed }))
  return { text: parts.join(' '), notable: parts.length > 1 }
}

/** A configuration value that may be copied: the value in mono, then the mockup's quiet copy button. */
function Copyable({ value, label }) {
  const { t } = useTranslation()
  const { copy } = useClipboard()
  const { showSuccess } = useNotification()
  if (!value) return '—'
  return (
    <>
      <span className="mono">{value}</span>{' '}
      <IconBtn quiet icon="copy" label={t('hsm.copyValue', { name: label })} onClick={() => { copy(value); showSuccess(t('common.copied')) }} />
    </>
  )
}

/** The configuration of a provider, per type, as terms and values; secrets never shown. */
export function ProviderConfig({ provider: p }) {
  const { t } = useTranslation()
  const items = {
    pkcs11: [
      [t('hsm.pkcs11Config.slotId'), p.pkcs11_slot_id ?? 'Auto'],
      [t('hsm.pkcs11Config.token'), p.pkcs11_token_label || '—'],
      [t('hsm.pkcs11Config.libraryPath'), <Copyable key="lib" value={p.pkcs11_library_path} label={t('hsm.pkcs11Config.libraryPath')} />],
    ],
    'aws-cloudhsm': [
      [t('hsm.awsConfig.clusterId'), <Copyable key="cl" value={p.aws_cluster_id} label={t('hsm.awsConfig.clusterId')} />],
      [t('hsm.pkcs11Config.tokenLabel'), p.pkcs11_token_label || '—'],
      [t('hsm.awsConfig.cryptoUser'), p.aws_crypto_user || '—'],
    ],
    'azure-keyvault': [
      [t('hsm.azureConfig.vaultUrl'), <Copyable key="vault" value={p.azure_vault_url} label={t('hsm.azureConfig.vaultUrl')} />],
      [t('hsm.azureConfig.tenant'), p.azure_tenant_id ? <span className="mono">{p.azure_tenant_id}</span> : '—'],
      [t('hsm.azureConfig.client'), p.azure_client_id ? <span className="mono">{p.azure_client_id}</span> : '—'],
    ],
    'google-kms': [
      [t('hsm.gcpConfig.project'), p.gcp_project_id || '—'],
      [t('hsm.gcpConfig.location'), p.gcp_location || '—'],
      [t('hsm.gcpConfig.keyRing'), p.gcp_keyring || '—'],
    ],
    openbao: [
      [t('hsm.openbaoConfig.url'), <Copyable key="url" value={p.openbao_url} label={t('hsm.openbaoConfig.url')} />],
      [t('hsm.openbaoConfig.mountPath'), p.openbao_mount_path || 'transit'],
      p.openbao_namespace && [t('hsm.openbaoConfig.namespace'), p.openbao_namespace],
    ],
  }[p.provider_type] || []
  return <div className="module-detail"><Section title={t('common.config')}><Props items={items} /></Section></div>
}

// Providers served by the PKCS#11 driver record what their module reports
const PKCS11_DRIVEN = ['pkcs11', 'aws-cloudhsm']

export function ModuleSection({ provider, fips }) {
  const { t } = useTranslation()
  if (!PKCS11_DRIVEN.includes(provider.provider_type)) return null
  const m = provider.module_info
  return (
    <Section title={t('hsm.module.title')}>
      {fips && provider.softhsm && <p className="notice warn"><Icon name="warning" /><span>{t('hsm.module.softhsmFips')}</span></p>}
      {m ? (
        <Props items={[
          [t('hsm.module.library'), m.library], [t('hsm.module.manufacturer'), m.manufacturer],
          [t('hsm.module.libraryVersion'), m.library_version], [t('hsm.module.firmwareVersion'), m.firmware_version],
        ]} />
      ) : <p className="muted small">{t('hsm.module.notRead')}</p>}
    </Section>
  )
}

/** The PKCS#11 dependencies the host lacks, in the mockup's warning notice. */
function Pkcs11Notice({ status }) {
  const { t } = useTranslation()
  return (
    <div className="notice warn" id="hsm-pkcs11-notice">
      <Icon name="warning" />
      <span>
        <strong>{t('hsm.pkcs11Unavailable')}</strong>
        {!status.pkcs11_installed && <> {t('hsm.pkcs11Missing')}.</>}
        {!status.softhsm_found && <> {t('hsm.softhsmMissing')}.</>}
        {status.install_command && <> <span className="mono">{status.install_command}</span></>}
      </span>
    </div>
  )
}

export default function HSMPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.language || 'en'
  const fips = useFipsMode()
  const { canWrite, canDelete } = usePermission()
  const { showSuccess, showWarning, showError, showConfirm } = useNotification()
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [hsmStatus, setHsmStatus] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [keys, setKeys] = useState([])
  const [section, setSection] = useState('overview')
  const [modal, setModal] = useState(null)
  const [testing, setTesting] = useState(false)
  const [syncingId, setSyncingId] = useState(null)
  const syncingRef = useRef(false)
  const [state, setState] = usePersistedState('ucm-hsm-state', '')
  const [type, setType] = usePersistedState('ucm-hsm-type', '')
  const [query, setQuery] = useState('')

  const loadData = async () => {
    setLoadError(null)
    try {
      const response = await hsmService.getProviders()
      setProviders(response.data || [])
    } catch (error) {
      setLoadError(error)
      showError(t('messages.errors.loadFailed.hsmProviders'))
    } finally {
      setLoading(false)
    }
  }
  const loadKeys = async (providerId) => {
    try {
      const response = await hsmService.getKeys(providerId)
      setKeys(response.data || [])
    } catch { /* the keys tab says none were read */ }
  }

  useEffect(() => {
    loadData()
    hsmService.getStatus().then((r) => setHsmStatus(r.data)).catch(() => { /* HSM may not be configured */ })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const listed = providers.find((p) => p.id === openId) || null
  const open = listed ? { ...listed, ...(detail?.id === openId ? detail : {}) } : null
  useEffect(() => {
    setKeys([])
    if (openId != null) loadKeys(openId)
  }, [openId])

  const openProvider = (p) => {
    if (p.id !== openId) { setSection('overview'); setDetail(null) }
    setOpenId(p.id)
  }

  const handleEdit = async (provider) => {
    try {
      // The list leaves the config out: the form needs the full provider to show its type's fields
      const response = await hsmService.getProvider(provider.id)
      setModal({ kind: 'provider', provider: response.data })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.hsmProviders'))
    }
  }

  const handleDelete = async (provider) => {
    const confirmed = await showConfirm(t('messages.confirm.hsm.deleteProvider', { name: provider.name }), { variant: 'danger', confirmText: t('common.delete') })
    if (!confirmed) return
    try {
      await hsmService.deleteProvider(provider.id)
      showSuccess(t('messages.success.delete.provider'))
      setOpenId(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.provider'))
    }
  }

  const handleTest = async (provider) => {
    setTesting(true)
    try {
      const response = await hsmService.testProvider(provider.id)
      if (response.data?.success) {
        showSuccess(response.data.message || t('messages.success.hsm.connectionOk'))
        loadData()
        // The open dock shows the provider as it was before the test read the module
        const fresh = await hsmService.getProvider(provider.id).catch(() => null)
        if (fresh?.data) setDetail(fresh.data)
      } else {
        showError(response.data?.message || t('messages.errors.hsm.testFailed'))
      }
    } catch (error) {
      showError(error.message || t('messages.errors.hsm.testFailed'))
    } finally {
      setTesting(false)
    }
  }

  // One sync at a time: two at once race on the keys' unique constraint
  const handleSyncKeys = async (provider) => {
    if (syncingRef.current) return
    syncingRef.current = true
    setSyncingId(provider.id)
    try {
      const response = await hsmService.syncKeys(provider.id)
      const { text, notable } = syncKeysMessage(t, response.data || {})
      ;(notable ? showWarning : showSuccess)(text)
      loadData()
      if (openId === provider.id) loadKeys(provider.id)
    } catch (error) {
      showError(error.message || t('messages.errors.hsm.syncFailed'))
    } finally {
      syncingRef.current = false
      setSyncingId(null)
    }
  }

  const handleSave = async (formData) => {
    const editing = modal?.provider
    try {
      if (editing) {
        await hsmService.updateProvider(editing.id, formData)
        showSuccess(t('messages.success.update.provider'))
        setDetail(null)
      } else {
        await hsmService.createProvider(formData)
        showSuccess(t('messages.success.create.provider'))
      }
      setModal(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.provider'))
    }
  }

  const handleGenerateKey = async (keyData) => {
    try {
      await hsmService.addKey(openId, keyData)
      showSuccess(t('messages.success.create.key'))
      setModal(null)
      loadKeys(openId)
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.generic'))
    }
  }

  const handleDeleteKey = async (key) => {
    const confirmed = await showConfirm(t('messages.confirm.hsm.deleteKey', { name: key.label }), { variant: 'danger', confirmText: t('common.delete') })
    if (!confirmed) return
    try {
      await hsmService.deleteKey(key.id)
      showSuccess(t('messages.success.delete.key'))
      loadKeys(openId)
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.key'))
    }
  }

  const stateLabel = (p) => t(`hsm.states.${stateOf(p)}`)
  const pill = (p) => <Pill label={stateLabel(p)} tone={STATES[stateOf(p)]} />
  const checked = (p) => dateTimeOf(p.last_tested_at, locale) || t('hsm.never')
  const keyCount = (p) => t('hsm.keyCount', { count: p.key_count || 0 })

  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return providers.filter((p) => (!type || p.provider_type === type)
      && (!q || [p.name, p.provider_type, typeLabel(p)].some((v) => String(v || '').toLowerCase().includes(q))))
  }, [providers, type, query])
  const present = Object.keys(STATES).filter((s) => providers.some((p) => stateOf(p) === s))
  const active = present.includes(state) ? state : ''
  const rows = searched.filter((p) => !active || stateOf(p) === active)
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    ...present.map((s) => ({ id: s, label: t(`hsm.states.${s}`), count: searched.filter((p) => stateOf(p) === s).length })),
  ]
  const narrowed = Boolean(query.trim() || type || active)
  const usesLocalPkcs11 = providers.some((p) => (p.provider_type || p.type) === 'pkcs11')
  const create = canWrite('hsm') ? { label: t('hsm.newProvider'), icon: 'plus', onClick: () => setModal({ kind: 'provider', provider: null }), primary: true } : undefined

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('shell.moduleLabel.hsm') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.name, icon: 'chip' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="chip" title={open.name} badge={pill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: open.name })}
        sections={[['overview', t('atelier.overview')], ['keys', t('hsm.hsmKeys')], ['config', t('common.config')]]}
        actions={<>
          <Btn icon="refresh" id="hsm-test" disabled={testing || undefined} onClick={() => handleTest(open)}>{testing ? t('common.testing') : t('common.test')}</Btn>
          {canWrite('hsm') && (
            <Btn icon="key" id="hsm-sync" write disabled={syncingId !== null || undefined} onClick={() => handleSyncKeys(open)}>
              {syncingId === open.id ? t('hsm.syncingKeys') : t('common.syncKeys')}
            </Btn>
          )}
          {canWrite('hsm') && <Btn icon="settings" id="hsm-edit" write onClick={() => handleEdit(open)}>{t('common.edit')}</Btn>}
          {canDelete('hsm') && <Btn tone="danger" icon="block" id="hsm-delete" onClick={() => handleDelete(open)}>{t('hsm.deleteProvider')}</Btn>}
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('hsm.columns.type'), typeLabel(open)], [t('hsm.columns.keys'), keyCount(open)], [t('hsm.columns.checked'), checked(open)],
                [t('atelier.state'), pill(open)],
                [t('hsm.certification.label'), open.certification ? t(`hsm.certification.values.${open.certification}`, open.certification) : t('hsm.certification.notDeclared')],
              ]} />
              {open.error_message && (
                <p className="notice warn" id="hsm-error"><Icon name="warning" /><span><strong>{t('hsm.connectionError')}</strong> : {open.error_message}</span></p>
              )}
            </Section>
            <Section title={t('atelier.summary')}>
              <p className="summary">{keys.length ? t('hsm.summaryKeys', { names: keys.map((k) => k.label).join(', ') }) : t('hsm.noKeysInHsm')}</p>
            </Section>
            <ModuleSection provider={open} fips={fips} />
          </div>
        )}
        {section === 'keys' && (
          <div className="module-detail">
            <Section title={t('hsm.keysInHsm', { count: keys.length })}>
              <RecordList empty={t('hsm.noKeysInHsm')}>
                {keys.map((k) => (
                  <RecordRow key={k.id} title={k.label} meta={[k.algorithm || k.key_type, k.purpose].filter(Boolean).join(' · ')}
                    action={canDelete('hsm') && (
                      <Btn icon="block" write aria-label={t('hsm.deleteKey', { name: k.label })} onClick={() => handleDeleteKey(k)}>{t('common.delete')}</Btn>
                    )} />
                ))}
              </RecordList>
              {canWrite('hsm') && <div className="copy-url"><Btn icon="plus" id="hsm-generate" write onClick={() => setModal({ kind: 'key' })}>{t('common.generate')}</Btn></div>}
            </Section>
          </div>
        )}
        {section === 'config' && <ProviderConfig provider={open} />}
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} after={<>
      {modal?.kind === 'provider' && <ProviderModal provider={modal.provider} hsmStatus={hsmStatus} onSave={handleSave} onClose={() => setModal(null)} />}
      {modal?.kind === 'key' && open && <KeyModal provider={open} onSave={handleGenerateKey} onClose={() => setModal(null)} />}
    </>}>
      <PageHead title={t('shell.moduleLabel.hsm')} total={t('hsm.unit', { count: providers.length })} intent={t('shell.moduleDesc.hsm')}
        actions={create && <Btn tone="primary" icon="plus" id="hsm-new" onClick={create.onClick}>{create.label}</Btn>} />
      {hsmStatus && !hsmStatus.ready && usesLocalPkcs11 && <Pkcs11Notice status={hsmStatus} />}
      <ListView label={t('shell.moduleLabel.hsm')} caption={t('hsm.caption')} icon="chip" rows={rows} loading={loading}
        filters={{ views, active, onChange: setState, label: t('hsm.filterByState') }}
        toolbar={(
          <Toolbar>
            <SearchField id="hsm-search" name="q" label={t('common.searchProviders')} placeholder={t('common.searchProviders')} value={query} onChange={setQuery} />
            <FilterSelect id="hsm-type" label={t('hsm.filterByType')} value={type} onChange={setType}
              options={[{ value: '', label: t('common.allTypes') }, ...PROVIDER_TYPES.map((x) => ({ value: x.value, label: x.label }))]} />
          </Toolbar>
        )}
        title={(p) => p.name} status={pill} openedId={openId} onOpen={openProvider}
        columns={[
          { id: 'type', label: t('hsm.columns.type'), cell: typeLabel, grow: true },
          { id: 'keys', label: t('hsm.columns.keys'), cell: keyCount },
          { id: 'checked', label: t('hsm.columns.checked'), cell: checked },
          { status: true },
        ]}
        error={loadError && (
          <LoadError id="hsm" title={t('messages.errors.loadFailed.hsmProviders')} onRetry={() => { setLoading(true); loadData() }}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/hsm/providers', message: loadError.message }} />} />
        )}
        empty={narrowed && providers.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setQuery(''); setType(''); setState('') }} />
        ) : (
          <EmptyBlock id="hsm" icon="chip" title={t('hsm.noHSM')} text={t('hsm.noHSMDescription')} action={create} />
        )}
        footer={{ range: t('hsm.range', { shown: rows.length, count: providers.length }) }} />
    </Zone>
  )
}

// Per type: the saved credential and the form fields it stays with (as on the server)
const SECRET_TARGETS = {
  pkcs11: ['pkcs11_pin', ['pkcs11_library_path', 'pkcs11_token_label', 'pkcs11_slot_id']],
  'aws-cloudhsm': ['aws_crypto_password', ['aws_cluster_id', 'aws_crypto_user']],
  'azure-keyvault': ['azure_client_secret', ['azure_vault_url', 'azure_tenant_id', 'azure_client_id']],
  openbao: ['openbao_token', ['openbao_url', 'openbao_mount_path', 'openbao_namespace',
    'openbao_tls_skip_verify']],
}

export const HSM_CERTIFICATIONS = ['cc-eal4+', 'eucc-high', 'fips-140-3-l3', 'fips-140-2-l3', 'other']

export function ProviderModal({ provider, hsmStatus, onSave, onClose }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    provider_type: provider?.provider_type || 'pkcs11',
    connection_timeout: provider?.connection_timeout || 30,
    pkcs11_library_path: provider?.pkcs11_library_path || '',
    pkcs11_slot_id: provider?.pkcs11_slot_id ?? '',
    pkcs11_pin: provider?.pkcs11_pin || '',
    pkcs11_token_label: provider?.pkcs11_token_label || '',
    aws_cluster_id: provider?.aws_cluster_id || '',
    aws_crypto_user: provider?.aws_crypto_user || '',
    aws_crypto_password: provider?.aws_crypto_password || '',
    azure_vault_url: provider?.azure_vault_url || '',
    azure_tenant_id: provider?.azure_tenant_id || '',
    azure_client_id: provider?.azure_client_id || '',
    azure_client_secret: provider?.azure_client_secret || '',
    gcp_project_id: provider?.gcp_project_id || '',
    gcp_location: provider?.gcp_location || 'global',
    gcp_keyring: provider?.gcp_keyring || '',
    gcp_credentials_json: provider?.gcp_credentials_json || '',
    openbao_url: provider?.openbao_url || '',
    openbao_token: provider?.openbao_token || '',
    openbao_mount_path: provider?.openbao_mount_path || 'transit',
    openbao_namespace: provider?.openbao_namespace || '',
    openbao_tls_skip_verify: provider?.openbao_tls_skip_verify ?? false,
    certification: provider?.certification || '',
  })

  const handleChange = (field, value) => setFormData(prev => ({ ...prev, [field]: value }))

  // The form as loaded: what the saved credential was saved for
  const [savedForm] = useState(formData)
  const [secretField, targetFields] = SECRET_TARGETS[formData.provider_type] || []
  const secretTarget = secretField ? {
    saved: savedForm, current: formData, fields: targetFields, secret: formData[secretField],
    secretSaved: provider?.[secretField] === '***',
  } : null
  const secretProps = (field) => (field === secretField ? secretInputProps(t, secretTarget) : {})

  const buildPayload = () => {
    const config = {}
    if (formData.provider_type === 'pkcs11') {
      config.module_path = formData.pkcs11_library_path
      config.token_label = formData.pkcs11_token_label
      config.user_pin = formData.pkcs11_pin
      if (formData.pkcs11_slot_id !== '') config.slot_index = formData.pkcs11_slot_id
    } else if (formData.provider_type === 'aws-cloudhsm') {
      config.module_path = formData.pkcs11_library_path || '/opt/cloudhsm/lib/libcloudhsm_pkcs11.so'
      config.hsm_user = formData.aws_crypto_user
      config.hsm_password = formData.aws_crypto_password
      config.cluster_id = formData.aws_cluster_id
      config.token_label = formData.pkcs11_token_label
    } else if (formData.provider_type === 'azure-keyvault') {
      config.vault_url = formData.azure_vault_url
      config.tenant_id = formData.azure_tenant_id
      config.client_id = formData.azure_client_id
      config.client_secret = formData.azure_client_secret
    } else if (formData.provider_type === 'google-kms') {
      config.project_id = formData.gcp_project_id
      config.location = formData.gcp_location
      config.key_ring = formData.gcp_keyring
      // '***' keeps the stored key; left out, the saved config has none and the
      // provider uses the server's default credentials
      if (formData.gcp_credentials_json) config.service_account_json = formData.gcp_credentials_json
    } else if (formData.provider_type === 'openbao') {
      config.url = formData.openbao_url
      config.token = formData.openbao_token
      config.mount_path = formData.openbao_mount_path || 'transit'
      if (formData.openbao_namespace) config.namespace = formData.openbao_namespace
      config.tls_skip_verify = formData.openbao_tls_skip_verify
    }
    // '' clears the declaration on the server
    return { name: formData.name, type: formData.provider_type, config, certification: formData.certification }
  }

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title={provider ? t('hsm.editProvider') : t('hsm.newProvider')}
      size="lg"
      onSubmit={() => onSave(buildPayload())}
      submitLabel={provider ? t('common.save') : t('common.create')}
    >
      <Input id="hsm-provider-name" label={t('common.providerName')} value={formData.name} onChange={e => handleChange('name', e.target.value)} required full={!!provider} data-autofocus="" />
      {!provider && (
        <Select id="hsm-provider-type" label={t('common.providerType')} value={formData.provider_type} onChange={value => handleChange('provider_type', value)} options={PROVIDER_TYPES} />
      )}

      {formData.provider_type === 'pkcs11' && (
        <>
          {hsmStatus && !hsmStatus.ready && <Pkcs11Notice status={hsmStatus} />}
          <Input id="hsm-pkcs11-library" label={t('hsm.pkcs11Config.libraryPath')} full value={formData.pkcs11_library_path} onChange={e => handleChange('pkcs11_library_path', e.target.value)} placeholder={t('hsm.pkcs11Config.libraryPathPlaceholder')} />
          <Input id="hsm-pkcs11-slot" label={t('hsm.pkcs11Config.slotId')} type="number" value={formData.pkcs11_slot_id} onChange={e => handleChange('pkcs11_slot_id', e.target.value ? parseInt(e.target.value) : '')} />
          <Input id="hsm-pkcs11-token" label={t('hsm.pkcs11Config.tokenLabel')} value={formData.pkcs11_token_label} onChange={e => handleChange('pkcs11_token_label', e.target.value)} />
          <SecretInput id="hsm-pkcs11-pin" label={t('hsm.pkcs11Config.pin')} full value={formData.pkcs11_pin === '***' ? '' : (formData.pkcs11_pin || '')} onChange={e => handleChange('pkcs11_pin', e.target.value)} hasExistingValue={provider?.pkcs11_pin === '***'} {...secretProps('pkcs11_pin')} />
        </>
      )}

      {formData.provider_type === 'aws-cloudhsm' && (
        <>
          <Input id="hsm-aws-cluster" label={t('hsm.awsConfig.clusterId')} value={formData.aws_cluster_id} onChange={e => handleChange('aws_cluster_id', e.target.value)} />
          <Input id="hsm-aws-token" label={t('hsm.pkcs11Config.tokenLabel')} value={formData.pkcs11_token_label} onChange={e => handleChange('pkcs11_token_label', e.target.value)} />
          <Input id="hsm-aws-user" label={t('hsm.awsConfig.cryptoUser')} value={formData.aws_crypto_user} onChange={e => handleChange('aws_crypto_user', e.target.value)} />
          <SecretInput id="hsm-aws-password" label={t('hsm.awsConfig.cryptoPassword')} value={formData.aws_crypto_password === '***' ? '' : (formData.aws_crypto_password || '')} onChange={e => handleChange('aws_crypto_password', e.target.value)} hasExistingValue={provider?.aws_crypto_password === '***'} {...secretProps('aws_crypto_password')} />
        </>
      )}

      {formData.provider_type === 'azure-keyvault' && (
        <>
          <Input id="hsm-azure-vault" label={t('hsm.azureConfig.vaultUrl')} full value={formData.azure_vault_url} onChange={e => handleChange('azure_vault_url', e.target.value)} placeholder={t('hsm.azureConfig.vaultUrlPlaceholder')} />
          <Input id="hsm-azure-tenant" label={t('hsm.azureConfig.tenantId')} value={formData.azure_tenant_id} onChange={e => handleChange('azure_tenant_id', e.target.value)} />
          <Input id="hsm-azure-client" label={t('common.clientId')} value={formData.azure_client_id} onChange={e => handleChange('azure_client_id', e.target.value)} />
          <SecretInput id="hsm-azure-secret" label={t('common.clientSecret')} full value={formData.azure_client_secret === '***' ? '' : (formData.azure_client_secret || '')} onChange={e => handleChange('azure_client_secret', e.target.value)} hasExistingValue={provider?.azure_client_secret === '***'} {...secretProps('azure_client_secret')} />
        </>
      )}

      {formData.provider_type === 'google-kms' && (
        <>
          <Input id="hsm-gcp-project" label={t('hsm.gcpConfig.projectId')} value={formData.gcp_project_id} onChange={e => handleChange('gcp_project_id', e.target.value)} />
          <Input id="hsm-gcp-location" label={t('hsm.gcpConfig.location')} value={formData.gcp_location} onChange={e => handleChange('gcp_location', e.target.value)} />
          <Input id="hsm-gcp-keyring" label={t('hsm.gcpConfig.keyRing')} full value={formData.gcp_keyring} onChange={e => handleChange('gcp_keyring', e.target.value)} />
          <Textarea
            id="hsm-gcp-credentials"
            label={t('hsm.gcpConfig.credentialsJson')}
            mono
            rows={4}
            value={formData.gcp_credentials_json === '***' ? '' : formData.gcp_credentials_json}
            onChange={e => handleChange('gcp_credentials_json', e.target.value || (provider?.gcp_credentials_json === '***' ? '***' : ''))}
            placeholder='{"type":"service_account", ...}'
            disabled={provider?.gcp_credentials_json === '***' && !formData.gcp_credentials_json}
            helperText={provider?.gcp_credentials_json === '***' ? t('hsm.gcpConfig.credentialsJsonStored') : t('hsm.gcpConfig.credentialsJsonHelp')}
          />
          {provider?.gcp_credentials_json === '***' && (
            <ToggleSwitch
              checked={!formData.gcp_credentials_json}
              onChange={(val) => handleChange('gcp_credentials_json', val ? '' : '***')}
              label={t('hsm.gcpConfig.useDefaultCredentials')}
            />
          )}
        </>
      )}

      {formData.provider_type === 'openbao' && (
        <>
          <Input id="hsm-openbao-url" label={t('hsm.openbaoConfig.url')} full value={formData.openbao_url} onChange={e => handleChange('openbao_url', e.target.value)} placeholder="https://openbao.example.com:8200" required />
          <SecretInput id="hsm-openbao-token" label={t('hsm.openbaoConfig.token')} full value={formData.openbao_token === '***' ? '' : (formData.openbao_token || '')} onChange={e => handleChange('openbao_token', e.target.value)} hasExistingValue={provider?.openbao_token === '***'} {...secretProps('openbao_token')} />
          <Input id="hsm-openbao-mount" label={t('hsm.openbaoConfig.mountPath')} value={formData.openbao_mount_path} onChange={e => handleChange('openbao_mount_path', e.target.value)} placeholder="transit" />
          <Input id="hsm-openbao-namespace" label={t('hsm.openbaoConfig.namespace')} value={formData.openbao_namespace} onChange={e => handleChange('openbao_namespace', e.target.value)} placeholder={t('common.optional')} />
          <ToggleSwitch
            checked={formData.openbao_tls_skip_verify}
            onChange={(val) => handleChange('openbao_tls_skip_verify', val)}
            label={t('hsm.openbaoConfig.tlsSkipVerify')}
          />
        </>
      )}

      <Select
        id="hsm-certification"
        full
        label={t('hsm.certification.label')}
        value={formData.certification}
        onChange={value => handleChange('certification', value)}
        options={[{ value: '', label: t('hsm.certification.notDeclared') }, ...HSM_CERTIFICATIONS.map(v => ({ value: v, label: t(`hsm.certification.values.${v}`) }))]}
        helperText={t('hsm.certification.hint')}
      />
    </FormModal>
  )
}

// Symmetric keys are not in the key registry
const AES_ALGORITHMS = ['AES-128', 'AES-256']
const AES_GROUP = 'aes'

export function KeyModal({ provider, onSave, onClose }) {
  const { t } = useTranslation()
  const platform = useKeyPlatform()
  const providerType = provider?.provider_type ?? ''
  const asymmetric = listAlgorithms({ generate: true, provider: providerType, ...platform })
  const groupOptions = [
    ...KEY_GROUPS.filter(g => asymmetric.some(a => a.group === g.id)).map(g => ({ value: g.id, label: t(g.labelKey) })),
    { value: AES_GROUP, label: t('common.keyGroups.aes') },
  ]
  const algorithmsOf = (group) => (group === AES_GROUP
    ? AES_ALGORITHMS
    : asymmetric.filter(a => a.group === group).map(a => a.label))

  const [formData, setFormData] = useState(() => ({
    label: '',
    group: groupOptions[0].value,
    algorithm: algorithmsOf(groupOptions[0].value)[0],
    purpose: 'signing',
    extractable: false,
  }))
  // The policy answer can withdraw the group picked before it (ML-DSA in FIPS mode)
  const groupGone = !groupOptions.some(g => g.value === formData.group)
  useEffect(() => {
    if (groupGone) {
      setFormData(f => ({ ...f, group: groupOptions[0].value, algorithm: algorithmsOf(groupOptions[0].value)[0] }))
    }
  }, [groupGone]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = () => {
    onSave({
      label: formData.label,
      algorithm: formData.algorithm,
      purpose: formData.purpose,
      extractable: formData.extractable,
    })
  }

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title={t('hsm.generateHsmKey')}
      size="md"
      onSubmit={handleSubmit}
      submitLabel={t('common.generate')}
    >
      <Input id="hsm-key-label" label={t('hsm.keyLabel')} full value={formData.label} onChange={e => setFormData({...formData, label: e.target.value})} required placeholder={t('hsm.keyLabelPlaceholder')} data-autofocus="" />
        <Select
          id="hsm-key-group"
          label={t('common.keyType')}
          value={formData.group}
          onChange={value => setFormData({ ...formData, group: value, algorithm: algorithmsOf(value)[0] })}
          options={groupOptions}
        />
        <Select
          id="hsm-key-algorithm"
          label={t('common.keySize')}
          value={formData.algorithm}
          onChange={value => setFormData({ ...formData, algorithm: value })}
          options={algorithmsOf(formData.group).map(label => ({ value: label, label }))}
          after={<><BrainpoolNotice atelier label={formData.algorithm} /><UntestedKeyNotice atelier label={formData.algorithm} provider={providerType} /></>}
        />
      <Select id="hsm-key-purpose" full label={t('common.purpose')} value={formData.purpose} onChange={value => setFormData({...formData, purpose: value})} options={[{ value: 'signing', label: t('hsm.purposes.caSigning') }, { value: 'encryption', label: t('common.smtpEncryption') }, { value: 'wrapping', label: t('hsm.purposes.general') }, { value: 'all', label: t('common.all') }]} />
    </FormModal>
  )
}
