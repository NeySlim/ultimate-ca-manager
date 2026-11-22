/**
 * SCEP: the mockup's scep module, a listView() of the profiles (Autorité, Modèle, Intune, État)
 * with its one-object dock (Profil), the Activer / Désactiver and Régénérer le mot de passe…
 * actions and their dialogs (scepToggle, scepRotateDialog, then the new value shown once). What
 * the product has more (the enrollment requests and their approval, the challenge of each CA, the
 * Intune app registrations, the server configuration) takes the same list and dock, and the
 * mockup's settingsView(), behind the page switch. Per-profile enrolments and journal (M04) and
 * an OAEP flag per profile (doubtful, never copied) are not drawn.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  Zone, Btn, Pill, PageHead, Toolbar, SearchField, IconBtn, ListView, Dock, DockBody, Section, Props, SettingsView, SkeletonPanel,
  LoadError, LoadCause, EmptyBlock, NoMatch, AtelierDialog, Icon, useClientList, useSortParam,
} from '../components/atelier'
import { SetupEmptyBlock } from '../components/shell/SetupEmptyBlock'
import { scepService, casService, templatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useClipboard } from '../hooks'
import { useLinkedId } from '../hooks/useLinkedId'
import { useDockParam, useDockSelection, asId } from '../components/atelier/useDockParam'
import { stateLabel } from '../lib/stateLabel'
import { scepPickerCas, unlistedScepPickerCas } from '../lib/caSelection'
import { extractData } from '../lib/utils'
import { dateTimeOf } from './admin/adminDates'
import { Copyable, Notice, ViewSwitch, YesNo } from './protocols/atelierParts'
import { parseDN } from './protocols/protocolStates'
import ScepProfileForm from './scep/ScepProfileForm'
import IntuneAppForm from './scep/IntuneAppForm'

const VIEWS = ['profiles', 'requests', 'challenges', 'intune', 'config']
// The former tab names of /scep-config?tab=… keep their place
const FORMER = { challenge: 'challenges', info: 'config' }
const REQUEST_TONES = { pending: 'warn', approved: 'good', issued: 'good', rejected: 'bad' }
const CONFIG_FIELDS = ['enabled', 'ca_id', 'auto_approve', 'challenge_validity', 'getcacert_chain', 'plain_http', 'enforce_signing_time', 'time_skew_minutes']


const configDraft = (c) => ({
  enabled: !!c.enabled, ca_id: c.ca_id != null ? String(c.ca_id) : '__none__', auto_approve: !!c.auto_approve,
  challenge_validity: String(c.challenge_validity || 24), getcacert_chain: !!c.getcacert_chain, plain_http: !!c.plain_http,
  enforce_signing_time: !!c.enforce_signing_time, time_skew_minutes: String(c.time_skew_minutes || 10),
})

const NONE = []
// The default sort of each view (T4): a name ascending, the newest request first; each view keeps its own in the address (T9)
const BY_NAME = { key: 'name', asc: true }
const NEWEST = { key: 'created_at', asc: false }
const PROFILE_SORT_KEYS = ['name', 'ca', 'template', 'intune', 'state']
// The requests are paged by the server, so sorted by it (T2): its keys
const REQUEST_SORT_KEYS = ['subject', 'transaction_id', 'created_at', 'status']
const CHALLENGE_SORT_KEYS = ['name', 'subject', 'state']
const APP_SORT_KEYS = ['name', 'tenant', 'client', 'test', 'state']

export default function SCEPPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { showSuccess, showError, showInfo, showConfirm } = useNotification()
  const { hasPermission } = usePermission()
  const auditPath = hasPermission('read:audit') ? '/audit' : undefined
  const canEdit = hasPermission('write:scep')
  const { copy } = useClipboard()
  const [searchParams, setSearchParams] = useSearchParams()
  const asked = FORMER[searchParams.get('tab')] || searchParams.get('tab')
  const view = VIEWS.includes(asked) ? asked : 'profiles'
  const setView = (v) => setSearchParams(v === 'profiles' ? {} : { tab: v }, { replace: true })

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [config, setConfig] = useState({})
  const [draft, setDraft] = useState(configDraft({}))
  const [profiles, setProfiles] = useState([])
  const [templates, setTemplates] = useState([])
  const [cas, setCas] = useState([])
  const [stats, setStats] = useState({ pending: 0, approved: 0, rejected: 0, total: 0 })
  const [profileState, setProfileState] = useState('')
  const [profileForm, setProfileForm] = useState(null)
  const [rotate, setRotate] = useState(null)
  const [secret, setSecret] = useState(null)
  const [busy, setBusy] = useState(false)
  // Requests, paged, searched and filtered by the server
  const [requests, setRequests] = useState([])
  const [requestsLoading, setRequestsLoading] = useState(true)
  const [totalRequests, setTotalRequests] = useState(0)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [rejecting, setRejecting] = useState(null)
  const profileSort = useSortParam(BY_NAME, view === 'profiles' ? PROFILE_SORT_KEYS : NONE)
  const requestSort = useSortParam(NEWEST, view === 'requests' ? REQUEST_SORT_KEYS : NONE)
  const challengeSort = useSortParam(BY_NAME, view === 'challenges' ? CHALLENGE_SORT_KEYS : NONE)
  const appSort = useSortParam(BY_NAME, view === 'intune' ? APP_SORT_KEYS : NONE)
  // A sort read from the address (a click, Back, a shared link) goes back to page one
  const requestMark = `${requestSort.sort.key}:${requestSort.sort.asc}`
  const [requestMarked, setRequestMarked] = useState(requestMark)
  if (requestMarked !== requestMark) { setRequestMarked(requestMark); setPage(1) }
  const [rejectReason, setRejectReason] = useState('')
  // The challenge of each CA (the CA-wide endpoint), read when its view opens
  const [challenges, setChallenges] = useState(null)
  // Intune app registrations
  const [apps, setApps] = useState(null)
  // The object open in the view's dock lives in the URL (`item`): a profile, a request, a CA's challenge or an app
  const scepDock = useDockParam()
  const itemOf = (v) => (view === v && scepDock.item != null ? asId(scepDock.item) : null)
  const openIn = (id) => (id == null ? scepDock.close() : scepDock.open(id))
  const openProfile = itemOf('profiles')
  const setOpenProfile = openIn
  const openCa = itemOf('challenges')
  const setOpenCa = openIn
  const openApp = itemOf('intune')
  const setOpenApp = openIn
  const [appForm, setAppForm] = useState(null)
  // Configuration form
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState({})
  const [failed, setFailed] = useState([])
  const [announce, setAnnounce] = useState('')
  const stateRef = useRef(null)

  const loadData = async () => {
    setLoadError(null)
    try {
      const [configRes, casRes, statsRes, profilesRes, templatesRes] = await Promise.all([
        scepService.getConfig(), casService.getAll(), scepService.getStats(),
        scepService.getProfiles().catch(() => ({ data: [] })), templatesService.getAll().catch(() => ({ data: [] })),
      ])
      const c = configRes.data || {}
      setConfig(c)
      setDraft(configDraft(c))
      setCas(casRes.data || [])
      setStats(statsRes.data || { pending: 0, approved: 0, rejected: 0, total: 0 })
      setProfiles(profilesRes.data || [])
      setTemplates((templatesRes.data || []).filter((tpl) => tpl.template_type !== 'ca'))
      loadRequestsRef.current()
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.scep'))
    } finally {
      setLoading(false)
    }
  }

  // An answer older than the last request sent is dropped
  const requestSeq = useRef(0)
  const loadRequests = useCallback(async () => {
    const seq = ++requestSeq.current
    try {
      const params = { page, per_page: perPage, sort_by: requestSort.sort.key, sort_order: requestSort.sort.asc ? 'asc' : 'desc' }
      if (searchQuery) params.search = searchQuery
      if (statusFilter) params.status = [statusFilter]
      const res = await scepService.getRequests(params)
      if (seq !== requestSeq.current) return
      setRequests(res.data || [])
      setTotalRequests(res.meta?.total ?? (res.data || []).length)
    } catch (error) {
      if (seq === requestSeq.current) notifyRef.current(error.message)
    } finally {
      if (seq === requestSeq.current) setRequestsLoading(false)
    }
  }, [page, perPage, searchQuery, statusFilter, requestSort.sort])
  const notifyRef = useRef(() => {})
  notifyRef.current = (message) => showError(message || t('messages.errors.loadFailed.scep'))
  const loadRequestsRef = useRef(loadRequests)
  loadRequestsRef.current = loadRequests
  useEffect(() => { loadRequests() }, [loadRequests])
  useEffect(() => { loadData() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // A request off the page (a reload) is read by id
  const loadRequest = useCallback((id) => scepService.getRequest(asId(id)).then((res) => res?.data), [])
  const requestSel = useDockSelection(view === 'requests' ? requests : NONE, { ready: view === 'requests' && !requestsLoading, load: loadRequest })
  const openRequest = view === 'requests' ? requestSel.selected : null
  const setOpenRequest = requestSel.select

  // /scep-config?tab=requests&request=N opens that request, even past the latest page
  const linkedId = useLinkedId('request')
  useEffect(() => {
    if (!linkedId) return
    let cancelled = false
    scepService.getRequest(linkedId)
      .then((res) => {
        if (cancelled || !res?.data) return
        requestSel.hold(res.data)
        setSearchParams({ tab: 'requests', item: String(res.data.id) }, { replace: true })
        if (res.data.status !== 'pending') showInfo(t('overview.link.handled', { id: res.data.id, status: stateLabel(t, res.data.status) }))
      })
      .catch((error) => {
        if (cancelled) return
        if (error?.status === 404) showInfo(t('overview.link.gone', { id: linkedId }))
        else showError(error.message || t('messages.errors.loadFailed.scep'))
      })
    return () => { cancelled = true }
  }, [linkedId]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadChallenges = async () => {
    const list = await Promise.all((cas || []).map(async (ca) => {
      try {
        const res = await scepService.getChallenge(ca.id)
        return { ...ca, scep_challenge: res.data?.challenge || null }
      } catch {
        return { ...ca, scep_challenge: null }
      }
    }))
    setChallenges(list)
  }
  useEffect(() => { if (view === 'challenges' && !loading && challenges === null) loadChallenges() }, [view, loading]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadApps = async () => {
    try {
      setApps(extractData(await scepService.getIntuneApps()) || [])
    } catch (error) {
      setApps([])
      showError(error.message || t('messages.errors.loadFailed.scep'))
    }
  }
  useEffect(() => { if (view === 'intune' && apps === null) loadApps() }, [view]) // eslint-disable-line react-hooks/exhaustive-deps

  const baseUrl = useMemo(() => window.location.origin, [])
  const profileUrl = (p) => `${baseUrl}/scep/${p.url_slug}/pkiclient.exe`
  const caName = (refid) => {
    const ca = cas.find((c) => c.refid === refid)
    return ca?.descr || ca?.name || ca?.common_name || refid || '—'
  }
  const profileOf = (id) => profiles.find((p) => p.id === id)

  // ── Profiles (the mockup's list) ──
  const profilePill = (p) => <Pill label={t(p.enabled ? 'common.active' : 'common.disabled')} tone={p.enabled ? 'good' : 'muted'} />
  const profileFilters = [
    ['', t('common.all'), () => true],
    ['active', t('scep.filters.active'), (p) => p.enabled],
    ['disabled', t('scep.filters.disabled'), (p) => !p.enabled],
    ['intune', 'Intune', (p) => p.intune_enabled],
  ]
  const activeFilter = profileFilters.find((f) => f[0] === profileState) || profileFilters[0]
  const shownProfiles = profiles.filter(activeFilter[2])
  const profileList = useClientList(shownProfiles, {
    resetKey: profileState, sortParam: profileSort,
    sorts: {
      name: (p) => p.name, ca: (p) => p.ca_name || caName(p.ca_refid), template: (p) => p.template_name || null,
      intune: (p) => (p.intune_enabled ? 0 : 1), state: (p) => (p.enabled ? 0 : 1),
    },
  })
  const opened = openProfile != null ? profiles.find((p) => p.id === openProfile) : null
  const yesNo = (v) => t(v ? 'common.yes' : 'common.no')
  const challengeText = (p) => (p.intune_enabled ? t('scep.challengeIntune') : p.challenge_set ? t('scep.challengeHidden') : t('scep.challengeNone'))

  const toggleProfile = async (p) => {
    setBusy(true)
    try {
      await scepService.updateProfile(p.id, { enabled: !p.enabled })
      showSuccess(t(p.enabled ? 'scep.profileDisabled' : 'scep.profileEnabled', { name: p.name }))
      setProfiles((list) => list.map((x) => (x.id === p.id ? { ...x, enabled: !p.enabled } : x)))
      requestAnimationFrame(() => document.getElementById('scep-toggle')?.focus())
    } catch (error) {
      showError(error.message || t('common.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const deleteProfile = async (p) => {
    const confirmed = await showConfirm(t('scep.profileDeleteConfirm', { name: p.name }), {
      title: t('common.confirmDelete'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      await scepService.deleteProfile(p.id)
      showSuccess(t('scep.profileDeleted'))
      setOpenProfile(null)
      loadData()
    } catch (error) {
      showError(error.message)
    }
  }

  // The old challenge stops working at once; the new value is shown once, whatever the clipboard does
  const confirmRotate = async () => {
    const p = rotate
    setBusy(true)
    try {
      const res = await scepService.regenerateProfileChallenge(p.id)
      setRotate(null)
      const value = res.data?.challenge || res.challenge
      if (value) setSecret({ name: p.name, value })
      loadData()
    } catch (error) {
      showError(error.message)
    } finally {
      setBusy(false)
    }
  }

  // ── Requests ──
  const requestName = (r) => parseDN(r.subject).cn || t('scep.requestNumber', { id: r.id })
  const requestPill = (r) => <Pill label={stateLabel(t, r.status)} tone={REQUEST_TONES[r.status] || 'muted'} />
  const handleApprove = async (req) => {
    try {
      await scepService.approveRequest(req.id)
      showSuccess(t('scep.requestApproved'))
      setOpenRequest(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }
  const handleReject = async () => {
    try {
      await scepService.rejectRequest(rejecting.id, rejectReason)
      showSuccess(t('scep.requestRejected'))
      setRejecting(null)
      setRejectReason('')
      setOpenRequest(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  // ── Challenges of the CAs ──
  const regenerateCaChallenge = async (ca) => {
    // Every device already provisioned with the old challenge stops enrolling
    const confirmed = await showConfirm(t('scep.confirmRegenerateChallenge'), {
      title: t('scep.regenerate'), confirmText: t('scep.regenerate'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      await scepService.regenerateChallenge(ca.id)
      showSuccess(t('scep.challengeRegenerated'))
      loadChallenges()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  // ── Intune apps ──
  const deleteApp = async (app) => {
    const confirmed = await showConfirm(t('scep.intuneAppDeleteConfirm', { name: app.name }), {
      title: t('common.confirmDelete'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      await scepService.deleteIntuneApp(app.id)
      showSuccess(t('scep.intuneAppDeleted'))
      setOpenApp(null)
      loadApps()
    } catch (error) {
      showError(error.message)
    }
  }

  // ── Configuration ──
  const savedDraft = configDraft(config)
  const changed = CONFIG_FIELDS.filter((k) => String(draft[k]) !== String(savedDraft[k]))
  const range = config.challenge_validity_range
  const validate = () => {
    const e = {}
    const hours = Number(draft.challenge_validity)
    if (!Number.isInteger(hours) || (range && (hours < range[0] || hours > range[1])) || hours < 1) {
      e.challenge_validity = range ? t('scep.challengeValidityHelp', { min: range[0], max: range[1] }) : t('scep.challengeValidityInvalid')
    }
    const skew = Number(draft.time_skew_minutes)
    if (draft.enforce_signing_time && (!Number.isInteger(skew) || skew < 1 || skew > 1440)) e.time_skew_minutes = t('scep.timeSkewMinutesHelp')
    return e
  }
  const handleSaveConfig = async () => {
    if (!canEdit) return
    const e = validate()
    setErrors(e)
    if (Object.keys(e).length) {
      setAnnounce(t('scep.fixBeforeSaving', { count: Object.keys(e).length }))
      requestAnimationFrame(() => document.querySelector('#settings-form [aria-invalid="true"]')?.focus())
      return
    }
    setSaving(true)
    setFailed([])
    try {
      await scepService.updateConfig({
        ...config, enabled: draft.enabled, ca_id: draft.ca_id === '__none__' ? null : parseInt(draft.ca_id, 10),
        auto_approve: draft.auto_approve, challenge_validity: parseInt(draft.challenge_validity, 10),
        getcacert_chain: draft.getcacert_chain, plain_http: draft.plain_http,
        enforce_signing_time: draft.enforce_signing_time, time_skew_minutes: parseInt(draft.time_skew_minutes, 10),
      })
      showSuccess(t('messages.success.update.settings'))
      setAnnounce(t('messages.success.update.settings'))
      await loadData()
      stateRef.current?.focus()
    } catch (error) {
      setFailed([t('scep.serverSettings')])
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const off = !canEdit
  const unlisted = unlistedScepPickerCas(cas, config.ca_id)
  const sections = [
    {
      id: 'server', label: t('scep.serverSettings'), icon: 'globe', desc: t('scep.enableScepDesc'),
      groups: [{
        legend: t('scep.serverSettings'),
        fields: [
          { key: 'enabled', label: t('scep.enableScep'), checkbox: true, disabled: off },
          { key: 'url', label: t('scep.scepEndpointUrl'), readonly: `${baseUrl}/scep/pkiclient.exe`, hint: t('scep.useThisUrl') },
          {
            key: 'ca_id', label: t('common.issuingCA'), disabled: off,
            hint: unlisted > 0 ? t('cas.notListedForScep', { count: unlisted }) : undefined,
            options: [['__none__', t('common.none')], ...scepPickerCas(cas, config.ca_id).map((ca) => [String(ca.id), ca.name || ca.subject])],
          },
        ],
      }],
    },
    {
      id: 'security', label: t('common.securitySettings'), icon: 'lock', desc: t('scep.securityDesc'),
      groups: [{
        legend: t('common.securitySettings'),
        fields: [
          { key: 'auto_approve', label: t('scep.autoApprove'), hint: t('scep.autoApproveDesc'), checkbox: true, disabled: off || !draft.enabled },
          {
            key: 'challenge_validity', label: `${t('scep.challengeValidity')} (${t('scep.hours')})`, numeric: true, short: true, disabled: off || !draft.enabled,
            hint: range ? t('scep.challengeValidityHelp', { min: range[0], max: range[1] }) : undefined,
          },
          { key: 'getcacert_chain', label: t('scep.getCaCertChain'), hint: t('scep.getCaCertChainHelp'), checkbox: true, disabled: off || !draft.enabled },
          { key: 'plain_http', label: t('scep.plainHttp'), hint: t('scep.plainHttpHelp'), checkbox: true, disabled: off || !draft.enabled },
          { key: 'enforce_signing_time', label: t('scep.enforceSigningTime'), checkbox: true, disabled: off || !draft.enabled },
          ...(draft.enforce_signing_time ? [{ key: 'time_skew_minutes', label: t('scep.timeSkewMinutes'), hint: t('scep.timeSkewMinutesHelp'), numeric: true, short: true, disabled: off || !draft.enabled }] : []),
        ],
      }],
      children: draft.auto_approve && <Notice tone="warn" id="scep-auto-approve-warning">{t('scep.autoApproveWarning')}</Notice>,
    },
    {
      id: 'info', label: t('scep.connectionDetails'), icon: 'help', desc: t('scep.aboutScepDesc'),
      groups: [],
      children: (
        <fieldset className="settings-group">
          <legend>{t('scep.supportedOperations')}</legend>
          <Props items={[
            [t('scep.scepURL'), <Copyable key="u" url value={`${baseUrl}/scep/pkiclient.exe`} label={t('scep.scepURL')} />],
            [t('scep.supportedOperations'), ['GetCACaps', 'GetCACert', 'GetCACertChain', 'PKIOperation'].join(', ')],
          ]} />
          <h3 className="section-title scep-example-title">{t('scep.ciscoExample')}</h3>
          <pre className="code-preview">{`crypto ca trustpoint UCM-CA
 enrollment url ${baseUrl}/scep/pkiclient.exe
 subject-name CN=device.example.com
 revocation-check none
 auto-enroll 70
!
crypto ca authenticate UCM-CA
crypto ca enroll UCM-CA`}</pre>
        </fieldset>
      ),
    },
  ]

  // ── Docks ──
  const profileDock = opened && (
    <Dock label={t('atelier.detailOf', { name: 'SCEP' })} tabsLabel={t('atelier.openItem')} activeKey={opened.id}
      tabs={[{ key: opened.id, title: opened.name, icon: 'globe' }]} onClose={() => setOpenProfile(null)}>
      <DockBody icon="globe" title={opened.name} badge={profilePill(opened)} section="profile" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: opened.name })} sections={[['profile', t('scep.tabs.profile')]]}
        actions={canEdit && <>
          <Btn icon={opened.enabled ? 'block' : 'check'} id="scep-toggle" write disabled={busy || undefined} onClick={() => toggleProfile(opened)}>
            {t(opened.enabled ? 'scep.disable' : 'scep.enable')}
          </Btn>
          {!opened.intune_enabled && <Btn icon="refresh" id="scep-rotate" write onClick={() => setRotate(opened)}>{t('scep.rotate')}</Btn>}
          <Btn icon="settings" id="scep-edit" write onClick={() => setProfileForm({ profile: opened })}>{t('common.edit')}</Btn>
          <Btn icon="block" tone="danger" id="scep-delete" onClick={() => deleteProfile(opened)}>{t('common.delete')}</Btn>
        </>}>
        <div className="module-detail">
          <Section title={t('scep.sections.enrollment')}>
            <Props items={[
              [t('scep.enrollmentUrl'), <span key="u" className="mono url">{profileUrl(opened)}</span>],
              [t('scep.challenge'), challengeText(opened)],
            ]} />
            <CopyUrlButton url={profileUrl(opened)} copy={copy} />
          </Section>
          <Section title={t('scep.sections.issuance')}>
            <Props items={[
              [t('scep.columns.ca'), opened.ca_name || caName(opened.ca_refid)],
              [t('scep.columns.template'), opened.template_name || t('scep.noTemplate')],
              ['Intune', <YesNo key="i" value={opened.intune_enabled} />],
              [t('scep.autoApprove'), <YesNo key="a" value={opened.auto_approve} />],
              [t('atelier.state'), profilePill(opened)],
            ]} />
            {opened.description && <Notice>{opened.description}</Notice>}
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  const req = openRequest
  const requestDock = req && (
    <Dock label={t('atelier.detailOf', { name: t('scep.requests') })} tabsLabel={t('atelier.openItem')} activeKey={req.id}
      tabs={[{ key: req.id, title: requestName(req), icon: 'globe' }]} onClose={() => setOpenRequest(null)}>
      <DockBody icon="globe" title={requestName(req)} badge={requestPill(req)} section="request" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: requestName(req) })} sections={[['request', t('common.requestDetails')]]}
        actions={req.status === 'pending' && canEdit && <>
          <Btn tone="primary" icon="check" id="scep-approve" onClick={() => handleApprove(req)}>{t('scep.approve')}</Btn>
          <Btn tone="danger" icon="block" id="scep-reject" onClick={() => setRejecting(req)}>{t('scep.reject')}</Btn>
        </>}>
        <div className="module-detail">
          <Section title={t('common.requestDetails')}>
            <Props items={[
              [t('scep.transactionId'), <Copyable key="tx" value={req.transaction_id} label={t('scep.transactionId')} />],
              [t('common.subject'), <span key="s" className="mono">{req.subject || '—'}</span>],
              req.profile_id && [t('scep.columns.profile'), profileOf(req.profile_id)?.name || `#${req.profile_id}`],
              [t('scep.columns.ca'), caName(req.ca_refid)],
              req.client_ip && [t('scep.clientIp'), <span key="ip" className="mono">{req.client_ip}</span>],
              [t('atelier.state'), requestPill(req)],
              [t('common.created'), dateTimeOf(req.created_at, locale) || '—'],
              req.approved_at && [t('scep.approvedAt'), `${dateTimeOf(req.approved_at, locale)}${req.approved_by ? ` · ${req.approved_by}` : ''}`],
              req.rejection_reason && [t('scep.rejectionReason'), req.rejection_reason],
            ]} />
          </Section>
          {req.csr_pem && <Section title={t('common.csrContent')}><pre className="code-preview">{req.csr_pem}</pre></Section>}
        </div>
      </DockBody>
    </Dock>
  )

  const caOpen = openCa != null ? (challenges || []).find((c) => c.id === openCa) : null
  const caDock = caOpen && (
    <Dock label={t('atelier.detailOf', { name: t('common.challenges') })} tabsLabel={t('atelier.openItem')} activeKey={caOpen.id}
      tabs={[{ key: caOpen.id, title: caOpen.name || caOpen.subject, icon: 'key' }]} onClose={() => setOpenCa(null)}>
      <DockBody icon="key" title={caOpen.name || caOpen.subject} section="challenge" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: caOpen.name || caOpen.subject })} sections={[['challenge', t('scep.challenge')]]}
        actions={canEdit && <Btn icon="refresh" id="scep-ca-regenerate" write onClick={() => regenerateCaChallenge(caOpen)}>{t('scep.regenerate')}</Btn>}>
        <div className="module-detail">
          <Section title={t('scep.challenge')}>
            <Props items={[
              [t('common.subject'), <span key="s" className="mono">{caOpen.subject || '—'}</span>],
              [t('scep.challenge'), caOpen.scep_challenge ? <Copyable key="c" value={caOpen.scep_challenge} label={t('scep.challenge')} /> : t('scep.noChallengeSet')],
            ]} />
            {!config.enabled && <Notice tone="warn">{t('scep.scepDisabledDesc')}</Notice>}
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  const appOpen = openApp != null ? (apps || []).find((a) => a.id === openApp) : null
  const appDock = appOpen && (
    <Dock label={t('atelier.detailOf', { name: t('scep.intuneApps') })} tabsLabel={t('atelier.openItem')} activeKey={appOpen.id}
      tabs={[{ key: appOpen.id, title: appOpen.name, icon: 'server' }]} onClose={() => setOpenApp(null)}>
      <DockBody icon="server" title={appOpen.name} section="app" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: appOpen.name })} sections={[['app', t('atelier.overview')]]}
        actions={canEdit && <>
          <Btn icon="settings" id="scep-app-edit" write onClick={() => setAppForm({ app: appOpen })}>{t('common.edit')}</Btn>
          <Btn icon="block" tone="danger" id="scep-app-delete" onClick={() => deleteApp(appOpen)}>{t('common.delete')}</Btn>
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('scep.intuneTenantId'), <span key="t" className="mono">{appOpen.tenant_id}</span>],
              [t('scep.intuneClientId'), <span key="c" className="mono">{appOpen.client_id}</span>],
              [t('scep.intuneAppLastTest'), appOpen.last_test_at ? `${dateTimeOf(appOpen.last_test_at, locale)} (${appOpen.last_test_result})` : t('scep.intuneAppNeverTested')],
              [t('scep.profiles'), appOpen.profile_names?.length ? appOpen.profile_names.join(', ') : t('scep.intuneAppNotUsed')],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  const dock = { profiles: profileDock, requests: requestDock, challenges: caDock, intune: appDock, config: null }[view]

  // ── Views ──
  const loadErr = loadError && (
    <LoadError id="scep" journal={auditPath} title={t('messages.errors.loadFailed.scep')} onRetry={() => { setLoading(true); loadData() }}
      cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/scep/config', message: loadError.message }} />} />
  )
  const profilesView = (
    <ListView label="SCEP" caption={t('scep.caption')} icon="globe" list={profileList} nameSort="name" loading={loading}
      filters={{ views: profileFilters.map(([id, label, test]) => ({ id, label, count: profiles.filter(test).length })), active: activeFilter[0], onChange: setProfileState, label: t('scep.filterByState') }}
      title={(p) => p.name} status={profilePill} openedId={openProfile} onOpen={(p) => setOpenProfile(p.id)}
      columns={[
        { id: 'ca', label: t('scep.columns.ca'), cell: (p) => p.ca_name || caName(p.ca_refid), kind: 'text', priority: 2, sort: 'ca' },
        { id: 'template', label: t('scep.columns.template'), cell: (p) => p.template_name || t('scep.noTemplate'), kind: 'text', priority: 3, sort: 'template' },
        { id: 'intune', label: 'Intune', cell: (p) => yesNo(p.intune_enabled), kind: 'fit', priority: 3, labelled: true, sort: 'intune' },
        { status: true, sort: 'state' },
      ]}
      error={loadErr}
      empty={profiles.length ? (
        <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => setProfileState('')} />
      ) : (
        <SetupEmptyBlock id="scep" icon="globe" title={t('scep.noProfiles')} text={t('scep.emptyProfilesText')}
          action={canEdit ? { label: t('scep.newProfile'), icon: 'plus', onClick: () => setProfileForm({ profile: null }), primary: true } : undefined} />
      )}
      footer={{ range: t('scep.range', profileList.counts(profiles.length)) }} />
  )

  const requestViews = [
    { id: '', label: t('common.all'), count: stats.total },
    { id: 'pending', label: t('common.pending'), count: stats.pending, warn: stats.pending > 0 },
    { id: 'approved', label: t('common.approved'), count: stats.approved },
    { id: 'rejected', label: t('common.rejected'), count: stats.rejected },
  ]
  const pages = Math.max(1, Math.ceil(totalRequests / perPage))
  const start = totalRequests ? (page - 1) * perPage + 1 : 0
  // The rows wait for the profiles and authorities their cells name: the columns are measured on the first rows drawn
  const requestsView = (
    <ListView label={t('scep.requests')} caption={t('scep.requestsCaption')} icon="globe" rows={loading ? NONE : requests} loading={requestsLoading || loading}
      filters={{ views: requestViews, active: statusFilter, onChange: (v) => { setStatusFilter(v); setPage(1) }, label: t('scep.filterByState') }}
      toolbar={(
        <Toolbar>
          <SearchField id="scep-request-search" name="q" label={t('scep.searchRequests')} placeholder={t('scep.searchRequests')} value={searchQuery}
            onChange={(v) => { setSearchQuery(v); setPage(1) }} />
          <IconBtn icon="refresh" label={t('common.refresh')} onClick={() => loadData()} />
        </Toolbar>
      )}
      title={requestName} status={requestPill} openedId={req?.id} onOpen={setOpenRequest}
      nameSort="subject" sort={requestSort.sort} onSort={requestSort.onSort}
      columns={[
        // The name takes the room left; the transaction id, a long identifier, folds first with its whole value in its title
        { id: 'tx', label: t('scep.transactionId'), cell: (r) => <span className="mono">{r.transaction_id}</span>, kind: 'text', priority: 4,
          title: (r) => r.transaction_id || undefined, sort: 'transaction_id' },
        { id: 'profile', label: t('scep.columns.profile'), cell: (r) => (r.profile_id ? profileOf(r.profile_id)?.name || `#${r.profile_id}` : t('scep.caWide')), kind: 'text', priority: 3 },
        { id: 'ca', label: t('scep.columns.ca'), cell: (r) => caName(r.ca_refid), kind: 'text', priority: 3 },
        { id: 'created', label: t('scep.requested'), cell: (r) => dateTimeOf(r.created_at, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'created_at' },
        { status: true, sort: 'status' },
      ]}
      empty={searchQuery || statusFilter ? (
        <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => { setSearchQuery(''); setStatusFilter(''); setPage(1) }} />
      ) : <EmptyBlock id="scep-requests" icon="globe" title={t('scep.noRequests')} text={t('scep.noRequestsDesc')} />}
      footer={{
        range: t('scep.requestRange', { start, end: Math.min(page * perPage, totalRequests), count: totalRequests }),
        pagination: { page, pages, perPage, onPage: setPage, onPerPage: (v) => { setPerPage(v); setPage(1) } },
      }} />
  )

  const challengeList = useClientList(challenges || NONE, {
    sortParam: challengeSort,
    sorts: { name: (c) => c.name || c.subject, subject: (c) => c.subject || null, state: (c) => (c.scep_challenge ? 0 : 1) },
  })
  const appList = useClientList(apps || NONE, {
    sortParam: appSort,
    sorts: {
      name: (a) => a.name, tenant: (a) => a.tenant_id, client: (a) => a.client_id,
      test: (a) => (a.last_test_at ? Date.parse(a.last_test_at) : null), state: (a) => a.profile_count || 0,
    },
  })
  const challengesView = (
    <>
      {!config.enabled && !loading && <Notice tone="warn" id="scep-disabled">{t('scep.scepDisabledDesc')}</Notice>}
      <ListView label={t('common.challenges')} caption={t('scep.challengesCaption')} icon="key" list={challengeList} nameSort="name" loading={loading || challenges === null}
        title={(c) => c.name || c.subject} status={(c) => <Pill label={t(c.scep_challenge ? 'scep.challengeSet' : 'scep.noChallengeSet')} tone={c.scep_challenge ? 'good' : 'muted'} />}
        openedId={openCa} onOpen={(c) => setOpenCa(c.id)}
        columns={[{ id: 'subject', label: t('common.subject'), cell: (c) => c.subject, grow: true, muted: true, kind: 'text', priority: 4, sort: 'subject' }, { status: true, sort: 'state' }]}
        empty={<EmptyBlock id="scep-cas" icon="key" title={t('scep.noCasAvailable')} text={t('scep.noCasAvailableDesc')} />}
        footer={{ range: t('crlOcsp.range', challengeList.counts((challenges || []).length)) }} />
    </>
  )

  const intuneView = (
    <ListView label={t('scep.intuneApps')} caption={t('scep.intuneCaption')} icon="server" list={appList} nameSort="name" loading={apps === null}
      title={(a) => a.name} status={(a) => <Pill label={a.profile_count > 0 ? t('scep.intuneAppUsedBy', { count: a.profile_count }) : t('scep.intuneAppNotUsed')} tone={a.profile_count > 0 ? 'good' : 'muted'} />}
      openedId={openApp} onOpen={(a) => setOpenApp(a.id)}
      columns={[
        // Two identifiers of Microsoft Entra: they fold first, their whole value in their title
        { id: 'tenant', label: t('scep.intuneTenantId'), cell: (a) => <span className="mono">{a.tenant_id}</span>, kind: 'text', priority: 4, title: (a) => a.tenant_id, sort: 'tenant' },
        { id: 'client', label: t('scep.intuneClientId'), cell: (a) => <span className="mono">{a.client_id}</span>, kind: 'text', priority: 4, title: (a) => a.client_id, sort: 'client' },
        { id: 'test', label: t('scep.columns.lastTest'), labelFull: t('scep.intuneAppLastTest'), kind: 'fit', priority: 3, labelled: true, sort: 'test',
          cell: (a) => (a.last_test_at ? dateTimeOf(a.last_test_at, locale) : t('scep.intuneAppNeverTested')) },
        { status: true, sort: 'state' },
      ]}
      empty={<EmptyBlock id="scep-intune" icon="server" title={t('scep.noIntuneApps')} text={t('scep.noIntuneAppsDesc')}
        action={canEdit ? { label: t('scep.newIntuneApp'), icon: 'plus', onClick: () => setAppForm({ app: null }), primary: true } : undefined} />}
      footer={{ range: t('scep.intuneRange', appList.counts((apps || []).length)) }} />
  )

  const configView = loading ? <SkeletonPanel label={t('common.loading')} /> : loadError ? loadErr : (
    <SettingsView sections={sections} values={draft} errors={errors} changed={changed}
      onChange={(k, v) => { setDraft((d) => ({ ...d, [k]: v })); if (errors[k]) setErrors((e) => { const n = { ...e }; delete n[k]; return n }) }}
      onSave={handleSaveConfig} onReset={() => { setDraft(savedDraft); setErrors({}) }} saving={saving} failed={failed} announce={announce}
      stateRef={stateRef} tocLabel={t('protocols.sectionsOf', { name: 'SCEP' })} />
  )

  const totals = {
    profiles: t('scep.unit', { count: profiles.length }),
    requests: t('scep.requestUnit', { count: totalRequests }),
    challenges: t('crlOcsp.unit', { count: cas.length }),
    intune: t('scep.intuneUnit', { count: (apps || []).length }),
    config: t('protocols.sections', { count: sections.length }),
  }
  const create = canEdit && (view === 'profiles'
    ? <Btn tone="primary" icon="plus" id="scep-new" onClick={() => setProfileForm({ profile: null })}>{t('scep.newProfile')}</Btn>
    : view === 'intune' ? <Btn tone="primary" icon="plus" id="scep-app-new" onClick={() => setAppForm({ app: null })}>{t('scep.newIntuneApp')}</Btn> : null)

  return (
    <Zone dock={dock} after={<>
      {profileForm && (
        <ScepProfileForm profile={profileForm.profile} cas={cas} templates={templates} onClose={() => setProfileForm(null)}
          onSaved={() => { setProfileForm(null); loadData() }} onManageIntuneApps={() => setView('intune')} />
      )}
      {appForm && (
        <IntuneAppForm app={appForm.app} onClose={() => setAppForm(null)}
          onSaved={(o) => { if (!o?.keepOpen) setAppForm(null); loadApps() }} />
      )}
      {rotate && (
        <AtelierDialog size="narrow" title={t('scep.rotateTitle')} onClose={() => setRotate(null)} returnTo="scep-rotate">
          <div className="notice warn"><Icon name="warning" /><span>{t('scep.rotateWarning', { name: rotate.name })}</span></div>
          <div className="modal-actions">
            <Btn onClick={() => setRotate(null)}>{t('common.cancel')}</Btn>
            <Btn tone="primary" icon="refresh" id="scep-rotate-confirm" disabled={busy || undefined} onClick={confirmRotate}>{t('scep.regenerate')}</Btn>
          </div>
        </AtelierDialog>
      )}
      {secret && (
        <AtelierDialog size="narrow" title={t('scep.newChallengeTitle')} onClose={() => setSecret(null)} returnTo="scep-rotate">
          <p className="event-detail">{t('scep.newChallengeOnce', { name: secret.name })}{' '}<strong className="mono secret" id="scep-new-secret">{secret.value}</strong></p>
          <p className="small muted">{t('scep.newChallengeHint')}</p>
          <div className="modal-actions">
            <Btn icon="copy" id="scep-secret-copy" onClick={async () => { if (await copy(secret.value)) showSuccess(t('common.copied')) }}>{t('common.copy')}</Btn>
            <Btn tone="primary" write={false} onClick={() => setSecret(null)}>{t('common.close')}</Btn>
          </div>
        </AtelierDialog>
      )}
      {rejecting && (
        <AtelierDialog size="narrow" title={t('scep.rejectRequest')} onClose={() => { setRejecting(null); setRejectReason('') }} returnTo="scep-reject">
          <div className="notice bad"><Icon name="warning" /><span>{t('scep.rejectEnrollment')} <span className="mono">{rejecting.subject || rejecting.transaction_id}</span></span></div>
          <div className="form-fields">
            <div className="field full">
              <label htmlFor="scep-reject-reason">{t('scep.rejectionReason')}</label>
              <textarea id="scep-reject-reason" rows={3} data-autofocus value={rejectReason} placeholder={t('scep.rejectionPlaceholder')}
                onChange={(e) => setRejectReason(e.target.value)} />
            </div>
          </div>
          <div className="modal-actions">
            <Btn onClick={() => { setRejecting(null); setRejectReason('') }}>{t('common.cancel')}</Btn>
            <Btn tone="danger" icon="block" id="scep-reject-confirm" onClick={handleReject}>{t('scep.rejectRequest')}</Btn>
          </div>
        </AtelierDialog>
      )}
    </>}>
      <PageHead title="SCEP" total={totals[view]} intent={t('shell.moduleDesc.scep')}
        actions={<>
          <ViewSwitch id="scep-view" label={t('protocols.view')} value={view} onChange={setView}
            options={[
              { value: 'profiles', label: t('scep.profiles') }, { value: 'requests', label: t('scep.requests') },
              { value: 'challenges', label: t('scep.views.challenges') }, { value: 'intune', label: t('scep.intuneApps') },
              { value: 'config', label: t('common.config') },
            ]} />
          {create}
        </>} />
      {{ profiles: profilesView, requests: requestsView, challenges: challengesView, intune: intuneView, config: configView }[view]}
    </Zone>
  )
}

function CopyUrlButton({ url, copy }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()
  return (
    <Btn icon="copy" className="btn copy-url" onClick={async () => { if (await copy(url)) showSuccess(t('common.copied')) }}>{t('scep.copyUrl')}</Btn>
  )
}
