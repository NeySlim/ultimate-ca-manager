/**
 * CRL / OCSP: the mockup's crl module, a simplePage() list (CRL, Publiée, Prochaine mise à jour,
 * OCSP, État) with its one-object dock, on the authorities and their CRLs. What the product has
 * more (search, the OCSP responder's figures, regeneration and download, the publication schedule,
 * the delta CRL, the CRL deployment, OCSP and its delegated responder, the distribution points and
 * the CPS) takes the mockup's toolbar, the filters' aside, dock actions and further dock tabs.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Zone, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, ListView, Dock, DockBody,
  Section, Facts, RecordList, RecordRow, LoadError, LoadCause, NoMatch, useClientList, useSortParam,
} from '../components/atelier'
import { SetupEmptyBlock } from '../components/shell/SetupEmptyBlock'
import { CRLDeploySection } from '../components/CRLDeploySection'
import { casService, crlService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { useLinkedId } from '../hooks/useLinkedId'
import { useDockParam, asId } from '../components/atelier/useDockParam'
import { downloadBlob } from '../lib/utils'
import { findAlgorithm } from '../lib/keyAlgorithms'
import { dateTimeOf } from './admin/adminDates'
import { CheckLine, Field, Notice, UrlList } from './protocols/atelierParts'
import { copyRow, fact } from '../components/atelier/facts'
import { crlState } from './protocols/protocolStates'

const TONES = { current: 'good', soon: 'warn', expired: 'bad', none: 'muted' }
const STATE_ORDER = ['current', 'soon', 'expired', 'none']

const VALIDITY = [1, 2, 3, 7, 14, 30, 90, 180, 365, 1095, 1825]
const PUBLISH = [6, 12, 24, 48, 72]
const DELTA = [1, 2, 4, 8, 12, 24]
const URL_FIELDS = { cdp: 'cdp_urls', ocsp: 'ocsp_urls', aia: 'aia_ca_issuers_urls' }

const CRL_SECTIONS = ['overview', 'publication', 'ocsp', 'distribution']
const NEXT_FIRST = { key: 'next', asc: true }
const CRL_SORT_KEYS = ['name', 'number', 'published', 'next', 'ocsp', 'state']

export default function CRLOCSPPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { showSuccess, showError, showInfo, showConfirm } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  // The read error links the journal for who may read it
  const auditPath = hasPermission('read:audit') ? '/audit' : undefined

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [cas, setCas] = useState([])
  const [crls, setCrls] = useState([])
  const [ocspStatus, setOcspStatus] = useState({ enabled: false, running: false })
  const [ocspStats, setOcspStats] = useState({ total_requests: 0, cache_hits: 0 })
  const [selectedCRL, setSelectedCRL] = useState(null)
  // The open authority and its section live in the URL (`item`, `section`); the work queue's ?ca= opens it too
  const crlDock = useDockParam({ sections: CRL_SECTIONS, aliases: ['ca'] })
  const openId = crlDock.item == null ? null : asId(crlDock.item)
  const { section, setSection } = crlDock
  const [query, setQuery] = useState('')
  const [state, setState] = useState('')
  const [regenerating, setRegenerating] = useState(false)
  const [deltaRegenerating, setDeltaRegenerating] = useState(false)
  const [adding, setAdding] = useState({ type: null, value: '' })
  const [savingUrls, setSavingUrls] = useState(false)
  const [cpsDraft, setCpsDraft] = useState({ uri: '', oid: '' })
  const [ocspResponder, setOcspResponder] = useState(null)
  const [eligible, setEligible] = useState(null)
  const [loadingResponder, setLoadingResponder] = useState(false)

  const loadData = async () => {
    setLoadError(null)
    try {
      const [casRes, crlsRes, ocspStatusRes, ocspStatsRes] = await Promise.all([
        casService.getAll(), crlService.getAll(), crlService.getOcspStatus(), crlService.getOcspStats(),
      ])
      setCas(casRes.data || [])
      setCrls(crlsRes.data || [])
      setOcspStatus(ocspStatusRes.data || { enabled: false, running: false })
      setOcspStats(ocspStatsRes.data || { total_requests: 0, cache_hits: 0 })
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.crl'))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { loadData() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Reload when the change was made elsewhere, through a ref so the listener never holds a stale loader
  const loadDataRef = useRef(loadData)
  loadDataRef.current = loadData
  useEffect(() => {
    const handler = (e) => { if (e.detail?.type === 'ca') loadDataRef.current() }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [])

  const rows = useMemo(() => cas.map((ca) => {
    const crl = crls.find((c) => c.ca_id === ca.id || c.caref === ca.refid)
    return {
      ...ca,
      crl_number: crl?.crl_number,
      revoked_count: crl?.revoked_count || 0,
      crl_updated: crl?.this_update || crl?.updated_at,
      crl_next_update: crl?.next_update,
      crl_next_publish: crl?.next_publish,
      has_crl: !!crl,
      delta_crl: crl?.delta_crl || null,
    }
  }), [cas, crls])
  const open = rows.find((r) => r.id === openId) || null

  const loadCRLForCA = async (caId) => {
    try {
      const response = await crlService.getForCA(caId)
      setSelectedCRL(response.data || null)
    } catch {
      setSelectedCRL(null)
    }
  }

  const readCa = (ca) => {
    setCpsDraft({ uri: ca.cps_uri || '', oid: ca.cps_oid || '2.5.29.32.0' })
    loadCRLForCA(ca.id)
    crlService.getOcspResponder(ca.id).then((res) => setOcspResponder(res.data?.responder || null)).catch(() => setOcspResponder(null))
  }
  const openCa = (ca, tab = 'overview') => {
    if (ca.id !== openId || tab !== 'overview') crlDock.open(ca.id, tab === 'overview' ? {} : { section: tab })
    if (ca.id === openId && tab === 'overview') readCa(ca)
  }
  // The authority's CRL, responder and CPS draft are read once it opens, by a click or by the URL
  const readFor = useRef(null)
  useEffect(() => {
    if (!open) { readFor.current = null; return }
    if (readFor.current === open.id) return
    readFor.current = open.id
    setAdding({ type: null, value: '' })
    setEligible(null)
    setOcspResponder(null)
    readCa(open)
  }, [open?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  // An authority the URL names that the list no longer holds leaves it
  useEffect(() => {
    if (!loading && crlDock.item && !rows.some((r) => String(r.id) === crlDock.item)) crlDock.close()
  }, [loading, rows, crlDock.item]) // eslint-disable-line react-hooks/exhaustive-deps

  // /crl-ocsp?ca=N (a CRL to publish, from the work queue) opens that authority on its publication
  const linkedCa = useLinkedId('ca')
  const openedCa = useRef(null)
  useEffect(() => {
    if (!linkedCa || loading || openedCa.current === linkedCa) return
    openedCa.current = linkedCa
    const ca = rows.find((c) => String(c.id) === linkedCa)
    if (ca) openCa(ca, 'publication')
    else showInfo(t('overview.link.gone', { id: linkedCa }))
  }, [linkedCa, loading, rows]) // eslint-disable-line react-hooks/exhaustive-deps

  const patchCa = (id, updated) => setCas((prev) => prev.map((c) => (c.id === id ? { ...c, ...updated } : c)))

  const handleRegenerateCRL = async () => {
    if (!open) return
    setRegenerating(true)
    try {
      await crlService.regenerate(open.id)
      showSuccess(t('messages.success.crl.generated'))
      loadCRLForCA(open.id)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.crl'))
    } finally {
      setRegenerating(false)
    }
  }

  const handleDownloadCRL = () => {
    if (!selectedCRL?.crl_pem) return
    downloadBlob(new Blob([selectedCRL.crl_pem], { type: 'application/x-pem-file' }), `${open?.descr || 'crl'}.crl`)
  }

  const handleToggleAutoRegen = async (ca) => {
    try {
      const result = await crlService.toggleAutoRegen(ca.id, !ca.cdp_enabled)
      const updated = result.data || result
      showSuccess(t(updated.cdp_enabled ? 'crlOcsp.autoRegenEnabled' : 'crlOcsp.autoRegenDisabled', { name: ca.descr }))
      patchCa(ca.id, updated)
    } catch (error) {
      showError(error.message || t('crlOcsp.toggleAutoRegenFailed'))
    }
  }

  const handleToggleDeltaCRL = async (ca) => {
    try {
      const enabled = !ca.delta_crl_enabled
      await crlService.configureDelta(ca.id, { enabled })
      showSuccess(t(enabled ? 'crlOcsp.deltaCrlEnabled' : 'crlOcsp.deltaCrlDisabled'))
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.deltaCrlToggleFailed'))
    }
  }

  const handleGenerateDelta = async (ca) => {
    setDeltaRegenerating(true)
    try {
      await crlService.generateDelta(ca.id)
      showSuccess(t('crlOcsp.deltaCrlGenerated'))
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.deltaCrlGenerateFailed'))
    } finally {
      setDeltaRegenerating(false)
    }
  }

  const handleCrlScheduleChange = async (ca, field, value) => {
    try {
      await crlService.configureCrl(ca.id, { [field]: value })
      showSuccess(t('crlOcsp.crlScheduleUpdated'))
      await loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.crlScheduleFailed'))
    }
  }

  const handleDeltaIntervalChange = async (ca, interval) => {
    try {
      await crlService.configureDelta(ca.id, { interval: parseInt(interval, 10) })
      showSuccess(t('crlOcsp.deltaIntervalUpdated'))
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.deltaIntervalFailed'))
    }
  }

  const toggleCaFlag = async (ca, field, onKey, offKey, failKey) => {
    try {
      const value = !ca[field]
      const result = await casService.update(ca.id, { [field]: value })
      showSuccess(t(value ? onKey : offKey, { name: ca.descr }))
      patchCa(ca.id, result.data || result)
      loadData()
    } catch (error) {
      showError(error.message || t(failKey))
    }
  }
  const handleToggleOcsp = (ca) => toggleCaFlag(ca, 'ocsp_enabled', 'crlOcsp.ocspEnabled', 'crlOcsp.ocspDisabled', 'crlOcsp.toggleOcspFailed')
  const handleToggleAia = (ca) => toggleCaFlag(ca, 'aia_ca_issuers_enabled', 'crlOcsp.aiaIssuersEnabled', 'crlOcsp.aiaIssuersDisabled', 'crlOcsp.toggleAiaFailed')

  const handleEnableNamedUrls = async () => {
    if (!open) return
    const confirmed = await showConfirm(t('crlOcsp.namedUrlsConfirm', { name: open.descr }), {
      title: t('crlOcsp.namedUrlsTitle'), confirmText: t('crlOcsp.namedUrlsEnable'),
    })
    if (!confirmed) return
    setSavingUrls(true)
    try {
      const result = await casService.update(open.id, { namedUrls: true })
      const updated = result.data || result
      showSuccess(t('crlOcsp.namedUrlsEnabled', { slug: updated.url_slug }))
      patchCa(open.id, updated)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed.generic'))
    } finally {
      setSavingUrls(false)
    }
  }

  const saveUrls = async (type, list) => {
    setSavingUrls(true)
    try {
      await casService.update(open.id, { [URL_FIELDS[type]]: list })
      showSuccess(t('common.saved'))
      setAdding({ type: null, value: '' })
      await loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed.generic'))
    } finally {
      setSavingUrls(false)
    }
  }
  const addUrl = (type) => {
    const url = adding.value.trim()
    if (!url || !open) return
    saveUrls(type, [...(open[URL_FIELDS[type]] || []), url])
  }
  const removeUrl = (type, index) => open && saveUrls(type, (open[URL_FIELDS[type]] || []).filter((_, i) => i !== index))

  const handleCpsUpdate = async (field, value) => {
    if (!open) return
    setSavingUrls(true)
    try {
      await casService.update(open.id, { [field]: value })
      showSuccess(t('common.saved'))
      await loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed.generic'))
    } finally {
      setSavingUrls(false)
    }
  }

  const handleAssignResponder = async (certId) => {
    try {
      await crlService.setOcspResponder(open.id, certId)
      showSuccess(t('crlOcsp.delegatedResponderSet'))
      const res = await crlService.getOcspResponder(open.id)
      setOcspResponder(res.data?.responder || null)
    } catch (error) {
      showError(error.message || t('crlOcsp.delegatedResponderFailed'))
    }
  }

  const handleRemoveResponder = async () => {
    // Live OCSP answers change signer the moment this lands
    const confirmed = await showConfirm(
      t('crlOcsp.removeResponderConfirm', { name: open?.descr || open?.name || '' }),
      { title: t('crlOcsp.removeResponder'), confirmText: t('common.remove'), variant: 'danger' },
    )
    if (!confirmed) return
    try {
      await crlService.removeOcspResponder(open.id)
      showSuccess(t('crlOcsp.delegatedResponderRemoved'))
      setOcspResponder(null)
    } catch (error) {
      showError(error.message || t('crlOcsp.delegatedResponderRemoveFailed'))
    }
  }

  const handleLoadEligible = async () => {
    setLoadingResponder(true)
    try {
      const res = await crlService.getEligibleOcspResponders(open.id)
      setEligible(res.data || [])
    } catch {
      setEligible([])
    } finally {
      setLoadingResponder(false)
    }
  }

  const name = (r) => r.descr || r.name || r.common_name
  const stateOf = (r) => crlState(r)
  const pill = (r) => <Pill label={t(`crlOcsp.states.${stateOf(r)}`)} tone={TONES[stateOf(r)]} />
  const number = (r) => (r.has_crl ? t('crlOcsp.numberOf', { number: r.crl_number }) : t('crlOcsp.noCRL'))
  // Under its column's name the number reads alone; a CA without a CRL says so in its state
  // The list and the panel say the number alike (« n° 4 »), as the mockup's CRL column
  const crlNumber = (r) => (r.has_crl ? t('crlOcsp.numberOf', { number: r.crl_number }) : '—')
  const published = (r) => dateTimeOf(r.crl_updated, locale) || '—'
  const next = (r) => dateTimeOf(r.crl_next_update, locale) || '—'
  const ocsp = (r) => t(r.ocsp_enabled ? 'crlOcsp.ocspActive' : 'crlOcsp.ocspInactive')
  // In the dock the responder is a state of service: a pill, as in the CA panel
  const ocspState = (r) => (r.ocsp_enabled ? ['good', ocsp(r), 'check'] : ['muted', ocsp(r), 'block'])

  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((r) => !q || [r.descr, r.name, r.common_name].some((v) => String(v || '').toLowerCase().includes(q)))
  }, [rows, query])
  const present = STATE_ORDER.filter((s) => rows.some((r) => stateOf(r) === s))
  const active = present.includes(state) ? state : ''
  const shown = searched.filter((r) => !active || stateOf(r) === active)
  // The nearest next update first, kept in the address
  const sortParam = useSortParam(NEXT_FIRST, CRL_SORT_KEYS)
  const list = useClientList(shown, {
    resetKey: `${query}|${active}`,
    sortParam,
    sorts: {
      name, number: (r) => (r.has_crl ? r.crl_number : null), published: (r) => r.crl_updated && Date.parse(r.crl_updated),
      next: (r) => r.crl_next_update && Date.parse(r.crl_next_update), ocsp: (r) => (r.ocsp_enabled ? 0 : 1), state: (r) => STATE_ORDER.indexOf(stateOf(r)),
    },
  })
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    ...present.map((s) => ({ id: s, label: t(`crlOcsp.states.${s}`), count: searched.filter((r) => stateOf(r) === s).length })),
  ]
  const hitRate = ocspStats.total_requests > 0 ? Math.round((ocspStats.cache_hits / ocspStats.total_requests) * 100) : 0
  const responder = t(!ocspStatus.enabled ? 'crlOcsp.responderDisabled' : ocspStatus.running ? 'crlOcsp.responderRunning' : 'crlOcsp.responderStopped')
  const aside = <span className="phone-aside">{t('crlOcsp.responderAside', { state: responder, count: ocspStats.total_requests || 0, rate: hitRate })}</span>

  const write = canWrite('crl')
  const withKey = (r) => r.has_private_key !== false
  const summary = (r) => {
    const s = stateOf(r)
    if (s === 'none') return t('crlOcsp.summaryNone')
    const lead = t('crlOcsp.summaryRevoked', { count: r.revoked_count || 0, number: r.crl_number })
    return s === 'current' ? lead : `${lead} ${t(`crlOcsp.summary.${s}`)}`
  }

  const urlBlock = (type, label, enabled, placeholder) => (
    <Section title={label}>
      <UrlList urls={open[URL_FIELDS[type]] || []} label={label} busy={savingUrls}
        empty={enabled ? t('crlOcsp.urlNotConfigured') : t('common.disabled')}
        onRemove={write ? (i) => removeUrl(type, i) : undefined}
        adding={adding.type === type ? adding.value : null}
        onAdding={(v) => setAdding(v === null ? { type: null, value: '' } : { type, value: v })}
        onAdd={write && enabled ? () => addUrl(type) : undefined} placeholder={placeholder} />
    </Section>
  )

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('shell.moduleLabel.crlOcsp') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: name(open), icon: 'crl' }]} onClose={() => { crlDock.close(); setSelectedCRL(null) }}>
      <DockBody icon="crl" title={name(open)} badge={pill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: name(open) })}
        sections={[['overview', t('atelier.overview')], ['publication', t('crlOcsp.tabs.publication')], ['ocsp', 'OCSP'], ['distribution', t('crlOcsp.cdpNote')]]}
        actions={<>
          {write && withKey(open) && (
            <Btn icon="refresh" id="crl-regenerate" write disabled={regenerating || undefined} onClick={handleRegenerateCRL}>
              {regenerating ? t('crlOcsp.regenerating') : t('crlOcsp.regenerateCRL')}
            </Btn>
          )}
          {selectedCRL?.crl_pem && <Btn icon="download" id="crl-download" onClick={handleDownloadCRL}>{t('common.download')}</Btn>}
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Facts items={[
                open.has_crl ? ['CRL', number(open)] : { label: 'CRL', absent: number(open) },
                fact(t('crlOcsp.columns.published'), dateTimeOf(open.crl_updated, locale)), fact(t('crlOcsp.nextUpdate'), dateTimeOf(open.crl_next_update, locale)),
                { label: 'OCSP', state: ocspState(open) }, [t('atelier.state'), pill(open)],
                fact(t('crlOcsp.revokedCount'), open.has_crl ? String(open.revoked_count || 0) : null),
              ]} />
            </Section>
            <Section title={t('atelier.summary')}><p className="summary">{summary(open)}</p></Section>
          </div>
        )}
        {section === 'publication' && (
          <div className="module-detail">
            <Section title={t('crlOcsp.tabs.publication')}>
              <div>
                <CheckLine id="crl-auto-regen" checked={open.cdp_enabled} disabled={!withKey(open) || !write} onChange={() => handleToggleAutoRegen(open)}>
                  {t('crlOcsp.autoRegen')}
                </CheckLine>
                <CheckLine id="crl-delta" checked={open.delta_crl_enabled} disabled={!withKey(open) || !open.cdp_enabled || !write} onChange={() => handleToggleDeltaCRL(open)}>
                  {t('crlOcsp.deltaCrl')}
                </CheckLine>
              </div>
              {open.has_private_key && (
                <>
                  {open.crl_next_publish && <Facts items={[[t('crlOcsp.nextPublish'), dateTimeOf(open.crl_next_publish, locale)]]} />}
                  <div className="form-fields dock-form">
                    <Field label={t('crlOcsp.crlValidity')} id="crl-validity"
                      hint={(open.crl_validity_days || 0) > 365 ? t('crlOcsp.crlValidityOfflineWarning') : undefined}>
                      {(p) => (
                        <select {...p} value={open.crl_validity_days || 7} disabled={!write || undefined}
                          onChange={(e) => handleCrlScheduleChange(open, 'validity_days', parseInt(e.target.value, 10))}>
                          {VALIDITY.map((d) => <option key={d} value={d}>{t('crlOcsp.days', { count: d })}</option>)}
                        </select>
                      )}
                    </Field>
                    <Field label={t('crlOcsp.crlPublishInterval')} id="crl-publish-interval">
                      {(p) => (
                        <select {...p} value={open.crl_publish_interval_hours || ''} disabled={!write || undefined}
                          onChange={(e) => handleCrlScheduleChange(open, 'publish_interval_hours', e.target.value ? parseInt(e.target.value, 10) : null)}>
                          <option value="">{t('crlOcsp.crlPublishAuto')}</option>
                          {PUBLISH.map((h) => <option key={h} value={h}>{t('crlOcsp.hours', { count: h })}</option>)}
                        </select>
                      )}
                    </Field>
                    {/* An ML-DSA authority's key takes no digest, whatever crl_digest says */}
                    {open.crl_digest && findAlgorithm(open.key_type)?.digest !== null && (
                      <Field label={t('crlOcsp.crlDigest')} id="crl-digest">
                        {(p) => (
                          <select {...p} value={open.crl_digest} disabled={!write || undefined}
                            onChange={(e) => handleCrlScheduleChange(open, 'digest', e.target.value)}>
                            <option value="sha256">SHA-256</option>
                            <option value="sha384">SHA-384</option>
                            <option value="sha512">SHA-512</option>
                          </select>
                        )}
                      </Field>
                    )}
                  </div>
                  {open.crl_digest_ignored && (
                    <Notice id="crl-digest-ignored">
                      {t('crlOcsp.crlDigestIgnored', { digest: open.crl_digest_ignored.toUpperCase() })}{' '}
                      <Btn write disabled={!write || undefined} onClick={() => handleCrlScheduleChange(open, 'digest', null)}>{t('crlOcsp.crlDigestClear')}</Btn>
                    </Notice>
                  )}
                  <p className="muted small">{t('crlOcsp.crlScheduleNote')}</p>
                </>
              )}
            </Section>
            {open.cdp_enabled && open.delta_crl_enabled && (
              <Section title={t('crlOcsp.deltaCrlTitle')}>
                {open.delta_crl && (
                  <Facts items={[
                    [t('crlOcsp.deltaCrlNumber'), `#${open.delta_crl.crl_number}`], [t('crlOcsp.baseCrlNumber'), `#${open.delta_crl.base_crl_number}`],
                    [t('crlOcsp.deltaEntries'), String(open.delta_crl.revoked_count ?? 0)],
                    fact(t('crlOcsp.deltaNextUpdate'), dateTimeOf(open.delta_crl.next_update, locale)),
                  ]} />
                )}
                <div className="form-fields dock-form">
                  <Field label={t('crlOcsp.deltaInterval')} id="delta-interval">
                    {(p) => (
                      <select {...p} value={open.delta_crl_interval || 4} disabled={!write || undefined} onChange={(e) => handleDeltaIntervalChange(open, e.target.value)}>
                        {DELTA.map((h) => <option key={h} value={h}>{t('crlOcsp.hours', { count: h })}</option>)}
                      </select>
                    )}
                  </Field>
                </div>
                {write && (
                  <div className="copy-url">
                    <Btn icon="refresh" id="crl-delta-generate" write disabled={deltaRegenerating || undefined} onClick={() => handleGenerateDelta(open)}>
                      {deltaRegenerating ? t('common.generating') : t('crlOcsp.generateDelta')}
                    </Btn>
                  </div>
                )}
              </Section>
            )}
            <CRLDeploySection ca={open} hasCRL={Boolean(selectedCRL)} />
          </div>
        )}
        {section === 'ocsp' && (
          <div className="module-detail">
            <Section title={t('crlOcsp.ocspConfig')}>
              <div>
                <CheckLine id="crl-ocsp" checked={open.ocsp_enabled} disabled={!withKey(open) || !write} onChange={() => handleToggleOcsp(open)}>
                  {t('crlOcsp.ocspResponderOf')}
                </CheckLine>
              </div>
              <Facts items={[
                { label: t('atelier.state'), state: ocspState(open) },
                open.ocsp_enabled && (open.ocsp_urls || []).length > 0 && copyRow('URL', open.ocsp_urls[0], 'url', { copyLabel: 'OCSP' }),
                [t('crlOcsp.totalRequests'), String(ocspStats.total_requests || 0)],
                [t('crlOcsp.cacheHits'), String(ocspStats.cache_hits || 0)],
              ]} />
              <p className="muted small">{t('crlOcsp.statsAllAuthorities')}</p>
            </Section>
            <Section title={t('crlOcsp.delegatedResponder')}>
              <p className="muted small">{t('crlOcsp.delegatedResponderDescription')}</p>
              {ocspResponder ? (
                <RecordList>
                  <RecordRow title={ocspResponder.common_name}
                    meta={`${t('crlOcsp.serial', { serial: ocspResponder.serial_number })} · ${t('common.expires')} ${dateTimeOf(ocspResponder.valid_to, locale)}`}
                    action={canWrite('cas') && <Btn tone="danger" icon="block" id="crl-responder-remove" onClick={handleRemoveResponder}>{t('crlOcsp.removeResponder')}</Btn>} />
                </RecordList>
              ) : (
                <>
                  <p className="muted small">{t('crlOcsp.delegatedResponderNone')}</p>
                  {canWrite('cas') && (eligible === null ? (
                    <div className="copy-url"><Btn icon="key" id="crl-responder-load" write disabled={loadingResponder || undefined} onClick={handleLoadEligible}>{t('crlOcsp.selectResponder')}</Btn></div>
                  ) : eligible.length ? (
                    <div className="form-fields">
                      <Field label={t('crlOcsp.selectResponder')} id="crl-responder" full>
                        {(p) => (
                          <select {...p} defaultValue="" onChange={(e) => e.target.value && handleAssignResponder(parseInt(e.target.value, 10))}>
                            <option value="" disabled>{t('crlOcsp.selectResponder')}</option>
                            {eligible.map((c) => <option key={c.id} value={c.id}>{c.common_name} ({t('crlOcsp.serial', { serial: c.serial_number })})</option>)}
                          </select>
                        )}
                      </Field>
                    </div>
                  ) : <p className="muted small">{t('crlOcsp.noEligibleResponders')}</p>)}
                </>
              )}
            </Section>
          </div>
        )}
        {section === 'distribution' && (
          <div className="module-detail">
            <Section title={t('crlOcsp.namedUrlsTitle')}>
              {open.url_slug ? <Facts items={[copyRow(t('crlOcsp.slug'), open.url_slug)]} /> : <p className="muted small">{t('crlOcsp.namedUrlsOff')}</p>}
              {!open.url_slug && write && (
                <div className="copy-url"><Btn id="crl-named-urls" write disabled={savingUrls || undefined} onClick={handleEnableNamedUrls}>{t('crlOcsp.namedUrlsEnable')}</Btn></div>
              )}
            </Section>
            {urlBlock('cdp', t('crlOcsp.cdp'), open.cdp_enabled, 'http://cdp.example.com/crl.pem')}
            {urlBlock('ocsp', 'OCSP', open.ocsp_enabled, 'http://ocsp.example.com/')}
            <Section title={t('crlOcsp.aiaIssuersConfig')}>
              <div>
                <CheckLine id="crl-aia" checked={open.aia_ca_issuers_enabled} disabled={!withKey(open) || !write} onChange={() => handleToggleAia(open)}>
                  {t('crlOcsp.aiaIssuers')}
                </CheckLine>
              </div>
              <UrlList urls={open.aia_ca_issuers_urls || []} label={t('crlOcsp.aiaIssuersUrl')} busy={savingUrls}
                empty={open.aia_ca_issuers_enabled ? t('crlOcsp.urlNotConfigured') : undefined}
                onRemove={write ? (i) => removeUrl('aia', i) : undefined}
                adding={adding.type === 'aia' ? adding.value : null}
                onAdding={(v) => setAdding(v === null ? { type: null, value: '' } : { type: 'aia', value: v })}
                onAdd={write && open.aia_ca_issuers_enabled ? () => addUrl('aia') : undefined} placeholder="http://ca.example.com/ca.cer" />
              <p className="muted small">{t('crlOcsp.includeURLsNote')}</p>
            </Section>
            <Section title={t('crlOcsp.cpsTitle')}>
              <CheckLine id="crl-cps" checked={open.cps_enabled} disabled={savingUrls || !write} onChange={(v) => handleCpsUpdate('cps_enabled', v)}>
                {t('crlOcsp.cpsEnabled')}
              </CheckLine>
              <div className="form-fields">
                {open.cps_enabled && (
                  <>
                    <Field label={t('crlOcsp.cpsUri')} id="crl-cps-uri" full>
                      {(p) => (
                        <input {...p} type="url" className="mono" placeholder="http://ca.example.com/cps.pdf" value={cpsDraft.uri} disabled={!write || undefined}
                          onChange={(e) => setCpsDraft({ ...cpsDraft, uri: e.target.value })}
                          onBlur={(e) => { if (e.target.value !== (open.cps_uri || '')) handleCpsUpdate('cps_uri', e.target.value) }} />
                      )}
                    </Field>
                    <Field label={t('crlOcsp.cpsOid')} id="crl-cps-oid" full hint={t('crlOcsp.cpsOidNote')}>
                      {(p) => (
                        <input {...p} className="mono" placeholder="2.5.29.32.0" value={cpsDraft.oid} disabled={!write || undefined}
                          onChange={(e) => setCpsDraft({ ...cpsDraft, oid: e.target.value })}
                          onBlur={(e) => { if (e.target.value !== (open.cps_oid || '2.5.29.32.0')) handleCpsUpdate('cps_oid', e.target.value || '2.5.29.32.0') }} />
                      )}
                    </Field>
                  </>
                )}
              </div>
            </Section>
          </div>
        )}
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock}>
      <PageHead title={t('shell.moduleLabel.crlOcsp')} total={t('crlOcsp.unit', { count: rows.length })} intent={t('shell.moduleDesc.crlOcsp')} />
      <ListView label={t('shell.moduleLabel.crlOcsp')} caption={t('crlOcsp.caption')} icon="crl" list={list} loading={loading} nameSort="name"
        filters={{ views, active, onChange: setState, label: t('crlOcsp.filterByState'), aside }}
        toolbar={(
          <Toolbar>
            <SearchField id="crl-search" name="q" label={t('crlOcsp.search')} placeholder={t('crlOcsp.search')} value={query} onChange={setQuery} />
            <IconBtn icon="refresh" label={t('common.refresh')} onClick={() => loadData()} />
          </Toolbar>
        )}
        title={name} status={pill} openedId={openId} onOpen={openCa}
        columns={[
          { id: 'number', label: 'CRL', cell: crlNumber, kind: 'fit', priority: 3, labelled: true, sort: 'number' },
          { id: 'published', label: t('crlOcsp.columns.published'), cell: published, kind: 'fit', priority: 3, labelled: true, sort: 'published' },
          { id: 'next', label: t('crlOcsp.columns.nextUpdate'), labelFull: t('crlOcsp.nextUpdate'), cell: next, kind: 'fit', priority: 2, labelled: true, sort: 'next' },
          { id: 'ocsp', label: 'OCSP', cell: ocsp, kind: 'fit', priority: 3, sort: 'ocsp' },
          { status: true, sort: 'state' },
        ]}
        error={loadError && (
          <LoadError id="crl" journal={auditPath} title={t('messages.errors.loadFailed.crl')} onRetry={() => { setLoading(true); loadData() }}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/crl', message: loadError.message }} />} />
        )}
        empty={rows.length && (query.trim() || active) ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => { setQuery(''); setState('') }} />
        ) : (
          <SetupEmptyBlock id="crl" icon="crl" title={t('crlOcsp.emptyTitle')} text={t('crlOcsp.emptyText')}
            action={canWrite('cas') ? { label: t('crlOcsp.createCa'), icon: 'plus', to: '/cas' } : undefined} />
        )}
        footer={{ range: t('crlOcsp.range', list.counts(rows.length)) }} />
    </Zone>
  )
}
