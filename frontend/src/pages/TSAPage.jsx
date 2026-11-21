/**
 * TSA: the mockup's tsa module, a simplePage() list (Autorité, Hachage, Politique, État) with its
 * one-object dock, on the product's one time-stamping service; its configuration takes the mockup's
 * settingsView(). Several named services (M10) and token counts over 7 days (M11) are functions
 * the product lacks: the list holds the one service, the dock the totals the server keeps.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  Zone, Btn, Pill, PageHead, ListView, Dock, DockBody, Section, Props, SettingsView, SkeletonPanel,
  LoadError, LoadCause, EmptyBlock,
} from '../components/atelier'
import { Input, Select, FormModal } from '../components'
import { tsaService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { hiddenFromIssuance, listedForIssuance, pickerCas, unlistedPickerCas } from '../lib/caSelection'
import { HiddenCasToggle } from '../components/cas/HiddenCasToggle'
import { certificateLabel } from '../lib/utils'
import { TSA_LABELS, findAlgorithm, groupedOptions, listAlgorithms } from '../lib/keyAlgorithms'
import { useKeyPlatform } from '../lib/policyAlgorithms'
import { BrainpoolNotice } from '../components/BrainpoolNotice'
import { dateTimeOf } from './admin/adminDates'
import { Copyable, Notice, ViewSwitch } from './protocols/atelierParts'

// OpenSSL's example policy OID, assigned to no one
const DEFAULT_POLICY_OID = '1.2.3.4.1'
// The digests a request may carry in its messageImprint (services/tsa_service.py)
const DIGESTS = 'SHA-256, SHA-384, SHA-512'
const FIELDS = ['enabled', 'ca_refid', 'policy_oid', 'signer_cert_refid', 'require_dedicated_cert']

// The signer request names its key as the issue API does: the registry row's `issue` pair
function signerKey(label) {
  const [key_type, key_size] = findAlgorithm(label)?.issue || [label]
  return { key_type, key_size }
}

const draftOf = (c) => ({
  enabled: !!c.enabled, ca_refid: c.ca_refid || '', policy_oid: c.policy_oid || DEFAULT_POLICY_OID,
  signer_cert_refid: c.signer_cert_refid || '', require_dedicated_cert: c.require_dedicated_cert !== false,
})

export default function TSAPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { showSuccess, showError } = useNotification()
  const { hasPermission } = usePermission()
  const auditPath = hasPermission('read:audit') ? '/audit' : undefined
  const canEdit = hasPermission('write:settings')
  const platform = useKeyPlatform()
  const [searchParams, setSearchParams] = useSearchParams()
  const view = searchParams.get('tab') === 'config' ? 'config' : 'list'

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [config, setConfig] = useState({})
  const [draft, setDraft] = useState(draftOf({}))
  const [cas, setCas] = useState([])
  const [signerCandidates, setSignerCandidates] = useState([])
  const [stats, setStats] = useState({ total: 0 })
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState([])
  const [announce, setAnnounce] = useState('')
  const [opened, setOpened] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genForm, setGenForm] = useState(null)
  const [showHiddenCas, setShowHiddenCas] = useState(false)
  const stateRef = useRef(null)

  const loadData = async () => {
    setLoadError(null)
    try {
      const [configRes, casRes, statsRes, candidatesRes] = await Promise.all([
        tsaService.getConfig(), casService.getAll(), tsaService.getStats(), tsaService.getSignerCandidates(),
      ])
      const c = configRes.data || {}
      setConfig(c)
      setDraft(draftOf(c))
      setCas(casRes.data || [])
      setStats(statsRes.data || { total: 0 })
      setSignerCandidates(candidatesRes.data || [])
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.tsa'))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { loadData() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const saved = draftOf(config)
  const changed = FIELDS.filter((k) => String(draft[k]) !== String(saved[k]))
  const setView = (v) => setSearchParams(v === 'config' ? { tab: 'config' } : {}, { replace: true })

  const handleSaveConfig = async () => {
    if (!canEdit) return
    setSaving(true)
    setFailed([])
    try {
      await tsaService.updateConfig({ ...config, ...draft })
      showSuccess(t('messages.success.update.settings'))
      setAnnounce(t('messages.success.update.settings'))
      // Re-read so the resolved signer status (expiry, chain, usability) gates the strict mode
      await loadData()
      stateRef.current?.focus()
    } catch (error) {
      setFailed([t('tsa.sections.service')])
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const openGenerate = () => {
    setGenForm({ ca_refid: draft.ca_refid || (cas[0]?.refid ?? ''), cn: 'UCM Timestamping Authority', validity_days: 397, key_type: TSA_LABELS[0] })
    setShowHiddenCas(false)
    setGenerateOpen(true)
  }

  const handleGenerateSigner = async () => {
    if (!genForm) return
    setGenerating(true)
    try {
      const key = signerKey(genForm.key_type || TSA_LABELS[0])
      const res = await tsaService.issueSignerCertificate({
        ca_refid: genForm.ca_refid || undefined,
        cn: genForm.cn || undefined,
        // Whatever was typed (0 included) goes to the server, which refuses it
        validity_days: String(genForm.validity_days ?? '').trim() === '' ? undefined : Number(genForm.validity_days),
        ...key,
      })
      setGenerateOpen(false)
      showSuccess(res?.data?.selected ? t('tsa.signerGeneratedSelected') : t('tsa.signerGenerated'))
      await loadData()
    } catch (error) {
      showError(error.message || t('tsa.signerGenerateFailed'))
    } finally {
      setGenerating(false)
    }
  }

  // config.signer describes what is SAVED: its status counts only for the current selection
  const signerStatus = config.signer && config.signer.refid === draft.signer_cert_refid ? config.signer : null
  const selectionUnsaved = Boolean(draft.signer_cert_refid) && !signerStatus
  const dedicatedSignerReady = Boolean(signerStatus?.usable)
  const strictMode = draft.require_dedicated_cert
  // Without a saved dedicated signer, the CA certificate signs (strict mode off) or /tsa signs nothing
  const noSavedSigner = !config.signer?.configured
  const signerWarning = (strict) => (noSavedSigner ? (strict ? 'tsa.strictNoSigner' : 'tsa.caSignerWarning') : null)
  const placeholderPolicy = (draft.policy_oid || DEFAULT_POLICY_OID) === DEFAULT_POLICY_OID

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
  const caName = (refid) => {
    const ca = cas.find((c) => c.refid === refid)
    return ca?.name || ca?.descr || ca?.subject || config.ca_name || '—'
  }
  const service = useMemo(() => (loading || loadError ? [] : [{
    id: 'tsa', name: t('tsa.serviceName'), ca: caName(config.ca_refid), policy: config.policy_oid || DEFAULT_POLICY_OID,
    state: config.enabled ? 'active' : 'disabled',
  }]), [config, cas, loading, loadError, t]) // eslint-disable-line react-hooks/exhaustive-deps
  const row = service[0]
  const pill = (r) => <Pill label={t(r.state === 'active' ? 'common.active' : 'common.disabled')} tone={r.state === 'active' ? 'good' : 'muted'} />
  const signerText = config.signer?.configured
    ? (config.signer.subject || config.signer.refid)
    : t('tsa.signingCertCa')
  const summary = t('tsa.summaryTotals', { total: stats.total || 0, successful: stats.successful || 0, failed: stats.failed || 0 })

  const dock = opened && row && (
    <Dock label={t('atelier.detailOf', { name: 'TSA' })} tabsLabel={t('atelier.openItem')} activeKey={row.id}
      tabs={[{ key: row.id, title: row.name, icon: 'stamp' }]} onClose={() => setOpened(false)}>
      <DockBody icon="stamp" title={row.name} badge={pill(row)} section="overview" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: row.name })} sections={[['overview', t('atelier.overview')]]}
        actions={canEdit && <Btn icon="settings" id="tsa-configure" onClick={() => setView('config')}>{t('tsa.configure')}</Btn>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('tsa.columns.ca'), row.ca], [t('tsa.columns.digest'), DIGESTS], [t('tsa.columns.policy'), <span key="p" className="mono">{row.policy}</span>],
              [t('atelier.state'), pill(row)], [t('tsa.signingCert'), signerText],
              config.signer?.not_after && [t('tsa.signerExpires'), dateTimeOf(config.signer.not_after, locale)],
              ['URL', <Copyable key="u" url value={`${baseUrl}/tsa`} label={t('tsa.endpoint')} />],
            ]} />
            {!config.enabled && <Notice tone="warn">{t('tsa.tsaDisabledDesc')}</Notice>}
            {signerWarning(saved.require_dedicated_cert) && <Notice tone="warn" role="alert">{t(signerWarning(saved.require_dedicated_cert))}</Notice>}
          </Section>
          <Section title={t('atelier.summary')}>
            <p className="summary">{summary}</p>
            <h3 className="section-title tsa-usage-title">{t('tsa.usage')}</h3>
            <pre className="code-preview">{`# ${t('tsa.usageCreateRequest')}
openssl ts -query -data file.pdf -sha256 -cert -out request.tsq
# ${t('tsa.usageSendRequest')}
curl -X POST -H "Content-Type: application/timestamp-query" --data-binary @request.tsq ${baseUrl}/tsa -o response.tsr
# ${t('tsa.usageVerify')}
openssl ts -reply -in response.tsr -text`}</pre>
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  const onChange = (key, value) => setDraft((d) => ({ ...d, [key]: value }))
  const off = !canEdit
  const sections = [
    {
      id: 'service', label: t('tsa.sections.service'), icon: 'stamp', desc: t('tsa.enableTsaDesc'),
      groups: [{
        legend: t('tsa.serverSettings'),
        fields: [
          { key: 'enabled', label: t('tsa.enableTsa'), checkbox: true, disabled: off },
          {
            key: 'ca_refid', label: t('tsa.signingCA'), disabled: off || !draft.enabled,
            hint: unlistedPickerCas(cas, draft.ca_refid) > 0 ? t('cas.notListedForSigning', { count: unlistedPickerCas(cas, draft.ca_refid) }) : undefined,
            options: [['', t('tsa.selectCA')], ...pickerCas(cas, draft.ca_refid).map((ca) => [ca.refid || String(ca.id), ca.name || ca.subject])],
          },
          { key: 'policy_oid', label: t('tsa.policyOid'), hint: t('tsa.policyOidHelp'), placeholder: DEFAULT_POLICY_OID, disabled: off || !draft.enabled, wide: true },
        ],
      }],
      children: placeholderPolicy && <Notice tone="warn" role="alert" id="tsa-policy-warning">{t('tsa.policyPlaceholderWarning')}</Notice>,
    },
    {
      id: 'signer', label: t('tsa.sections.signer'), icon: 'key', desc: t('tsa.signingCertDesc'),
      groups: [{
        legend: t('tsa.signingCert'),
        fields: [
          {
            key: 'signer_cert_refid', label: t('tsa.signingCert'), hint: t('tsa.signingCertHelp'), disabled: off || !draft.enabled,
            options: [['', t('tsa.signingCertCa')], ...signerCandidates.map((c) => [c.refid,
              `${certificateLabel(c) || c.subject}${c.key_type ? ` (${c.key_type})` : ''}${c.eku_critical_exclusive ? `: ${t('tsa.signerStrictBadge')}` : ''}`])],
          },
          {
            key: 'require_dedicated_cert', label: t('tsa.requireDedicatedCert'), checkbox: true,
            hint: dedicatedSignerReady || strictMode ? t('tsa.requireDedicatedCertDesc') : t('tsa.requireDedicatedCertBlocked'),
            // Turning the strict mode on is offered once a usable dedicated signer is saved
            disabled: off || !draft.enabled || (!dedicatedSignerReady && !strictMode),
          },
        ],
      }],
      children: (
        <div className="tsa-signer">
          {signerWarning(strictMode) && <Notice tone="warn" role="alert">{t(signerWarning(strictMode))}</Notice>}
          {selectionUnsaved && <Notice>{t('tsa.signerUnsaved')}</Notice>}
          {signerStatus && (
            <Notice tone={signerStatus.usable ? undefined : 'warn'} icon={signerStatus.usable ? 'check' : 'warning'} id="tsa-signer-status">
              {signerStatus.subject && <><span className="mono">{signerStatus.subject}</span><br /></>}
              {signerStatus.not_after && <><span>{t('tsa.signerExpires')} : {dateTimeOf(signerStatus.not_after, locale)}</span><br /></>}
              {signerStatus.usable ? (
                <>
                  <span>{signerStatus.chain_to_root ? t('tsa.signerChainComplete') : t('tsa.signerChainPartial', { count: signerStatus.chain_len || 0 })}</span><br />
                  <span>{signerStatus.eku_critical_exclusive ? t('tsa.signerEkuStrict') : t('tsa.signerEkuLoose')}</span>
                </>
              ) : <span>{signerStatus.error || t('tsa.signerUnusable')}</span>}
            </Notice>
          )}
          <p className="muted small">{t('tsa.signerGenerateHint')}</p>
          <div className="copy-url">
            <Btn icon="key" id="tsa-generate" write disabled={!draft.enabled || !hasPermission('write:settings') || !hasPermission('write:certificates') || undefined}
              onClick={openGenerate}>{t('tsa.signerGenerate')}</Btn>
          </div>
        </div>
      ),
    },
  ]

  const listView = (
    <ListView label="TSA" caption={t('tsa.caption')} icon="stamp" rows={service} loading={loading}
      filters={{ views: [{ id: '', label: t('common.all'), count: service.length }, ...(row ? [{ id: row.state, label: t(row.state === 'active' ? 'common.active' : 'common.disabled'), count: 1 }] : [])], active: '', onChange: () => {}, label: t('tsa.filterByState') }}
      title={(r) => r.name} status={pill} openedId={opened ? row?.id : null} onOpen={() => setOpened(true)}
      columns={[
        { id: 'ca', label: t('tsa.columns.ca'), cell: (r) => r.ca, grow: true },
        { id: 'digest', label: t('tsa.columns.digest'), cell: () => DIGESTS },
        { id: 'policy', label: t('tsa.columns.policy'), cell: (r) => r.policy },
        { status: true },
      ]}
      error={loadError && (
        <LoadError id="tsa" journal={auditPath} title={t('messages.errors.loadFailed.tsa')} onRetry={() => { setLoading(true); loadData() }}
          cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/tsa/config', message: loadError.message }} />} />
      )}
      empty={<EmptyBlock id="tsa" icon="stamp" title={t('tsa.serviceName')} />}
      footer={{ range: t('tsa.range', { shown: service.length, count: service.length }) }} />
  )

  return (
    <Zone dock={view === 'list' ? dock : null} after={generateOpen && genForm && (
      <FormModal open={generateOpen} onClose={() => setGenerateOpen(false)} title={t('tsa.signerGenerateTitle')}
        onSubmit={handleGenerateSigner} submitLabel={t('tsa.signerGenerate')} loading={generating}>
        <p className="text-xs text-text-secondary">{t('tsa.signerGenerateModalDesc')}</p>
        <div>
          <Select label={t('tsa.signingCA')}
            options={listedForIssuance(pickerCas(cas, genForm.ca_refid), showHiddenCas, genForm.ca_refid).map((ca) => ({ value: ca.refid || ca.id.toString(), label: ca.name || ca.subject }))}
            value={genForm.ca_refid} onChange={(val) => setGenForm({ ...genForm, ca_refid: val })}
            helperText={unlistedPickerCas(cas, genForm.ca_refid) > 0 ? t('cas.notListedForSigning', { count: unlistedPickerCas(cas, genForm.ca_refid) }) : undefined} />
          <HiddenCasToggle count={hiddenFromIssuance(pickerCas(cas, genForm.ca_refid), genForm.ca_refid)} shown={showHiddenCas} onToggle={() => setShowHiddenCas((v) => !v)} />
        </div>
        <Input label={t('tsa.signerGenerateCn')} value={genForm.cn} onChange={(e) => setGenForm({ ...genForm, cn: e.target.value })} />
        <Input label={t('tsa.signerGenerateValidity')} type="number" value={genForm.validity_days} onChange={(e) => setGenForm({ ...genForm, validity_days: e.target.value })} />
        <Select label={t('tsa.signerGenerateKeyType')}
          options={groupedOptions(listAlgorithms({ labels: TSA_LABELS, generate: true, ...platform }), t, (k) => k.display)}
          value={genForm.key_type} onChange={(val) => setGenForm({ ...genForm, key_type: val })} />
        <BrainpoolNotice label={genForm.key_type} />
        {findAlgorithm(genForm.key_type)?.family === 'ML-DSA' && <p className="text-xs text-text-secondary" role="note">{t('tsa.signerMldsaVerifyNote')}</p>}
        <p className="text-xs text-text-tertiary">{t('tsa.signerGenerateRenewalNote')}</p>
      </FormModal>
    )}>
      <PageHead title="TSA" intent={t('shell.moduleDesc.tsa')}
        total={view === 'config' ? t('protocols.sections', { count: sections.length }) : t('tsa.unit', { count: service.length })}
        actions={<ViewSwitch id="tsa-view" label={t('protocols.view')} value={view} onChange={setView}
          options={[{ value: 'list', label: t('tsa.views.list') }, { value: 'config', label: t('tsa.views.config') }]} />} />
      {view === 'list' ? listView : loading ? <SkeletonPanel label={t('common.loading')} /> : loadError ? listView : (
        <SettingsView sections={sections} values={draft} changed={changed} onChange={onChange} onSave={handleSaveConfig}
          onReset={() => setDraft(saved)} saving={saving} failed={failed} announce={announce} stateRef={stateRef}
          tocLabel={t('protocols.sectionsOf', { name: 'TSA' })} />
      )}
    </Zone>
  )
}
