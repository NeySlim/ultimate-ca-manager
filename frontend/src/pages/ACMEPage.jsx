/**
 * ACME: the mockup's acme module, a listView() of the server's accounts (Contact, Créé le, État,
 * Commandes) with its dock (Compte, Commandes, Défis) and the Désactiver le compte… dialog, and the
 * Copier l'URL du répertoire action of its head. What the product has more takes the same list and
 * dock, or the mockup's settingsView(), behind the page switch: the server's orders, local domains,
 * EAB credentials and settings; the client's settings, orders, upstream CAs, DNS providers and
 * domains; the history of ACME certificates. The client of an account, its EAB binding, its last
 * order in the list and its journal (M01), the failure of a challenge (M02) and the revocation of
 * an order's certificate (M03) are functions the product lacks.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Modal } from '../components/atelier/Form'
import { Zone, Icon, Btn, IconBtn, Pill, RecordList, RecordRow, PageHead, Toolbar, SearchField, ListView, SkeletonPanel, EmptyBlock, NoMatch, LoadError, LoadCause, useClientList, useSortParam } from '../components/atelier'
import { acmeService, casService, certificatesService, templatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useClipboard } from '../hooks'
import { useLinkedId } from '../hooks/useLinkedId'
import { useDockSelection, asId } from '../components/atelier/useDockParam'
import { stateLabel } from '../lib/stateLabel'
import { downloadBlob, publicBaseUrl } from '../lib/utils'
import { fetchPages, fetchListing } from '../lib/fetchAllPages'
import { dateOf } from './admin/adminDates'
import AccountDock from './acme/AccountDetailPanel'
import LetsEncryptTab from './acme/LetsEncryptTab'
import LetsEncryptOrdersTab from './acme/LetsEncryptOrdersTab'
import ConfigTab from './acme/ConfigTab'
import DnsProvidersTab from './acme/DnsProvidersTab'
import DomainsTab from './acme/DomainsTab'
import LocalDomainsTab from './acme/LocalDomainsTab'
import LocalOrdersTab from './acme/LocalOrdersTab'
import EabTab from './acme/EabTab'
import HistoryTab from './acme/HistoryTab'
import CreateAccountForm from './acme/CreateAccountForm'
import RequestCertificateForm from './acme/RequestCertificateForm'
import CaAccountsManager from './acme/CaAccountsManager'
import { effectiveDnsUpdatePort } from './acme/dnsUpdatePort'
import DnsProviderForm from './acme/DnsProviderForm'
import DomainForm from './acme/DomainForm'
import LocalDomainForm from './acme/LocalDomainForm'
import { Notice, ViewSwitch } from './protocols/atelierParts'
import { DockSlot, DockSlotProvider, SlotDock } from './protocols/dockSlot'
import { ACCOUNT_TONES, accountLabel, accountContact } from './protocols/protocolStates'

// The order list pages by 100 rows; the tab shows and filters all of them
const CLIENT_ORDERS_MAX = 5000
// The accounts too: every page is read (100 a page), so the list sorts and searches them all
const ACCOUNTS_MAX = 5000

// The default sorts (COLONNES-SPEC T4, E16): the newest account, the latest certificate first
const NEWEST_ACCOUNT = { key: 'created', asc: false }
const ACCOUNT_SORT_KEYS = ['name', 'contact', 'created', 'state', 'orders']
const LATEST_ISSUED = { key: 'created_at', asc: false }
const HISTORY_SORT_KEYS = ['common_name', 'source', 'valid_to', 'created_at', 'status']

// The views keep the former tab names of /acme?tab=…: the accounts (the mockup's list) open first
const SERVER_VIEWS = ['accounts', 'localorders', 'localdomains', 'eab', 'config']
const CLIENT_VIEWS = ['letsencrypt', 'letsencryptorders', 'upstream', 'dns', 'domains']
const ACME_TABS = [...SERVER_VIEWS, ...CLIENT_VIEWS, 'history']

const NONE = []
const ACCOUNT_SECTIONS = ['account', 'orders', 'challenges']

export default function ACMEPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { showSuccess, showError, showConfirm, showWarning, showInfo } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()
  const { copy } = useClipboard()

  // Data states - ACME Server
  const [accounts, setAccounts] = useState([])
  const [accountsPartial, setAccountsPartial] = useState(null)
  const [orders, setOrders] = useState([])
  const [challenges, setChallenges] = useState([])
  const [acmeSettings, setAcmeSettings] = useState({})
  const [serverSaved, setServerSaved] = useState({})
  // Profiles as the server holds them: its template bindings decide what stays offered
  const [savedProfiles, setSavedProfiles] = useState({})
  const [cas, setCas] = useState([])
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)

  // Data states - ACME client
  const [clientOrders, setClientOrders] = useState([])
  const [clientOrdersPartial, setClientOrdersPartial] = useState(null)
  // Server-paged views: their totals, read with the page and kept up to date by the views themselves
  const [localOrdersTotal, setLocalOrdersTotal] = useState(null)
  const [eabTotal, setEabTotal] = useState(null)
  const [clientSettings, setClientSettings] = useState({})
  const [dnsRestartRequired, setDnsRestartRequired] = useState(false)
  const [caAccounts, setCaAccounts] = useState([])
  const [dnsProviders, setDnsProviders] = useState([])
  const [dnsProviderTypes, setDnsProviderTypes] = useState([])
  const [acmeDomains, setAcmeDomains] = useState([])
  const [localDomains, setLocalDomains] = useState([])
  const [selectedDnsProvider, setSelectedDnsProvider] = useState(null)
  const [selectedAcmeDomain, setSelectedAcmeDomain] = useState(null)

  // UI states
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saving, setSaving] = useState(false)
  // /acme?tab=<view>&order=N: the view, and the order it holds
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const linkedTab = searchParams.get('tab')
  const linkedOrder = useLinkedId('order')
  const activeTab = ACME_TABS.includes(linkedTab) ? linkedTab : 'accounts'
  // The new view's URL carries no object: its dock closes
  const setActiveTab = (tab) => setSearchParams(tab === 'accounts' ? {} : { tab }, { replace: true })

  // The object open in the view's dock lives in the URL (`item`, the account's `section` too)
  const accountSel = useDockSelection(activeTab === 'accounts' ? accounts : NONE, { ready: false, sections: ACCOUNT_SECTIONS, fallback: 'account' })
  const selectedAccount = activeTab === 'accounts' ? accountSel.selected : null
  const setSelectedAccount = accountSel.select
  const { section: activeDetailTab, setSection: setActiveDetailTab } = accountSel
  const orderSel = useDockSelection(activeTab === 'letsencryptorders' ? clientOrders : NONE, { ready: activeTab === 'letsencryptorders' && !loading })
  const selectedClientOrder = activeTab === 'letsencryptorders' ? orderSel.selected : null
  const setSelectedClientOrder = orderSel.select
  const certSel = useDockSelection(activeTab === 'history' ? history : NONE, { ready: activeTab === 'history' && !historyLoading })
  const selectedCert = activeTab === 'history' ? certSel.selected : null
  const setSelectedCert = certSel.select
  // An order shown from elsewhere (a link, a new request): its view and its dock in one URL step
  const showOrder = (tab, order) => {
    if (tab === 'letsencryptorders') orderSel.hold(order)
    setSearchParams({ tab, item: String(order.id) }, { replace: true })
  }
  const [linkedLocalOrder, setLinkedLocalOrder] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showRequestModal, setShowRequestModal] = useState(false)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [preflightResult, setPreflightResult] = useState(null)
  const [showDnsProviderModal, setShowDnsProviderModal] = useState(false)
  const [showDomainModal, setShowDomainModal] = useState(false)
  const [showLocalDomainModal, setShowLocalDomainModal] = useState(false)
  const [selectedLocalDomain, setSelectedLocalDomain] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [accountState, setAccountState] = useState('')
  const [revokeSuperseded, setRevokeSuperseded] = useState(false)
  const [, setEabHmacInput] = useState(null)
  const [showRevokeConfirm, setShowRevokeConfirm] = useState(false)
  const [openEabCreate, setOpenEabCreate] = useState(false)
  const [upstreamCreate, setUpstreamCreate] = useState(0)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionResult, setConnectionResult] = useState(null)

  // History filters
  const [historyFilterStatus, setHistoryFilterStatus] = useState([])
  const [historyFilterCA, setHistoryFilterCA] = useState('')
  const [historyFilterSource, setHistoryFilterSource] = useState('')
  // The history is paged, filtered and sorted by the server
  const [historyPage, setHistoryPage] = useState(1)
  const [historyPerPage, setHistoryPerPage] = useState(25)
  const [historyTotal, setHistoryTotal] = useState(0)
  const [historyCAs, setHistoryCAs] = useState([])
  const [historySearch, setHistorySearch] = useState('')
  // The sort of each list lives in the address of its own view only (T9)
  const accountSort = useSortParam(NEWEST_ACCOUNT, activeTab === 'accounts' ? ACCOUNT_SORT_KEYS : NONE)
  const historySortParam = useSortParam(LATEST_ISSUED, activeTab === 'history' ? HISTORY_SORT_KEYS : NONE)
  const historySort = historySortParam.sort
  // A sort read from the address (a click, Back, a shared link) goes back to page one
  const historySortMark = `${historySort.key}:${historySort.asc}`
  const [historyMarked, setHistoryMarked] = useState(historySortMark)
  if (historyMarked !== historySortMark) { setHistoryMarked(historySortMark); setHistoryPage(1) }

  // EAB: only the required flag stays in the page; the credentials live in EabTab
  const [eabRequired, setEabRequired] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (!linkedOrder || !['letsencryptorders', 'localorders'].includes(linkedTab)) return
    let cancelled = false
    const client = linkedTab === 'letsencryptorders'
    const fetchOrder = client ? acmeService.getClientOrder(linkedOrder) : acmeService.getLocalOrder(linkedOrder)
    fetchOrder.then((res) => {
      const order = res?.data
      if (cancelled || !order) return
      const stillFailing = client ? order.renewal_failures > 0 : String(order.status).toLowerCase() === 'invalid'
      // Followed from the open page, the tab does not remount: switch to the order's tab
      if (!client) setLinkedLocalOrder(order)
      showOrder(linkedTab, order)
      if (!stillFailing) {
        showInfo(t('overview.link.handled', { id: order.id, status: stateLabel(t, order.status) }))
      }
    }).catch((error) => {
      if (cancelled) return
      if (error?.status === 404) showInfo(t('overview.link.gone', { id: linkedOrder }))
      else showError(error.message || t('messages.errors.loadFailed.acme'))
    })
    return () => { cancelled = true }
  }, [linkedOrder, linkedTab]) // eslint-disable-line react-hooks/exhaustive-deps

  // Templates a certificate profile may bind (CA templates excluded, as for
  // SCEP profiles); loaded once, independently of the ACME data refreshes.
  const [templates, setTemplates] = useState([])
  useEffect(() => {
    templatesService.getAll()
      .then(res => setTemplates((res.data || []).filter(tpl => tpl.template_type !== 'ca')))
      .catch(() => setTemplates([]))
  }, [])

  // Poll status for an order running the background auto-poll flow (DNS-01 with
  // an automated provider). request_certificate returns immediately and kicks
  // off a background thread; the UI reflects progress by polling /status until
  // the order reaches a terminal state.
  useEffect(() => {
    const order = selectedClientOrder
    if (!order || !['processing', 'validating'].includes(order.status)) return
    let cancelled = false
    const poll = async () => {
      try {
        const result = await acmeService.checkOrderStatus(order.id)
        if (cancelled) return
        const updated = result.data?.order
        const status = result.data?.status
        if (updated) {
          setSelectedClientOrder(updated)
          setClientOrders(prev => prev.map(o => o.id === updated.id ? updated : o))
        }
        if (status === 'issued') {
          showSuccess(t('acme.orderFinalized'))
          loadData()
        } else if (status === 'invalid') {
          showError(order.error_message || t('acme.orderInvalid'))
          loadData()
        }
      } catch {
        // Network blip — keep polling; the user can also refresh manually.
      }
    }
    const interval = setInterval(poll, 4000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [selectedClientOrder?.id, selectedClientOrder?.status])

  const historyParams = useCallback((paging) => {
    const params = { ...paging }
    if (historyFilterStatus.length > 0) params.status = historyFilterStatus
    if (historyFilterCA) params.ca = historyFilterCA
    if (historyFilterSource) params.source = historyFilterSource
    if (historySearch) params.search = historySearch
    params.sort_by = historySort.key
    params.sort_order = historySort.asc ? 'asc' : 'desc'
    return params
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(historyFilterStatus), historyFilterCA, historyFilterSource, historySearch, historySort])

  const historySeq = useRef(0)
  const loadHistory = useCallback(async () => {
    // An answer older than the last request sent is dropped
    const seq = ++historySeq.current
    try {
      const res = await acmeService.getHistory(historyParams({ page: historyPage, per_page: historyPerPage }))
      if (seq !== historySeq.current) return
      setHistory(res.data || [])
      setHistoryTotal(res.meta?.total ?? (res.data || []).length)
      setHistoryCAs((res.meta?.cas || []).map((name) => ({ value: name, label: name })))
    } catch (error) {
      if (seq === historySeq.current) notifyRef.current(error.message)
    } finally {
      if (seq === historySeq.current) setHistoryLoading(false)
    }
  }, [historyParams, historyPage, historyPerPage])
  const notifyRef = useRef(() => {})
  notifyRef.current = (message) => showError(message || t('messages.errors.loadFailed.acme'))
  const loadHistoryRef = useRef(loadHistory)
  loadHistoryRef.current = loadHistory
  useEffect(() => { loadHistory() }, [loadHistory])

  // Every page of the history as filtered and sorted on screen, for the table's export
  const exportHistory = useCallback((paging) => acmeService.getHistory(historyParams(paging)), [historyParams])

  const loadData = async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [accountsRes, settingsRes, casRes, clientOrdersRes, clientSettingsRes, dnsProvidersRes, dnsTypesRes, domainsRes, localDomainsRes, eabReqRes, caAccountsRes] = await Promise.all([
        fetchListing((page) => acmeService.getAccounts(page), { max: ACCOUNTS_MAX }).then(({ rows, partial }) => ({ data: rows, partial })),
        acmeService.getSettings(),
        casService.getAll(),
        fetchPages((page) => acmeService.getClientOrders(undefined, undefined, page), { max: CLIENT_ORDERS_MAX })
          .then(({ rows, total, complete }) => ({ data: rows, partial: complete ? null : { loaded: rows.length, total } }))
          .catch(() => ({ data: [] })),
        acmeService.getClientSettings().catch(() => ({ data: {} })),
        acmeService.getDnsProviders().catch(() => ({ data: [] })),
        acmeService.getDnsProviderTypes().catch(() => ({ data: [] })),
        acmeService.getDomains().catch(() => ({ data: [] })),
        acmeService.getLocalDomains().catch(() => ({ data: [] })),
        acmeService.getEabRequired().catch(() => ({ data: { eab_required: false } })),
        acmeService.getCaAccounts().catch(() => ({ data: [] })),
      ])
      // The totals of the two views paged by the server: one row each, only their meta is read
      Promise.resolve().then(() => acmeService.getLocalOrders({ page: 1, per_page: 1 }))
        .then((res) => setLocalOrdersTotal(res?.data?.meta?.total ?? res?.meta?.total ?? null)).catch(() => {})
      Promise.resolve().then(() => acmeService.listEabCredentials(undefined, { page: 1, per_page: 1 }))
        .then((res) => setEabTotal(res?.meta?.total ?? null)).catch(() => {})
      setAccounts(accountsRes.data || [])
      setAccountsPartial(accountsRes.partial)
      setAcmeSettings(settingsRes.data || settingsRes || {})
      setServerSaved(settingsRes.data || settingsRes || {})
      setSavedProfiles((settingsRes.data || settingsRes || {}).profiles || {})
      setCas(casRes.data || casRes.cas || [])
      setClientOrders(clientOrdersRes.data || [])
      setClientOrdersPartial(clientOrdersRes.partial || null)
      setClientSettings(clientSettingsRes.data || {})
      setCaAccounts(caAccountsRes.data || [])
      setEabHmacInput(null)
      setEabRequired(!!(eabReqRes.data?.eab_required))
      
      setDnsProviders(dnsProvidersRes.data || [])
      setDnsProviderTypes(dnsTypesRes.data || [])
      setAcmeDomains(domainsRes.data || [])
      setLocalDomains(localDomainsRes.data || [])
      loadHistoryRef.current()
    } catch (error) {
      setLoadError(error)
      showError(error.message || t('messages.errors.loadFailed.acme'))
    } finally {
      setLoading(false)
    }
  }

  // Select an account; its details, orders and challenges are read once its id is in the URL (a click or a reload)
  const selectAccount = setSelectedAccount
  const accountItem = activeTab === 'accounts' ? accountSel.item : null
  useEffect(() => {
    if (!accountItem || loading) return undefined
    let live = true
    const id = asId(accountItem)
    setOrders([])
    setChallenges([])
    Promise.all([acmeService.getAccountById(id), acmeService.getOrders(id), acmeService.getChallenges(id)])
      .then(([accountRes, ordersRes, challengesRes]) => {
        if (!live) return
        setSelectedAccount(accountRes.data || accountRes)
        setOrders(ordersRes.data || [])
        setChallenges(challengesRes.data || [])
      }, (error) => {
        if (!live) return
        showError(error.message || t('messages.errors.loadFailed.generic'))
        if (!accounts.some((a) => String(a.id) === accountItem)) setSelectedAccount(null)
      })
    return () => { live = false }
  }, [accountItem, loading]) // eslint-disable-line react-hooks/exhaustive-deps

  // Settings handlers
  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      await acmeService.updateSettings(acmeSettings)
      setSavedProfiles(acmeSettings.profiles || {})
      setServerSaved(acmeSettings)
      showSuccess(t('messages.success.update.settings'))
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const updateSetting = (key, value) => {
    setAcmeSettings(prev => ({ ...prev, [key]: value }))
  }

  // =========================================================================
  // Let's Encrypt Proxy Handlers
  // =========================================================================

  const handleRegisterProxy = async (typedEmail) => {
    const accountId = clientSettings.proxy_acme_account_id
    const selected = caAccounts.find(a => a.id === accountId)
    const email = (typedEmail || selected?.email || '').trim()
    if (!accountId) {
      showError(t('acme.proxySelectCaAccount'))
      return
    }
    if (!email) {
      showError(t('messages.errors.validation.requiredField'))
      return
    }
    try {
      await acmeService.registerProxy(email, accountId)
      showSuccess(t('acme.proxyRegisteredSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.proxyRegistrationFailed'))
    }
  }

  const handleUnregisterProxy = async () => {
    const confirmed = await showConfirm(t('acme.confirmUnregisterProxy'))
    if (!confirmed) return
    try {
      await acmeService.unregisterProxy(clientSettings.proxy_acme_account_id)
      showSuccess(t('acme.proxyUnregisteredSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.proxyUnregistrationFailed'))
    }
  }

  const handleResetProxyAccount = async () => {
    const confirmed = await showConfirm(t('acme.resetAccountConfirm'))
    if (!confirmed) return
    try {
      await acmeService.updateClientSettings({ reset_proxy_account: true })
      showSuccess(t('acme.resetAccountSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    }
  }

  const handleTestConnection = async () => {
    setTestingConnection(true)
    setConnectionResult(null)
    try {
      const res = await acmeService.testProxyConnection({
        acmeAccountId: clientSettings.proxy_acme_account_id,
      })
      setConnectionResult(res.data || res)
    } catch (error) {
      setConnectionResult({ connected: false, error: error.message })
    } finally {
      setTestingConnection(false)
    }
  }

  // =========================================================================
  // Let's Encrypt Client Handlers
  // =========================================================================
  
  // The DNS UPDATE listener port is read at start: the response says if a restart is needed.
  const handleToggleRevokeOnRenewal = (enabled) => {
    if (enabled && revokeSuperseded && acmeSettings.superseded_count > 0) {
      setShowRevokeConfirm(true)
    } else {
      updateSetting('revoke_on_renewal', enabled)
      if (enabled) setRevokeSuperseded(false)
    }
  }

  const handleConfirmRevokeSuperseded = async () => {
    try {
      setAcmeSettings(prev => ({ ...prev, revoke_on_renewal: true }))
      await acmeService.updateSettings({ ...acmeSettings, revoke_on_renewal: true, revoke_superseded: true })
      showSuccess(t('acme.supersededRevoked', { count: acmeSettings.superseded_count }))
      setShowRevokeConfirm(false)
      setRevokeSuperseded(false)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
      loadData()
    }
  }
  
  const handleRequestCertificate = async (data) => {
    try {
      const result = await acmeService.requestCertificate(data)
      const payload = result.data || {}
      if (payload.challenge_warning) {
        showWarning(payload.challenge_warning)
      } else if (payload.auto_polling) {
        showInfo(t('acme.certificateRequestAutoPolling'))
      } else {
        showSuccess(t('acme.certificateRequestCreated'))
      }
      setShowRequestModal(false)
      loadData()
      if (payload.order) showOrder('letsencryptorders', payload.order)
    } catch (error) {
      showError(error.message || t('acme.certificateRequestFailed'))
    }
  }

  const handlePreflight = async (data) => {
    setPreflightLoading(true)
    try {
      const result = await acmeService.preflightCertificate(data)
      const report = result.data || {}
      setPreflightResult(report)
      if (report.ok) {
        showSuccess(t('acme.preflightPassed'))
      } else {
        showWarning(t('acme.preflightFailed'))
      }
    } catch (error) {
      showError(error.message || t('acme.preflightError'))
    } finally {
      setPreflightLoading(false)
    }
  }

  // --- Multi-CA account management ---
  const handleCreateCaAccount = async (data) => {
    try {
      await acmeService.createCaAccount(data)
      showSuccess(t('acme.caAccountCreated'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.generic'))
      throw error
    }
  }

  const handleUpdateCaAccount = async (id, data) => {
    try {
      await acmeService.updateCaAccount(id, data)
      showSuccess(t('acme.caAccountUpdated'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
      throw error
    }
  }

  const handleDeleteCaAccount = async (id) => {
    // The account key goes with it; the sibling Deactivate already asked.
    const confirmed = await showConfirm(t('acme.confirmDeleteCaAccount'), {
      title: t('common.confirmDelete'),
      confirmText: t('common.delete'),
      variant: 'danger',
    })
    if (!confirmed) return
    try {
      await acmeService.deleteCaAccount(id)
      showSuccess(t('acme.caAccountDeleted'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
    }
  }

  const handleSetDefaultCaAccount = async (id) => {
    try {
      await acmeService.setDefaultCaAccount(id)
      showSuccess(t('acme.caAccountDefaultSet'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  const handleRegisterCaAccount = async (id, email) => {
    try {
      const res = await acmeService.registerCaAccount(id, email)
      showSuccess(res.message || t('acme.caAccountRegistered'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.registrationFailed'))
    }
  }

  const handleDeactivateCaAccount = async (id) => {
    const confirmed = await showConfirm(t('acme.confirmDeactivateCaAccount'), {
      title: t('acme.deactivateAccountTitle'),
      confirmText: t('common.deactivateAccount'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await acmeService.deactivateCaAccount(id)
      showSuccess(t('acme.caAccountDeactivated'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.accountDeactivationFailed'))
    }
  }

  const handleVerifyChallenge = async (order, force = false) => {
    try {
      const result = await acmeService.verifyChallenge(order.id, null, force)
      const data = result.data || {}

      // DNS self-check gate: the expected TXT record isn't visible to UCM yet.
      // Don't submit (a failed validation marks the order invalid and burns the
      // token). Surface the missing domains and offer to force-verify anyway.
      if (data.dns_not_ready) {
        const missing = (data.missing || []).join(', ') || '?'
        const confirmed = await showConfirm(
          t('acme.dnsNotReadyConfirmDesc', { domains: missing }),
          {
            title: t('acme.dnsNotReadyTitle'),
            confirmText: t('acme.forceVerify'),
            variant: 'primary',
          }
        )
        if (confirmed) {
          return handleVerifyChallenge(order, true)
        }
        showWarning(t('acme.dnsNotReadyWarning', { domains: missing }))
        return
      }

      // Same gate for HTTP-01: UCM could not fetch the challenge file itself.
      if (data.http_not_ready) {
        const missing = (data.missing || []).join(', ') || '?'
        const confirmed = await showConfirm(
          t('acme.http01NotReadyConfirmDesc', { domains: missing }),
          {
            title: t('acme.http01NotReadyTitle'),
            confirmText: t('acme.forceVerify'),
            variant: 'primary',
          }
        )
        if (confirmed) {
          return handleVerifyChallenge(order, true)
        }
        showWarning(t('acme.http01NotReadyWarning', { domains: missing }))
        return
      }

      const updatedOrder = data.order
      if (updatedOrder?.status === 'ready') {
        showSuccess(t('acme.challengeValidated'))
      } else if (updatedOrder?.status === 'pending') {
        showWarning(result.message || t('acme.challengeVerificationFailed'))
      } else {
        showSuccess(t('acme.challengeVerificationStarted'))
      }
      loadData()
    } catch (error) {
      showError(error.message || t('acme.challengeVerificationFailed'))
    }
  }
  
  const handleCheckOrderStatus = async (order) => {
    try {
      const result = await acmeService.checkOrderStatus(order.id)
      const status = result.data?.status
      if (status === 'ready') {
        showSuccess(t('acme.orderReady'))
      } else if (status === 'valid' || status === 'issued') {
        showSuccess(t('acme.orderFinalized'))
      } else if (status === 'invalid') {
        showError(t('acme.orderInvalid'))
      } else {
        showWarning(t('acme.orderStillProcessing'))
      }
      loadData()
    } catch (error) {
      showError(error.message || t('acme.statusCheckFailed'))
    }
  }
  
  const handleFinalizeOrder = async (order) => {
    try {
      await acmeService.finalizeOrder(order.id)
      showSuccess(t('acme.orderFinalized'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.orderFinalizationFailed'))
    }
  }
  
  const handleDeleteClientOrder = async (order) => {
    const confirmed = await showConfirm(
      t('acme.deleteOrderConfirm'),
      t('acme.deleteOrderConfirmDesc', { domain: order.primary_domain || order.domains?.[0] })
    )
    if (!confirmed) return
    
    try {
      await acmeService.deleteOrder(order.id)
      showSuccess(t('acme.orderDeleted'))
      if (selectedClientOrder?.id === order.id) {
        setSelectedClientOrder(null)
      }
      loadData()
    } catch (error) {
      showError(error.message || t('common.deleteFailed'))
    }
  }
  
  // Download certificate from order
  const handleDownloadCertificate = async (order, format = 'pem', includeKey = false) => {
    if (!order.certificate_id) {
      showError(t('acme.noCertificateYet'))
      return
    }
    try {
      const response = await certificatesService.export(order.certificate_id, format, { 
        include_key: includeKey,
        include_chain: true 
      })
      
      // Create download
      const blob = new Blob([response], { type: 'application/x-pem-file' })
      const domain = order.primary_domain || 'certificate'
      const suffix = includeKey ? '-with-key' : ''
      downloadBlob(blob, `${domain}${suffix}.${format}`)
      
      showSuccess(t('acme.certificateDownloaded'))
    } catch (error) {
      showError(error.message || t('acme.downloadFailed'))
    }
  }
  
  // Navigate to certificate in Certificates page
  const handleViewCertificate = (order) => {
    if (!order.certificate_id) {
      showError(t('acme.noCertificateYet'))
      return
    }
    navigate(`/certificates?item=${order.certificate_id}`)
  }
  
  const handleToggleOrderRenewal = async (order, enabled) => {
    try {
      await acmeService.updateOrder(order.id, { renewal_enabled: enabled })
      showSuccess(t('acme.orderRenewalUpdated'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  // Manual renewal
  const handleRenewCertificate = async (order) => {
    try {
      await acmeService.renewOrder(order.id)
      showSuccess(t('acme.renewalStarted'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.renewalFailed'))
      loadData()  // the order now shows the failure
    }
  }
  
  // =========================================================================
  // DNS Provider Handlers
  // =========================================================================
  
  const handleSaveDnsProvider = async (data) => {
    try {
      if (selectedDnsProvider) {
        await acmeService.updateDnsProvider(selectedDnsProvider.id, data)
        showSuccess(t('acme.dnsProviderUpdated'))
      } else {
        await acmeService.createDnsProvider(data)
        showSuccess(t('acme.dnsProviderCreated'))
      }
      setShowDnsProviderModal(false)
      setSelectedDnsProvider(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed.generic'))
    }
  }
  
  const handleTestDnsProvider = async (provider) => {
    try {
      const result = await acmeService.testDnsProvider(provider.id)
      if (result.data?.success) {
        showSuccess(t('acme.dnsProviderTestSuccess'))
      } else {
        showWarning(result.data?.message || result.message || t('common.dnsProviderTestFailed'))
      }
    } catch (error) {
      showError(error.message || t('common.dnsProviderTestFailed'))
    }
  }
  
  const handleDeleteDnsProvider = async (provider) => {
    const confirmed = await showConfirm(t('acme.confirmDeleteDnsProvider', { name: provider.name }))
    if (!confirmed) return
    try {
      await acmeService.deleteDnsProvider(provider.id)
      showSuccess(t('acme.dnsProviderDeleted'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
    }
  }

  // Account handlers
  const handleCreate = async (data) => {
    try {
      const created = await acmeService.createAccount(data)
      showSuccess(t('acme.accountCreatedSuccess'))
      setShowCreateModal(false)
      loadData()
      selectAccount(created)
    } catch (error) {
      showError(error.message || t('acme.accountCreationFailed'))
    }
  }

  // The account dock has asked (the mockup's acmeDisableDialog): no second question here
  const handleDeactivate = async (id) => {
    try {
      await acmeService.deactivateAccount(id)
      showSuccess(t('acme.accountDeactivatedSuccess'))
      setSelectedAccount(null)
      loadData()
    } catch (error) {
      showError(error.message || t('acme.accountDeactivationFailed'))
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm(t('acme.confirmDelete'), {
      title: t('common.deleteAccount'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await acmeService.deleteAccount(id)
      showSuccess(t('acme.accountDeletedSuccess'))
      setSelectedAccount(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
    }
  }

  // ==========================================================================
  // ACME Domains Handlers
  // ==========================================================================

  const handleCreateDomain = async (data) => {
    try {
      await acmeService.createDomain(data)
      showSuccess(t('acme.domainCreatedSuccess'))
      setShowDomainModal(false)
      setSelectedAcmeDomain(null)
      loadData()
    } catch (error) {
      showError(error.message || t('acme.domainCreateFailed'))
    }
  }

  const handleUpdateDomain = async (data) => {
    if (!selectedAcmeDomain) return
    try {
      await acmeService.updateDomain(selectedAcmeDomain.id, data)
      showSuccess(t('acme.domainUpdatedSuccess'))
      setShowDomainModal(false)
      setSelectedAcmeDomain(null)
      loadData()
    } catch (error) {
      showError(error.message || t('acme.domainUpdateFailed'))
    }
  }

  const handleDeleteDomain = async (domain) => {
    const confirmed = await showConfirm(
      t('acme.confirmDeleteDomain', { domain: domain.domain }),
      {
        title: t('acme.deleteDomain'),
        confirmText: t('common.delete'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      await acmeService.deleteDomain(domain.id)
      showSuccess(t('acme.domainDeletedSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
    }
  }

  const handleTestDomainAccess = async (domain) => {
    try {
      const result = await acmeService.testDomainAccess(domain.domain)
      showSuccess(result.message || t('acme.domainTestSuccess'))
    } catch (error) {
      showError(error.message || t('acme.domainTestFailed'))
    }
  }

  // Local Domain handlers
  const handleCreateLocalDomain = async (data) => {
    try {
      await acmeService.createLocalDomain(data)
      showSuccess(t('acme.domainCreatedSuccess'))
      setShowLocalDomainModal(false)
      setSelectedLocalDomain(null)
      loadData()
    } catch (error) {
      showError(error.message || t('acme.domainCreateFailed'))
    }
  }

  const handleUpdateLocalDomain = async (data) => {
    if (!selectedLocalDomain) return
    try {
      await acmeService.updateLocalDomain(selectedLocalDomain.id, data)
      showSuccess(t('acme.domainUpdatedSuccess'))
      setShowLocalDomainModal(false)
      setSelectedLocalDomain(null)
      loadData()
    } catch (error) {
      showError(error.message || t('acme.domainUpdateFailed'))
    }
  }

  const handleDeleteLocalDomain = async (domain) => {
    const confirmed = await showConfirm(
      t('acme.confirmDeleteDomain', { domain: domain.domain }),
      {
        title: t('acme.deleteDomain'),
        confirmText: t('common.delete'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      await acmeService.deleteLocalDomain(domain.id)
      showSuccess(t('acme.domainDeletedSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
    }
  }

  // EAB credential handlers
  const handleToggleEabRequired = async (value) => {
    try {
      await acmeService.setEabRequired(value)
      setEabRequired(value)
      showSuccess(t('acme.eab.requiredUpdated'))
    } catch (error) {
      showError(error.message || t('acme.eab.requiredUpdateFailed'))
    }
  }

  // ── The accounts of the server (the mockup's list) ──
  // The mockup's chips Actifs and Désactivés always, Révoqués when an account is (Avec échec needs the orders per account, M01)
  const accountStates = ['valid', 'deactivated', ...(accounts.some((a) => a.status === 'revoked') ? ['revoked'] : [])]
  const searchedAccounts = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return accounts.filter((a) => !q || [accountContact(a), a.account_id, a.key_type].some((v) => String(v || '').toLowerCase().includes(q)))
  }, [accounts, searchQuery])
  const shownAccounts = searchedAccounts.filter((a) => !accountState || a.status === accountState)
  // Every page of the server is read (or the list says it is partial): sorted and paged here
  const accountList = useClientList(shownAccounts, {
    resetKey: `${searchQuery}|${accountState}`,
    sortParam: accountSort,
    sorts: {
      name: accountLabel, contact: accountContact, created: (a) => a.created_at && Date.parse(a.created_at),
      state: (a) => (accountStates.includes(a.status) ? accountStates.indexOf(a.status) : null), orders: (a) => a.orders_count ?? 0,
    },
  })
  const accountPill = (a) => <Pill label={t(`acme.accountState.${a.status}`, { defaultValue: stateLabel(t, a.status) })} tone={ACCOUNT_TONES[a.status] || 'muted'} />
  const acmePublicBase = publicBaseUrl(acmeSettings.acme_public_base_url, '/acme')
  const directoryUrl = `${acmePublicBase}/directory`

  const accountsView = (<>
    {accountsPartial && <Notice tone="warn" role="status">{t('acme.accountsListPartial', accountsPartial)}</Notice>}
    <ListView label="ACME" caption={t('acme.accountsCaption')} icon="refresh" list={accountList} nameSort="name" loading={loading}
      filters={{
        views: [{ id: '', label: t('common.all'), count: searchedAccounts.length },
          ...accountStates.map((s) => ({ id: s, label: t(`acme.accountStates.${s}`), count: searchedAccounts.filter((a) => a.status === s).length }))],
        active: accountState, onChange: setAccountState, label: t('acme.filterByState'),
      }}
      toolbar={(
        <Toolbar>
          <SearchField id="acme-account-search" name="q" label={t('acme.searchAccounts')} placeholder={t('acme.searchAccounts')} value={searchQuery} onChange={setSearchQuery} />
          <IconBtn icon="refresh" label={t('common.refresh')} onClick={loadData} />
        </Toolbar>
      )}
      title={accountLabel} status={accountPill} openedId={selectedAccount?.id} onOpen={selectAccount}
      error={loadError && (
        <LoadError id="acme" title={t('messages.errors.loadFailed.acme')} onRetry={loadData} journal={hasPermission('read:audit') ? '/audit' : undefined}
          cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/acme/accounts', message: loadError.message }} />} />
      )}
      columns={[
        { id: 'contact', label: t('acme.contact'), cell: (a) => accountContact(a) || <span className="muted">{t('acme.noContact')}</span>, kind: 'text', priority: 4,
          title: (a) => accountContact(a) || undefined, sort: 'contact' },
        { id: 'created', label: t('acme.createdOn'), labelFull: t('table.fullCreated'), cell: (a) => dateOf(a.created_at, locale) || '—', muted: true, kind: 'fit', priority: 2, labelled: true, sort: 'created' },
        { status: true, sort: 'state' },
        // A count of one or two digits: an abbreviated header where the noun is long, the noun in its title (L8)
        { id: 'orders', label: t('acme.columns.orders'), labelFull: t('acme.orders'), cell: (a) => String(a.orders_count ?? 0), kind: 'number', priority: 3, sort: 'orders' },
      ]}
      empty={accounts.length ? (
        <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => { setSearchQuery(''); setAccountState('') }} />
      ) : (
        <EmptyBlock id="acme" icon="refresh" title={t('acme.emptyAccountsTitle')} text={t('acme.emptyAccountsText')}
          action={{ label: t('acme.copyDirectory'), icon: 'copy', onClick: async () => { if (await copy(directoryUrl)) showSuccess(t('common.copied')) } }} />
      )}
      footer={{ range: t('acme.accountsRange', accountList.counts(accounts.length)) }} />
  </>)

  const views = {
    accounts: <>{accountsView}<SlotDock>{selectedAccount && (
      <AccountDock account={selectedAccount} orders={orders} challenges={challenges} section={activeDetailTab} onSection={setActiveDetailTab}
        onClose={() => setSelectedAccount(null)} onDeactivate={handleDeactivate} onDelete={handleDelete}
        onChanged={(updated) => { setSelectedAccount(updated); loadData() }} />
    )}</SlotDock></>,
    localorders: <LocalOrdersTab linkedOrder={linkedLocalOrder} onCloseLinked={() => setLinkedLocalOrder(null)} onTotal={setLocalOrdersTotal} />,
    localdomains: (
      <LocalDomainsTab localDomains={localDomains} cas={cas} onAdd={() => { setSelectedLocalDomain(null); setShowLocalDomainModal(true) }}
        onEdit={(d) => { setSelectedLocalDomain(d); setShowLocalDomainModal(true) }} onDelete={handleDeleteLocalDomain}
        canWrite={canWrite('acme')} canDelete={canDelete('acme')} />
    ),
    eab: (
      <EabTab eabRequired={eabRequired} onToggleEabRequired={handleToggleEabRequired} showCreateModal={openEabCreate}
        onCloseCreateModal={() => setOpenEabCreate(false)} canWrite={canWrite('acme')} canDelete={canDelete('acme')} onTotal={setEabTotal} />
    ),
    config: loading ? <SkeletonPanel label={t('common.loading')} /> : (
      <ConfigTab acmeSettings={acmeSettings} saved={serverSaved} savedProfiles={savedProfiles} cas={cas} templates={templates}
        updateSetting={updateSetting} onSaveConfig={handleSaveConfig} onReset={() => { setAcmeSettings(serverSaved); setRevokeSuperseded(false) }}
        saving={saving} revokeSuperseded={revokeSuperseded} onRevokeSupersededChange={setRevokeSuperseded}
        onToggleRevokeOnRenewal={handleToggleRevokeOnRenewal} canWrite={canWrite('acme')} />
    ),
    letsencrypt: loading ? <SkeletonPanel label={t('common.loading')} /> : (
      <LetsEncryptTab clientSettings={clientSettings} caAccounts={caAccounts} canWrite={canWrite('acme')} onSaved={(saved = {}) => { setConnectionResult(null); if ('restartRequired' in saved) setDnsRestartRequired(saved.restartRequired); return loadData() }}
        restartRequired={dnsRestartRequired}
        onRegisterProxy={handleRegisterProxy} onUnregisterProxy={handleUnregisterProxy}
        onResetProxyAccount={handleResetProxyAccount} onTestConnection={handleTestConnection} testingConnection={testingConnection} connectionResult={connectionResult} />
    ),
    letsencryptorders: (
      <LetsEncryptOrdersTab clientOrders={clientOrders} partial={clientOrdersPartial} loading={loading} selectedClientOrder={selectedClientOrder}
        onSelectOrder={setSelectedClientOrder} onRefresh={loadData} onCheckOrderStatus={handleCheckOrderStatus} onVerifyChallenge={handleVerifyChallenge}
        onFinalizeOrder={handleFinalizeOrder} onViewCertificate={handleViewCertificate} onDownloadCertificate={handleDownloadCertificate}
        onRenewCertificate={handleRenewCertificate} onDeleteOrder={handleDeleteClientOrder} onToggleRenewal={handleToggleOrderRenewal}
        canDelete={canDelete('acme')} canWrite={canWrite('acme')} />
    ),
    upstream: (
      <CaAccountsManager accounts={caAccounts} proxyPublicBase={publicBaseUrl(clientSettings.acme_proxy_public_base_url, '/acme/proxy')}
        dnsUpdatePort={effectiveDnsUpdatePort(clientSettings)} canWrite={canWrite('acme')} canDelete={canDelete('acme')} createSignal={upstreamCreate}
        onCreate={handleCreateCaAccount} onUpdate={handleUpdateCaAccount} onDelete={handleDeleteCaAccount} onDeactivate={handleDeactivateCaAccount}
        onSetDefault={handleSetDefaultCaAccount} onRegister={handleRegisterCaAccount} />
    ),
    dns: (
      <DnsProvidersTab dnsProviders={dnsProviders} providerTypes={dnsProviderTypes} onAddProvider={() => { setSelectedDnsProvider(null); setShowDnsProviderModal(true) }}
        onEditProvider={(p) => { setSelectedDnsProvider(p); setShowDnsProviderModal(true) }} onTestProvider={handleTestDnsProvider}
        onDeleteProvider={handleDeleteDnsProvider} canWrite={canWrite('acme')} canDelete={canDelete('acme')} />
    ),
    domains: (
      <DomainsTab acmeDomains={acmeDomains} dnsProviders={dnsProviders} cas={cas} onAdd={() => { setSelectedAcmeDomain(null); setShowDomainModal(true) }}
        onEdit={(d) => { setSelectedAcmeDomain(d); setShowDomainModal(true) }} onDelete={handleDeleteDomain} onTest={handleTestDomainAccess}
        canWrite={canWrite('acme')} canDelete={canDelete('acme')} />
    ),
    history: (
      <HistoryTab history={history} total={historyTotal} loading={historyLoading} page={historyPage} perPage={historyPerPage} onPageChange={setHistoryPage}
        onPerPageChange={(v) => { setHistoryPerPage(v); setHistoryPage(1) }} search={historySearch}
        onSearchChange={(v) => { setHistorySearch(v); setHistoryPage(1) }} sort={historySort} onSort={historySortParam.onSort}
        caOptions={historyCAs} exportLoader={exportHistory} onRefresh={loadHistory} filterStatus={historyFilterStatus}
        onFilterStatusChange={(v) => { setHistoryFilterStatus(v); setHistoryPage(1) }} filterCA={historyFilterCA}
        onFilterCAChange={(v) => { setHistoryFilterCA(v); setHistoryPage(1) }} filterSource={historyFilterSource}
        onFilterSourceChange={(v) => { setHistoryFilterSource(v); setHistoryPage(1) }} selectedCert={selectedCert} onSelectCert={setSelectedCert} />
    ),
  }

  const totals = {
    accounts: t('acme.unit', { count: accounts.length }),
    localorders: localOrdersTotal === null ? t('acme.views.localorders') : t('acme.localOrdersCount', { count: localOrdersTotal }),
    localdomains: t('acme.domainsRange', { count: localDomains.length }),
    eab: eabTotal === null ? t('acme.views.eab') : t('acme.eab.totalCount', { count: eabTotal }),
    config: t('protocols.sections', { count: 8 }),
    letsencrypt: t('protocols.sections', { count: 3 }),
    // « 10 sur 10 » only when the list stops short of the server's total
    letsencryptorders: clientOrdersPartial ? t('acme.clientOrdersRange', { shown: clientOrders.length, count: clientOrdersPartial.total }) : t('acme.localOrdersCount', { count: clientOrders.length }),
    upstream: t('acme.upstreamRange', { count: caAccounts.length }),
    dns: t('acme.providersRange', { count: dnsProviders.length }),
    domains: t('acme.domainsRange', { count: acmeDomains.length }),
    history: t('acme.historyTotal', { count: historyTotal }),
  }
  const w = canWrite('acme')
  const create = {
    accounts: w && <Btn tone="primary" icon="plus" id="acme-new-account" onClick={() => setShowCreateModal(true)}>{t('acme.newAccount')}</Btn>,
    localdomains: w && <Btn tone="primary" icon="plus" onClick={() => { setSelectedLocalDomain(null); setShowLocalDomainModal(true) }}>{t('acme.addDomain')}</Btn>,
    eab: w && <Btn tone="primary" icon="plus" onClick={() => setOpenEabCreate(true)}>{t('acme.eab.new')}</Btn>,
    letsencrypt: w && <Btn tone="primary" icon="plus" id="acme-request" onClick={() => setShowRequestModal(true)}>{t('acme.requestCertificate')}</Btn>,
    letsencryptorders: w && <Btn tone="primary" icon="plus" onClick={() => setShowRequestModal(true)}>{t('acme.requestCertificate')}</Btn>,
    upstream: w && <Btn tone="primary" icon="plus" onClick={() => setUpstreamCreate((n) => n + 1)}>{t('acme.addUpstreamCa')}</Btn>,
    dns: w && <Btn tone="primary" icon="plus" onClick={() => { setSelectedDnsProvider(null); setShowDnsProviderModal(true) }}>{t('common.addDnsProvider')}</Btn>,
    domains: w && <Btn tone="primary" icon="plus" onClick={() => { setSelectedAcmeDomain(null); setShowDomainModal(true) }}>{t('acme.addDomain')}</Btn>,
  }[activeTab]
  // A tab counts what its view lists, a bar while it is read
  const counts = { accounts: accounts.length, localdomains: localDomains.length, letsencryptorders: clientOrders.length, upstream: caAccounts.length, dns: dnsProviders.length, domains: acmeDomains.length }
  const paged = { history: historyLoading ? null : historyTotal, localorders: localOrdersTotal, eab: eabTotal }
  const option = (v) => ({ value: v, label: t(`acme.views.${v}`), count: v in paged ? paged[v] : v in counts ? (loading ? null : counts[v]) : undefined })

  return (
    <DockSlotProvider>
      <Zone dock={<DockSlot />}>
        <PageHead title="ACME" total={totals[activeTab]} intent={t('shell.moduleDesc.acme')}
          actions={<>
            <Btn icon="copy" id="acme-copy-directory" onClick={async () => { if (await copy(directoryUrl)) showSuccess(t('common.copied')) }}>{t('acme.copyDirectory')}</Btn>
            {create || null}
          </>} />
        <ViewSwitch id="acme-view" label={t('protocols.view')} value={activeTab} onChange={setActiveTab}
          groups={[
            { label: t('acme.groups.localAcme'), options: SERVER_VIEWS.map(option) },
            { label: t('acme.groups.client'), options: CLIENT_VIEWS.map(option) },
            { label: t('acme.groups.history'), options: [option('history')] },
          ]}>
          {views[activeTab]}
        </ViewSwitch>
        {/* The phone hides the head's secondary buttons: the directory URL stays one tap away under the view */}
        <p className="phone-only">
          <Btn icon="copy" id="acme-copy-directory-phone" onClick={async () => { if (await copy(directoryUrl)) showSuccess(t('common.copied')) }}>{t('acme.copyDirectory')}</Btn>
        </p>
      </Zone>
      {/* Create Account Modal */}
      <Modal open={showCreateModal} onClose={() => setShowCreateModal(false)} title={t('acme.createAccountTitle')} size="sm" testId="acme-account-dialog">
        <CreateAccountForm onSubmit={handleCreate} onCancel={() => setShowCreateModal(false)} />
      </Modal>

      {/* Request Certificate Modal: gate on clientSettings being loaded
          so the form's useState captures the configured default env (#26). */}
      <Modal open={showRequestModal && clientSettings.environment != null} onClose={() => setShowRequestModal(false)}
        title={t('acme.requestCertificateTitle')} size="lg" testId="acme-request-dialog">
        <RequestCertificateForm
          onSubmit={handleRequestCertificate}
          onPreflight={handlePreflight}
          onCancel={() => setShowRequestModal(false)}
          dnsProviders={dnsProviders}
          caAccounts={caAccounts}
          defaultEnvironment={clientSettings.environment || 'staging'}
          defaultEmail={clientSettings.email || ''}
          defaultKeyType={clientSettings.key_type}
          preflightLoading={preflightLoading}
        />
      </Modal>

      <Modal open={!!preflightResult} onClose={() => setPreflightResult(null)} size="lg" testId="acme-preflight-dialog"
        title={preflightResult?.ok ? t('acme.preflightPassedTitle') : t('acme.preflightFailedTitle')} subtitle={t('acme.preflightStagingNote')}>
        {preflightResult && (
          <>
            <RecordList>
              {(preflightResult.steps || []).map((step) => (
                <RecordRow key={step.name} title={step.label} meta={step.detail || undefined}
                  badge={<Pill tone={step.status === 'pass' ? 'good' : 'bad'} label={step.status === 'pass' ? t('common.states.ok') : t('common.states.failed')} />}
                  extra={step.data?.txt_records?.length > 0 && step.data.txt_records.map((rec) => (
                    <span key={rec.name} className="rl-meta mono">{rec.name}<br />{rec.value}</span>
                  ))} />
              ))}
            </RecordList>
            {(preflightResult.txt_records || []).length > 0 && (
              <section style={{ marginTop: 18 }}>
                <h3 className="section-title">{t('acme.preflightTxtRecords')}</h3>
                <RecordList>
                  {preflightResult.txt_records.map((rec) => (
                    <RecordRow key={rec.name} title={<span className="mono">{rec.name}</span>} meta={<span className="mono">{rec.value}</span>} />
                  ))}
                </RecordList>
              </section>
            )}
            <div className="modal-actions">
              <button type="button" className="btn primary" data-action="close-modal" data-write="false" onClick={() => setPreflightResult(null)}>{t('common.close')}</button>
            </div>
          </>
        )}
      </Modal>

      {/* DNS Provider Modal */}
      <Modal open={showDnsProviderModal} onClose={() => { setShowDnsProviderModal(false); setSelectedDnsProvider(null) }}
        title={selectedDnsProvider ? t('acme.editDnsProvider') : t('common.addDnsProvider')} testId="acme-dns-dialog">
        <DnsProviderForm
          provider={selectedDnsProvider}
          providerTypes={dnsProviderTypes}
          onSubmit={handleSaveDnsProvider}
          onCancel={() => { setShowDnsProviderModal(false); setSelectedDnsProvider(null) }}
        />
      </Modal>

      {/* Domain Modal */}
      <Modal open={showDomainModal} onClose={() => { setShowDomainModal(false); setSelectedAcmeDomain(null) }}
        title={selectedAcmeDomain ? t('acme.editDomain') : t('acme.addDomain')} testId="acme-domain-dialog">
        <DomainForm
          domain={selectedAcmeDomain}
          dnsProviders={dnsProviders}
          cas={cas}
          onSubmit={selectedAcmeDomain ? handleUpdateDomain : handleCreateDomain}
          onCancel={() => { setShowDomainModal(false); setSelectedAcmeDomain(null) }}
        />
      </Modal>

      {/* Local Domain Modal */}
      <Modal open={showLocalDomainModal} onClose={() => { setShowLocalDomainModal(false); setSelectedLocalDomain(null) }}
        title={selectedLocalDomain ? t('acme.editDomain') : t('acme.addDomain')} size="sm" testId="acme-local-domain-dialog">
        <LocalDomainForm
          domain={selectedLocalDomain}
          cas={cas}
          onSubmit={selectedLocalDomain ? handleUpdateLocalDomain : handleCreateLocalDomain}
          onCancel={() => { setShowLocalDomainModal(false); setSelectedLocalDomain(null) }}
        />
      </Modal>

      {/* Revoke superseded confirmation */}
      <Modal open={showRevokeConfirm} onClose={() => setShowRevokeConfirm(false)} title={t('acme.revokeSupersededConfirmTitle')} size="sm" testId="acme-revoke-superseded-dialog">
        <div className="notice warn"><Icon name="warning" /><span><strong>{t('common.warning')}</strong> {t('acme.revokeSupersededConfirmDesc', { count: acmeSettings.superseded_count })}</span></div>
        <div className="modal-actions">
          <button type="button" className="btn" data-action="close-modal" data-autofocus="" onClick={() => setShowRevokeConfirm(false)}>{t('common.cancel')}</button>
          <button type="button" className="btn danger" data-write="" onClick={handleConfirmRevokeSuperseded}>
            {t('acme.revokeSupersededConfirmAction', { count: acmeSettings.superseded_count })}
          </button>
        </div>
      </Modal>
    </DockSlotProvider>
  )
}
