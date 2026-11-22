/**
 * EST: the mockup's est module, a simplePage() list (Autorité, Authentification, État) with its
 * one-object dock, on the endpoints the product really serves: the default one and one per CA
 * label (/.well-known/est/<label>/). Its configuration takes the mockup's settingsView(). Named
 * profiles with their own activation, authentication and last request (M09) are a function the
 * product lacks: activation and HTTP Basic credentials are shared by every endpoint.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  Zone, Btn, IconBtn, Icon, Pill, PageHead, ListView, Dock, DockBody, Section, Props, SettingsView, SkeletonPanel,
  LoadError, LoadCause,
} from '../components/atelier'
import { SetupEmptyBlock } from '../components/shell/SetupEmptyBlock'
import { estService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { useDockParam } from '../components/atelier/useDockParam'
import { pickerCas, unlistedPickerCas } from '../lib/caSelection'
import { Copyable, Notice, ViewSwitch } from './protocols/atelierParts'
import { repeatedRows } from './protocols/protocolStates'

const ENDPOINTS = ['cacerts', 'simpleenroll', 'simplereenroll', 'csrattrs', 'serverkeygen']
const FIELDS = ['enabled', 'ca_id', 'validity_days', 'response_include_chain', 'username', 'password']

// Rows carry a stable id so editing a label neither reorders the list nor collides mid-typing;
// the API's object keeps the first row of a repeated label, and a repeated label blocks the save
let nextRowId = 0
const toRows = (obj) => Object.entries(obj || {}).map(([key, val]) => ({ id: ++nextRowId, key, val }))
const toObject = (rows) => {
  const seen = new Set()
  return Object.fromEntries(rows.filter((r) => !seen.has(r.key) && seen.add(r.key)).map((r) => [r.key, r.val]))
}

// The API returns labels enriched ({label: {ca_refid, ca_name}}); the PATCH takes {label: ca_refid}
const flatLabels = (labels) => Object.fromEntries(Object.entries(labels || {}).map(([label, v]) => [label, (v && typeof v === 'object') ? (v.ca_refid || '') : v]))
const draftOf = (c) => ({
  enabled: !!c.enabled, ca_id: c.ca_id != null ? String(c.ca_id) : '', validity_days: String(c.validity_days || 365),
  response_include_chain: !!c.response_include_chain, username: c.username || '', password: '',
})

const DEFAULT_ITEM = 'default'

export default function ESTPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { hasPermission } = usePermission()
  const auditPath = hasPermission('read:audit') ? '/audit' : undefined
  const canEdit = hasPermission('write:est')
  const [searchParams, setSearchParams] = useSearchParams()
  const view = searchParams.get('tab') === 'config' ? 'config' : 'list'

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [config, setConfig] = useState({})
  const [draft, setDraft] = useState(draftOf({}))
  const [rows, setRows] = useState([])
  const [cas, setCas] = useState([])
  const [stats, setStats] = useState({ total: 0, successful: 0, failed: 0 })
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState([])
  const [announce, setAnnounce] = useState('')
  const [tried, setTried] = useState(false)
  // The open endpoint lives in the URL (`item`); the default one, which has no label, is `default`
  const estDock = useDockParam()
  const openId = estDock.item == null ? null : estDock.item === DEFAULT_ITEM ? '' : estDock.item
  const setOpenId = (id) => (id == null ? estDock.close() : estDock.open(id === '' ? DEFAULT_ITEM : id))
  const stateRef = useRef(null)

  const loadData = async () => {
    setLoadError(null)
    try {
      const [configRes, casRes, statsRes] = await Promise.all([estService.getConfig(), casService.getAll(), estService.getStats()])
      const raw = configRes.data || {}
      const c = { ...raw, labels: flatLabels(raw.labels), label_names: Object.fromEntries(Object.entries(raw.labels || {}).map(([k, v]) => [k, v?.ca_name])) }
      setConfig(c)
      setDraft(draftOf(c))
      setRows(toRows(c.labels))
      setCas(casRes.data || [])
      setStats(statsRes.data || { total: 0, successful: 0, failed: 0 })
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.est'))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { loadData() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const saved = draftOf(config)
  const labels = toObject(rows)
  const labelsChanged = JSON.stringify(labels) !== JSON.stringify(config.labels || {})
  const changed = [...FIELDS.filter((k) => String(draft[k]) !== String(saved[k])), ...(labelsChanged ? ['labels'] : [])]
  const repeated = repeatedRows(rows)
  const setView = (v) => setSearchParams(v === 'config' ? { tab: 'config' } : {}, { replace: true })

  const handleSaveConfig = async () => {
    if (!canEdit) return
    setTried(true)
    if (repeated.size) {
      setAnnounce(t('est.labelsRepeated'))
      return
    }
    setSaving(true)
    setFailed([])
    try {
      const payload = {
        ...config, enabled: draft.enabled, ca_id: draft.ca_id ? parseInt(draft.ca_id, 10) : null,
        validity_days: parseInt(draft.validity_days, 10), response_include_chain: draft.response_include_chain,
        username: draft.username, labels,
      }
      delete payload.label_names
      // An empty password keeps the saved one
      if (draft.password) payload.password = draft.password
      else delete payload.password
      await estService.updateConfig(payload)
      showSuccess(t('messages.success.update.settings'))
      setAnnounce(t('messages.success.update.settings'))
      setTried(false)
      await loadData()
      stateRef.current?.focus()
    } catch (error) {
      setFailed([t('est.serverSettings')])
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
  const caOf = (id) => cas.find((c) => String(c.id) === String(id))
  const caByRefid = (refid) => cas.find((c) => c.refid === refid)
  const caLabel = (ca) => ca?.name || ca?.descr || ca?.subject
  const basic = Boolean(config.username && config.password_set)
  const auth = t(basic ? 'est.auth.certOrPassword' : 'est.auth.cert')
  const state = config.enabled ? 'active' : 'disabled'
  // No CA, no label and off: nothing configured, the list is the mockup's empty block
  const unset = !config.enabled && !config.ca_id && !Object.keys(config.labels || {}).length
  const endpoints = useMemo(() => (loading || loadError || unset ? [] : [
    { id: '', name: t('est.defaultEndpoint'), path: '/.well-known/est', ca: caLabel(caOf(config.ca_id)) || config.ca_name || '—' },
    ...Object.entries(config.labels || {}).map(([label, refid]) => ({
      id: label, name: label, path: `/.well-known/est/${label}`, ca: caLabel(caByRefid(refid)) || config.label_names?.[label] || '—',
    })),
  ]), [config, cas, loading, loadError, t]) // eslint-disable-line react-hooks/exhaustive-deps
  const open = openId === null ? null : endpoints.find((e) => e.id === openId) || null
  const pill = () => <Pill label={t(state === 'active' ? 'common.active' : 'common.disabled')} tone={state === 'active' ? 'good' : 'muted'} />

  // activeKey is the row's data-open (the default endpoint's is ''), so the focus finds the row back
  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: 'EST' })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id || 'default', title: open.name, icon: 'plug' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="plug" title={open.name} badge={pill()} section="overview" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: open.name })} sections={[['overview', t('atelier.overview')]]}
        actions={canEdit && <Btn icon="settings" id="est-configure" onClick={() => setView('config')}>{t('tsa.configure')}</Btn>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('tsa.columns.ca'), open.ca], [t('est.columns.auth'), auth], [t('atelier.state'), pill()],
              [t('est.validityDays'), String(config.validity_days || 365)],
            ]} />
            {!config.enabled && <Notice tone="warn">{t('est.estDisabledDesc')}</Notice>}
          </Section>
          <Section title={t('est.endpoints')}>
            <Props items={ENDPOINTS.map((ep) => [t(`est.${ep}`), <Copyable key={ep} url value={`${baseUrl}${open.path}/${ep}`} label={t(`est.${ep}`)} />])} />
          </Section>
          <Section title={t('atelier.summary')}>
            <p className="summary">{stats.total > 0
              ? t('est.summaryTotals', { total: stats.total, successful: stats.successful || 0, failed: stats.failed || 0 })
              : t('est.noStats')}</p>
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  const onChange = (key, value) => setDraft((d) => ({ ...d, [key]: value }))
  const off = !canEdit
  const labelOptions = pickerCas(cas, ...Object.values(labels)).filter((ca) => ca.refid)
  const unlistedLabels = unlistedPickerCas(cas, ...Object.values(labels))
  const updateRow = (id, patch) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  const labelErrors = tried && repeated.size ? 'error' : ''
  const sections = [
    {
      id: 'service', label: t('est.serverSettings'), icon: 'plug', desc: t('est.enableEstDesc'),
      groups: [{
        legend: t('est.serverSettings'),
        fields: [
          { key: 'enabled', label: t('est.enableEst'), checkbox: true, disabled: off },
          {
            key: 'ca_id', label: t('common.issuingCA'), disabled: off || !draft.enabled,
            hint: unlistedPickerCas(cas, config.ca_id) > 0 ? t('cas.notListedForSigning', { count: unlistedPickerCas(cas, config.ca_id) }) : undefined,
            options: [['', t('common.acmeSelectCA')], ...pickerCas(cas, config.ca_id).map((ca) => [String(ca.id), ca.name || ca.subject])],
          },
          { key: 'validity_days', label: t('est.validityDays'), hint: t('est.validityDaysHelp'), numeric: true, short: true, disabled: off || !draft.enabled },
          { key: 'response_include_chain', label: t('est.responseIncludeChain'), hint: t('est.responseIncludeChainHelp'), checkbox: true, disabled: off || !draft.enabled },
        ],
      }],
    },
    {
      id: 'labels', label: t('est.labels'), icon: 'branch', desc: t('est.labelsDesc'), error: labelErrors && t('est.labelsRepeated'),
      extraKeys: [['labels', t('est.labels')]],
      groups: [],
      children: (
        <fieldset className="settings-group">
          <legend>{t('est.labels')}</legend>
          <div className="row-list" id="est-labels">
            {rows.map((row, i) => {
              const duplicate = repeated.has(row.id) ? t('common.duplicateKey', { key: row.key }) : ''
              return (
                <div className="ext-row" key={row.id}>
                  <label className="sr-only" htmlFor={`est-label-${i}`}>{t('est.labelName')} {i + 1}</label>
                  <input id={`est-label-${i}`} value={row.key} placeholder={t('est.labelPlaceholder')} disabled={off || undefined}
                    aria-invalid={duplicate ? 'true' : undefined} aria-describedby={duplicate ? `est-label-err-${i}` : undefined}
                    onChange={(e) => updateRow(row.id, { key: e.target.value })} />
                  <label className="sr-only" htmlFor={`est-label-ca-${i}`}>{t('common.issuingCA')} {i + 1}</label>
                  <select id={`est-label-ca-${i}`} value={row.val} disabled={off || undefined} onChange={(e) => updateRow(row.id, { val: e.target.value })}>
                    <option value="">{t('common.acmeSelectCA')}</option>
                    {labelOptions.map((ca) => <option key={ca.refid} value={ca.refid}>{ca.name || ca.subject}</option>)}
                  </select>
                  <IconBtn icon="close" label={t('est.removeLabel', { label: row.key || i + 1 })} disabled={off || undefined}
                    onClick={() => setRows((rs) => rs.filter((r) => r.id !== row.id))} />
                  {duplicate && <p className="field-error" id={`est-label-err-${i}`}><Icon name="warning" /><span>{duplicate}</span></p>}
                </div>
              )
            })}
          </div>
          {unlistedLabels > 0 && <p className="muted small">{t('cas.notListedForSigning', { count: unlistedLabels })}</p>}
          {canEdit && (
            <button type="button" className="btn quiet add-row" id="est-label-add" onClick={() => setRows((rs) => [...rs, { id: ++nextRowId, key: '', val: '' }])}>
              <Icon name="plus" />{t('est.addLabel')}
            </button>
          )}
        </fieldset>
      ),
    },
    {
      id: 'basic', label: t('est.basicAuth'), icon: 'lock', desc: t('est.basicAuthDesc'),
      groups: [{
        legend: t('est.basicAuth'),
        fields: [
          { key: 'username', label: t('est.username'), disabled: off || !draft.enabled },
          { key: 'password', label: t('est.password'), type: 'password', placeholder: config.password_set ? '••••••••' : '', disabled: off || !draft.enabled,
            hint: config.password_set ? t('est.passwordKept') : undefined },
        ],
      }],
    },
  ]

  const listView = (
    <ListView label="EST" caption={t('est.caption')} icon="plug" rows={endpoints} loading={loading}
      filters={{ views: [{ id: '', label: t('common.all'), count: endpoints.length }, ...(endpoints.length ? [{ id: state, label: t(state === 'active' ? 'common.active' : 'common.disabled'), count: endpoints.length }] : [])], active: '', onChange: () => {}, label: t('tsa.filterByState'),
        aside: t('est.aside', { total: stats.total || 0, failed: stats.failed || 0 }) }}
      title={(r) => r.name} status={pill} openedId={open ? (open.id || '') : null} onOpen={(r) => setOpenId(r.id)}
      columns={[
        { id: 'ca', label: t('tsa.columns.ca'), cell: (r) => r.ca, grow: true },
        { id: 'auth', label: t('est.columns.auth'), cell: () => auth },
        { status: true },
      ]}
      error={loadError && (
        <LoadError id="est" journal={auditPath} title={t('messages.errors.loadFailed.est')} onRetry={() => { setLoading(true); loadData() }}
          cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/est/config', message: loadError.message }} />} />
      )}
      empty={<SetupEmptyBlock id="est" icon="plug" title={t('est.emptyTitle')} text={t('est.emptyText')}
        action={canEdit ? { label: t('tsa.configure'), icon: 'settings', onClick: () => setView('config') } : undefined} />}
      footer={{ range: t('est.range', { shown: endpoints.length, count: endpoints.length }) }} />
  )

  return (
    <Zone dock={view === 'list' ? dock : null}>
      <PageHead title="EST" intent={t('shell.moduleDesc.est')}
        total={view === 'config' ? t('protocols.sections', { count: sections.length }) : t('est.unit', { count: endpoints.length })} />
      <ViewSwitch id="est-view" label={t('protocols.view')} value={view} onChange={setView}
        options={[{ value: 'list', label: t('est.views.list'), count: loading ? null : endpoints.length }, { value: 'config', label: t('tsa.views.config') }]}>
        {view === 'list' ? listView : loading ? <SkeletonPanel label={t('common.loading')} /> : loadError ? listView : (
          <SettingsView sections={sections} values={draft} changed={changed} onChange={onChange} onSave={handleSaveConfig}
            onReset={() => { setDraft(saved); setRows(toRows(config.labels)); setTried(false) }} saving={saving} failed={failed} announce={announce}
            stateRef={stateRef} tocLabel={t('protocols.sectionsOf', { name: 'EST' })} />
        )}
      </ViewSwitch>
    </Zone>
  )
}
