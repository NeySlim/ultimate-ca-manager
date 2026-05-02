import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Key, Plus, CheckCircle, ShieldCheck,
  Globe, Lightning, Database, Gear, ClockCounterClockwise,
  ArrowsClockwise, Warning, LockKey, GlobeHemisphereWest, PlugsConnected
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Badge, Card, Modal, HelpCard,
  LoadingSpinner, StatusIndicator,
  CompactStats, CompactHeader
} from '../components'
import { acmeService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, downloadBlob } from '../lib/utils'
import AccountDetailPanel from './acme/AccountDetailPanel'
import LetsEncryptTab from './acme/LetsEncryptTab'
import ConfigTab from './acme/ConfigTab'
import DnsProvidersTab from './acme/DnsProvidersTab'
import DomainsTab from './acme/DomainsTab'
import LocalDomainsTab from './acme/LocalDomainsTab'
import AccountsTab from './acme/AccountsTab'
import EabTab from './acme/EabTab'
import HistoryTab from './acme/HistoryTab'
import CertDetailPanel from './acme/CertDetailPanel'
import OrderDetailPanel from './acme/OrderDetailPanel'
import CreateAccountForm from './acme/CreateAccountForm'
import RequestCertificateForm from './acme/RequestCertificateForm'
import DnsProviderForm from './acme/DnsProviderForm'
import DomainForm from './acme/DomainForm'
import LocalDomainForm from './acme/LocalDomainForm'

export default function ACMEPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  const { canWrite, canDelete } = usePermission()

  // Data states - ACME Server
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [selectedCert, setSelectedCert] = useState(null)
  const [orders, setOrders] = useState([])
  const [challenges, setChallenges] = useState([])
  const [acmeSettings, setAcmeSettings] = useState({})
  const [cas, setCas] = useState([])
  const [history, setHistory] = useState([])

  // Data states - Let's Encrypt Client
  const [clientOrders, setClientOrders] = useState([])
  const [clientSettings, setClientSettings] = useState({})
  const [dnsProviders, setDnsProviders] = useState([])
  const [dnsProviderTypes, setDnsProviderTypes] = useState([])
  const [acmeDomains, setAcmeDomains] = useState([])
  const [localDomains, setLocalDomains] = useState([])
  const [selectedClientOrder, setSelectedClientOrder] = useState(null)
  const [selectedDnsProvider, setSelectedDnsProvider] = useState(null)
  const [selectedAcmeDomain, setSelectedAcmeDomain] = useState(null)

  // UI states
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('letsencrypt')
  const [activeDetailTab, setActiveDetailTab] = useState('account')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showRequestModal, setShowRequestModal] = useState(false)
  const [showDnsProviderModal, setShowDnsProviderModal] = useState(false)
  const [showDomainModal, setShowDomainModal] = useState(false)
  const [showLocalDomainModal, setShowLocalDomainModal] = useState(false)
  const [selectedLocalDomain, setSelectedLocalDomain] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [revokeSuperseded, setRevokeSuperseded] = useState(false)
  const [eabHmacInput, setEabHmacInput] = useState(null)
  const [showRevokeConfirm, setShowRevokeConfirm] = useState(false)
  const [proxyEmail, setProxyEmail] = useState('')
  const [openEabCreate, setOpenEabCreate] = useState(false)

  // Local state for text inputs (saved on blur, not on every keystroke)
  const [localContactEmail, setLocalContactEmail] = useState('')
  const [localDirectoryUrl, setLocalDirectoryUrl] = useState('')
  const [localEabKid, setLocalEabKid] = useState('')
  const [localProxyUpstreamUrl, setLocalProxyUpstreamUrl] = useState('')
  const [localProxyEabKid, setLocalProxyEabKid] = useState('')
  const [proxyEabHmacInput, setProxyEabHmacInput] = useState(null)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionResult, setConnectionResult] = useState(null)

  // History filters
  const [historyFilterStatus, setHistoryFilterStatus] = useState([])
  const [historyFilterCA, setHistoryFilterCA] = useState('')
  const [historyFilterSource, setHistoryFilterSource] = useState('')

  // EAB — only required flag stays in parent; credentials state lives in EabTab
  const [eabRequired, setEabRequired] = useState(false)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [accountsRes, settingsRes, casRes, historyRes, clientOrdersRes, clientSettingsRes, dnsProvidersRes, dnsTypesRes, domainsRes, localDomainsRes, eabReqRes] = await Promise.all([
        acmeService.getAccounts(),
        acmeService.getSettings(),
        casService.getAll(),
        acmeService.getHistory(),
        acmeService.getClientOrders().catch(() => ({ data: [] })),
        acmeService.getClientSettings().catch(() => ({ data: {} })),
        acmeService.getDnsProviders().catch(() => ({ data: [] })),
        acmeService.getDnsProviderTypes().catch(() => ({ data: [] })),
        acmeService.getDomains().catch(() => ({ data: [] })),
        acmeService.getLocalDomains().catch(() => ({ data: [] })),
        acmeService.getEabRequired().catch(() => ({ data: { eab_required: false } }))
      ])
      setAccounts(accountsRes.data || accountsRes.accounts || [])
      setAcmeSettings(settingsRes.data || settingsRes || {})
      setCas(casRes.data || casRes.cas || [])
      setHistory(historyRes.data || [])
      setClientOrders(clientOrdersRes.data || [])
      setClientSettings(clientSettingsRes.data || {})
      setEabHmacInput(null)
      setEabRequired(!!(eabReqRes.data?.eab_required))
      
      // Sync local text input state from loaded settings
      const cs = clientSettingsRes.data || {}
      setLocalContactEmail(cs.email || '')
      setLocalDirectoryUrl(cs.directory_url || '')
      setLocalEabKid(cs.eab_kid || '')
      setLocalProxyUpstreamUrl(cs.proxy_upstream_url || '')
      setLocalProxyEabKid(cs.proxy_eab_kid || '')
      
      setDnsProviders(dnsProvidersRes.data || [])
      setDnsProviderTypes(dnsTypesRes.data || [])
      setAcmeDomains(domainsRes.data || [])
      setLocalDomains(localDomainsRes.data || [])
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.acme'))
    } finally {
      setLoading(false)
    }
  }

  // Select an account and load its details
  const selectAccount = useCallback(async (account) => {
    try {
      const [accountRes, ordersRes, challengesRes] = await Promise.all([
        acmeService.getAccountById(account.id),
        acmeService.getOrders(account.id),
        acmeService.getChallenges(account.id),
      ])
      setSelectedAccount(accountRes.data || accountRes)
      setOrders(ordersRes.data?.orders || ordersRes.orders || [])
      setChallenges(challengesRes.data?.challenges || challengesRes.challenges || [])
      setActiveDetailTab('account')
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
    }
  }, [showError])

  // Settings handlers
  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      await acmeService.updateSettings(acmeSettings)
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

  const handleRegisterProxy = async () => {
    if (!proxyEmail) {
      showError(t('messages.errors.validation.requiredField'))
      return
    }
    try {
      await acmeService.registerProxy(proxyEmail)
      showSuccess(t('acme.proxyRegisteredSuccess'))
      setProxyEmail('')
      loadData()
    } catch (error) {
      showError(error.message || t('acme.proxyRegistrationFailed'))
    }
  }

  const handleUnregisterProxy = async () => {
    const confirmed = await showConfirm(t('acme.confirmUnregisterProxy'))
    if (!confirmed) return
    try {
      await acmeService.unregisterProxy()
      showSuccess(t('acme.proxyUnregisteredSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.proxyUnregistrationFailed'))
    }
  }

  const handleProxyModeChange = async (mode) => {
    try {
      setClientSettings(prev => ({ ...prev, proxy_upstream_mode: mode, proxy_account_registered: false, proxy_account_url: null, proxy_upstream_url: '' }))
      setConnectionResult(null)
      setLocalProxyUpstreamUrl('')
      await acmeService.updateClientSettings({ proxy_upstream_mode: mode })
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
      loadData()
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
      const url = clientSettings.proxy_upstream_url || localProxyUpstreamUrl
      const res = await acmeService.testProxyConnection(url || undefined)
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
  
  const handleUpdateClientSetting = async (key, value) => {
    try {
      const updated = { ...clientSettings, [key]: value }
      setClientSettings(updated)
      await acmeService.updateClientSettings({ [key]: value })
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
      loadData() // Revert on error
    }
  }

  // Save text input on blur (avoids saving on every keystroke)
  const handleBlurSave = async (key, value, localSetter) => {
    // Only save if value actually changed
    if (value === (clientSettings[key] || '')) return
    try {
      await acmeService.updateClientSettings({ [key]: value })
      setClientSettings(prev => ({ ...prev, [key]: value }))
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
      // Revert local state on error
      localSetter(clientSettings[key] || '')
    }
  }

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
      if (result.data?.challenge_warning) {
        showWarning(result.data.challenge_warning)
      } else {
        showSuccess(t('acme.certificateRequestCreated'))
      }
      setShowRequestModal(false)
      loadData()
      if (result.data) {
        setSelectedClientOrder(result.data)
      }
    } catch (error) {
      showError(error.message || t('acme.certificateRequestFailed'))
    }
  }
  
  const handleVerifyChallenge = async (order) => {
    try {
      const result = await acmeService.verifyChallenge(order.id)
      const updatedOrder = result.data?.order
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
    window.location.href = `/certificates?id=${order.certificate_id}`
  }
  
  // Manual renewal
  const handleRenewCertificate = async (order) => {
    try {
      await acmeService.renewOrder(order.id)
      showSuccess(t('acme.renewalStarted'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.renewalFailed'))
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

  const handleDeactivate = async (id) => {
    const confirmed = await showConfirm(t('acme.confirmDeactivate'), {
      title: t('common.deactivateAccount'),
      confirmText: t('common.deactivate'),
      variant: 'danger'
    })
    if (!confirmed) return
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

  // Computed stats
  const stats = useMemo(() => ({
    total: accounts.length,
    active: accounts.filter(a => a.status === 'valid').length,
    orders: orders.length,
    pending: challenges.filter(c => c.status === 'pending').length
  }), [accounts, orders, challenges])

  // Filtered accounts
  const filteredAccounts = useMemo(() => {
    if (!searchQuery) return accounts
    const q = searchQuery.toLowerCase()
    return accounts.filter(a => 
      a.email?.toLowerCase().includes(q) ||
      a.contact?.[0]?.toLowerCase().includes(q)
    )
  }, [accounts, searchQuery])

  // Table columns for accounts
  const accountColumns = useMemo(() => [
    {
      key: 'email',
      header: t('common.email'),
      priority: 1,
      render: (_, row) => (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
            <Key size={14} weight="duotone" />
          </div>
          <span className="font-medium text-text-primary">
            {row.contact?.[0]?.replace('mailto:', '') || row.email || `Account #${row.id}`}
          </span>
        </div>
      ),
      mobileRender: (_, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
              <Key size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">
              {row.contact?.[0]?.replace('mailto:', '') || row.email || `Account #${row.id}`}
            </span>
          </div>
          <Badge variant={row.status === 'valid' ? 'success' : 'orange'} size="sm" dot>
            {row.status}
          </Badge>
        </div>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 2,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val === 'valid' ? 'success' : 'orange'} size="sm" dot pulse={val === 'valid'}>
          {val === 'valid' && <CheckCircle size={10} weight="fill" />}
          {val}
        </Badge>
      )
    },
    {
      key: 'created_at',
      header: t('common.created'),
      priority: 3,
      hideOnMobile: true,
      render: (val) => formatDate(val),
      mobileRender: (val) => (
        <div className="text-xs text-text-tertiary">
          {t('common.created')}: <span className="text-text-secondary">{formatDate(val)}</span>
        </div>
      )
    }
  ], [t])

  // Main tabs
  const tabs = [
    { id: 'letsencrypt', label: t('acme.letsEncrypt'), icon: Globe },
    { id: 'dns', label: t('acme.dnsProviders'), icon: PlugsConnected, count: dnsProviders.length },
    { id: 'domains', label: t('acme.domains'), icon: GlobeHemisphereWest, count: acmeDomains.length },
    { id: 'config', label: t('acme.server'), icon: Gear },
    { id: 'localdomains', label: t('acme.localDomains'), icon: GlobeHemisphereWest, count: localDomains.length },
    { id: 'accounts', label: t('acme.accounts'), icon: Key, count: accounts.length },
    { id: 'eab', label: t('acme.eab.tab'), icon: LockKey },
    { id: 'history', label: t('common.history'), icon: ClockCounterClockwise, count: history.length }
  ]

  // Detail tabs (when account selected)
  const detailTabs = [
    { id: 'account', label: t('common.details'), icon: Key },
    { id: 'orders', label: t('acme.orders'), icon: Globe, count: orders.length },
    { id: 'challenges', label: t('common.challenges'), icon: ShieldCheck, count: challenges.length }
  ]

  // Header actions
  const headerActions = (
    <>
      <Button type="button" variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
        {t('common.refresh')}
      </Button>
      {activeTab === 'accounts' && canWrite('acme') && (
        <Button type="button" size="sm" onClick={() => setShowCreateModal(true)}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.newAccount')}</span>
        </Button>
      )}
      {activeTab === 'domains' && canWrite('acme') && (
        <Button type="button" size="sm" onClick={() => { setSelectedAcmeDomain(null); setShowDomainModal(true) }}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.addDomain')}</span>
        </Button>
      )}
      {activeTab === 'localdomains' && canWrite('acme') && (
        <Button type="button" size="sm" onClick={() => { setSelectedLocalDomain(null); setShowLocalDomainModal(true) }}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.addDomain')}</span>
        </Button>
      )}
      {activeTab === 'eab' && canWrite('acme') && (
        <Button type="button" size="sm" onClick={() => setOpenEabCreate(true)}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.eab.new')}</span>
        </Button>
      )}
    </>
  )

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary-op5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          {t('acme.statistics')}
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
            <p className="text-xs text-text-secondary">{t('acme.accounts')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-success-text">{stats.active}</p>
            <p className="text-xs text-text-secondary">{t('common.active')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-accent-primary">{stats.orders}</p>
            <p className="text-xs text-text-secondary">{t('acme.orders')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-warning-text">{stats.pending}</p>
            <p className="text-xs text-text-secondary">{t('common.pending')}</p>
          </div>
        </div>
      </Card>

      <Card className={`p-4 space-y-3 ${acmeSettings.enabled ? 'stat-card-success' : 'stat-card-warning'}`}>
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Lightning size={16} className="text-accent-primary" />
          {t('acme.serverStatus')}
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{t('acme.acmeServer')}</span>
            <StatusIndicator status={acmeSettings.enabled ? 'success' : 'warning'}>
              {acmeSettings.enabled ? t('common.enabled') : t('common.disabled')}
            </StatusIndicator>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        <HelpCard variant="info" title={t('common.aboutAcme')}>
          {t('acme.aboutAcmeInfo')}
        </HelpCard>

        <HelpCard variant="info" title={t('acme.localDomains')}>
          {t('acme.localDomainsHelp')}
        </HelpCard>

        <HelpCard variant="warning" title={t('common.warning')}>
          {t('acme.accountSecurityWarning')}
        </HelpCard>
      </div>
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title={t('acme.title')}
        subtitle={t('acme.subtitle', { count: accounts.length })}
        icon={Lightning}
        stats={[
          { icon: Key, label: t('acme.accounts'), value: accounts.length },
          { icon: CheckCircle, label: t('common.active'), value: stats.active, variant: 'success' },
          { icon: ClockCounterClockwise, label: t('common.certificates'), value: history.length, variant: 'primary' },
        ]}
        tabs={tabs}
        activeTab={activeTab}
        tabLayout="sidebar"
        sidebarContentClass=""
        tabGroups={[
          { labelKey: 'acme.groups.letsEncrypt', tabs: ['letsencrypt', 'dns', 'domains'], color: 'icon-bg-emerald' },
          { labelKey: 'acme.groups.localAcme', tabs: ['config', 'localdomains', 'accounts', 'eab'], color: 'icon-bg-violet' },
          { labelKey: 'acme.groups.history', tabs: ['history'], color: 'icon-bg-blue' },
        ]}
        onTabChange={(tab) => {
          setActiveTab(tab)
          // Clear selections when changing tabs
          setSelectedClientOrder(null)
          setSelectedAccount(null)
          setSelectedCert(null)
        }}
        actions={headerActions}
        helpPageKey="acme"
        
        // Split view for letsencrypt, accounts and history tabs
        splitView={activeTab === 'letsencrypt' || activeTab === 'accounts' || activeTab === 'history'}
        slideOverOpen={
          activeTab === 'letsencrypt' ? !!selectedClientOrder :
          activeTab === 'accounts' ? !!selectedAccount : 
          !!selectedCert
        }
        slideOverTitle={
          activeTab === 'letsencrypt'
            ? (selectedClientOrder?.primary_domain || t('acme.orderDetails'))
            : activeTab === 'accounts' 
              ? (selectedAccount?.email || t('common.details'))
              : (selectedCert?.common_name || t('common.certificateDetails'))
        }
        slideOverContent={
          activeTab === 'letsencrypt' ? (
            <OrderDetailPanel
              order={selectedClientOrder}
              onDownloadCert={handleDownloadCertificate}
              onViewCertificate={handleViewCertificate}
              onRenewCertificate={handleRenewCertificate}
              onVerifyChallenge={handleVerifyChallenge}
              onFinalizeOrder={handleFinalizeOrder}
              onDeleteOrder={handleDeleteClientOrder}
            />
          ) : activeTab === 'accounts' ? (
            <AccountDetailPanel
              account={selectedAccount}
              detailTabs={detailTabs}
              activeDetailTab={activeDetailTab}
              onDeactivate={handleDeactivate}
              onDelete={handleDelete}
              onDetailTabChange={setActiveDetailTab}
              orders={orders}
              challenges={challenges}
            />
          ) : (
            <CertDetailPanel cert={selectedCert} />
          )
        }
        onSlideOverClose={() => {
          if (activeTab === 'letsencrypt') {
            setSelectedClientOrder(null)
          } else if (activeTab === 'accounts') {
            setSelectedAccount(null)
          } else {
            setSelectedCert(null)
          }
        }}
      >
        {activeTab === 'letsencrypt' && (
          <LetsEncryptTab
            clientOrders={clientOrders}
            selectedClientOrder={selectedClientOrder}
            onSelectOrder={setSelectedClientOrder}
            clientSettings={clientSettings}
            localContactEmail={localContactEmail}
            onLocalContactEmailChange={setLocalContactEmail}
            localDirectoryUrl={localDirectoryUrl}
            onLocalDirectoryUrlChange={setLocalDirectoryUrl}
            localEabKid={localEabKid}
            onLocalEabKidChange={setLocalEabKid}
            localProxyUpstreamUrl={localProxyUpstreamUrl}
            onLocalProxyUpstreamUrlChange={setLocalProxyUpstreamUrl}
            localProxyEabKid={localProxyEabKid}
            onLocalProxyEabKidChange={setLocalProxyEabKid}
            proxyEabHmacInput={proxyEabHmacInput}
            onProxyEabHmacInputChange={setProxyEabHmacInput}
            eabHmacInput={eabHmacInput}
            onEabHmacInputChange={setEabHmacInput}
            proxyEmail={proxyEmail}
            onProxyEmailChange={setProxyEmail}
            testingConnection={testingConnection}
            connectionResult={connectionResult}
            onBlurSave={handleBlurSave}
            onUpdateClientSetting={handleUpdateClientSetting}
            onRegisterProxy={handleRegisterProxy}
            onUnregisterProxy={handleUnregisterProxy}
            onProxyModeChange={handleProxyModeChange}
            onResetProxyAccount={handleResetProxyAccount}
            onTestConnection={handleTestConnection}
            onRequestCertificate={() => setShowRequestModal(true)}
            onRefresh={loadData}
            onCheckOrderStatus={handleCheckOrderStatus}
            onVerifyChallenge={handleVerifyChallenge}
            onFinalizeOrder={handleFinalizeOrder}
            onViewCertificate={handleViewCertificate}
            onDownloadCertificate={handleDownloadCertificate}
            onRenewCertificate={handleRenewCertificate}
            onDeleteOrder={handleDeleteClientOrder}
            canWrite={canWrite('acme')}
            canDelete={canDelete('acme')}
          />
        )}
        {activeTab === 'dns' && (
          <DnsProvidersTab
            dnsProviders={dnsProviders}
            onAddProvider={() => { setSelectedDnsProvider(null); setShowDnsProviderModal(true) }}
            onEditProvider={(p) => { setSelectedDnsProvider(p); setShowDnsProviderModal(true) }}
            onTestProvider={handleTestDnsProvider}
            onDeleteProvider={handleDeleteDnsProvider}
            canWrite={canWrite('acme')}
            canDelete={canDelete('acme')}
          />
        )}
        {activeTab === 'domains' && (
          <DomainsTab
            acmeDomains={acmeDomains}
            dnsProviders={dnsProviders}
            cas={cas}
            onAdd={() => { setSelectedAcmeDomain(null); setShowDomainModal(true) }}
            onEdit={(d) => { setSelectedAcmeDomain(d); setShowDomainModal(true) }}
            onDelete={handleDeleteDomain}
            onTest={handleTestDomainAccess}
            canWrite={canWrite('acme')}
            canDelete={canDelete('acme')}
          />
        )}
        {activeTab === 'config' && (
          <ConfigTab
            acmeSettings={acmeSettings}
            updateSetting={updateSetting}
            onSaveConfig={handleSaveConfig}
            saving={saving}
            revokeSuperseded={revokeSuperseded}
            onRevokeSupersededChange={setRevokeSuperseded}
            onToggleRevokeOnRenewal={handleToggleRevokeOnRenewal}
            canWrite={canWrite('acme')}
          />
        )}
        {activeTab === 'localdomains' && (
          <LocalDomainsTab
            localDomains={localDomains}
            cas={cas}
            onAdd={() => { setSelectedLocalDomain(null); setShowLocalDomainModal(true) }}
            onEdit={(d) => { setSelectedLocalDomain(d); setShowLocalDomainModal(true) }}
            onDelete={handleDeleteLocalDomain}
            canWrite={canWrite('acme')}
            canDelete={canDelete('acme')}
          />
        )}
        {activeTab === 'accounts' && (
          <AccountsTab
            accounts={filteredAccounts}
            selectedAccount={selectedAccount}
            onSelectAccount={selectAccount}
            searchQuery={searchQuery}
            onSearch={setSearchQuery}
            columns={accountColumns}
            page={page}
            perPage={perPage}
            onPageChange={setPage}
            onPerPageChange={setPerPage}
            canWrite={canWrite('acme')}
            onShowCreateModal={() => setShowCreateModal(true)}
          />
        )}
        {activeTab === 'eab' && (
          <EabTab
            eabRequired={eabRequired}
            onToggleEabRequired={handleToggleEabRequired}
            showCreateModal={openEabCreate}
            onCloseCreateModal={() => setOpenEabCreate(false)}
            canWrite={canWrite('acme')}
            canDelete={canDelete('acme')}
          />
        )}
        {activeTab === 'history' && (
          <HistoryTab
            history={history}
            filterStatus={historyFilterStatus}
            onFilterStatusChange={setHistoryFilterStatus}
            filterCA={historyFilterCA}
            onFilterCAChange={setHistoryFilterCA}
            filterSource={historyFilterSource}
            onFilterSourceChange={setHistoryFilterSource}
            selectedCert={selectedCert}
            onSelectCert={setSelectedCert}
          />
        )}
      </ResponsiveLayout>

      {/* Create Account Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title={t('acme.createAccountTitle')}
      >
        <CreateAccountForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreateModal(false)}
        />
      </Modal>

      {/* Request Certificate Modal */}
      <Modal
        open={showRequestModal}
        onClose={() => setShowRequestModal(false)}
        title={t('acme.requestCertificateTitle')}
        size="lg"
      >
        <RequestCertificateForm
          onSubmit={handleRequestCertificate}
          onCancel={() => setShowRequestModal(false)}
          dnsProviders={dnsProviders}
          defaultEnvironment={clientSettings.default_environment || 'staging'}
          defaultEmail={clientSettings.contact_email || ''}
        />
      </Modal>
      
      {/* DNS Provider Modal */}
      <Modal
        open={showDnsProviderModal}
        onClose={() => { setShowDnsProviderModal(false); setSelectedDnsProvider(null) }}
        title={selectedDnsProvider ? t('acme.editDnsProvider') : t('common.addDnsProvider')}
      >
        <DnsProviderForm
          provider={selectedDnsProvider}
          providerTypes={dnsProviderTypes}
          onSubmit={handleSaveDnsProvider}
          onCancel={() => { setShowDnsProviderModal(false); setSelectedDnsProvider(null) }}
        />
      </Modal>

      {/* Domain Modal */}
      <Modal
        open={showDomainModal}
        onClose={() => { setShowDomainModal(false); setSelectedAcmeDomain(null) }}
        title={selectedAcmeDomain ? t('acme.editDomain') : t('acme.addDomain')}
      >
        <DomainForm
          domain={selectedAcmeDomain}
          dnsProviders={dnsProviders}
          cas={cas}
          onSubmit={selectedAcmeDomain ? handleUpdateDomain : handleCreateDomain}
          onCancel={() => { setShowDomainModal(false); setSelectedAcmeDomain(null) }}
        />
      </Modal>

      {/* Local Domain Modal */}
      <Modal
        open={showLocalDomainModal}
        onClose={() => { setShowLocalDomainModal(false); setSelectedLocalDomain(null) }}
        title={selectedLocalDomain ? t('acme.editDomain') : t('acme.addDomain')}
      >
        <LocalDomainForm
          domain={selectedLocalDomain}
          cas={cas}
          onSubmit={selectedLocalDomain ? handleUpdateLocalDomain : handleCreateLocalDomain}
          onCancel={() => { setShowLocalDomainModal(false); setSelectedLocalDomain(null) }}
        />
      </Modal>

      {/* Revoke superseded confirmation */}
      <Modal
        open={showRevokeConfirm}
        onClose={() => setShowRevokeConfirm(false)}
        title={t('acme.revokeSupersededConfirmTitle')}
      >
        <div className="p-4 space-y-4">
          <div className="flex items-start gap-3 p-3 rounded-lg bg-accent-warning-op10 border border-accent-warning-op30">
            <Warning size={20} className="text-accent-warning flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-accent-warning">{t('common.warning')}</p>
              <p className="text-text-secondary mt-1">
                {t('acme.revokeSupersededConfirmDesc', { count: acmeSettings.superseded_count })}
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setShowRevokeConfirm(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" variant="danger" onClick={handleConfirmRevokeSuperseded}>
              {t('acme.revokeSupersededConfirmAction', { count: acmeSettings.superseded_count })}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

