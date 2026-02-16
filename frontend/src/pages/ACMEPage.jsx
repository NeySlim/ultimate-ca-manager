/**
 * ACME Page - Refactored with ResponsiveLayout
 * ACME Protocol management for automated certificate issuance
 * 
 * Layout:
 * - Horizontal tabs: Configuration | Accounts
 * - Desktop: Split view with accounts list + detail panel
 * - Mobile: Full-screen navigation
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Key, Plus, Trash, CheckCircle, XCircle, FloppyDisk, ShieldCheck, 
  Globe, Lightning, Database, Gear, ClockCounterClockwise, Certificate, Clock,
  ArrowsClockwise, CloudArrowUp, PlugsConnected, Play, Warning,
  DownloadSimple, Eye, LockKey, GlobeHemisphereWest, PencilSimple, MagnifyingGlass
} from '@phosphor-icons/react'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Badge, Card, Input, Modal, Select, HelpCard,
  LoadingSpinner, StatusIndicator,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { acmeService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { formatDate, cn } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'
import { ProviderIcon, getProviderColor } from '../components/ProviderIcons'

export default function ACMEPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  
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
  const [showRevokeConfirm, setShowRevokeConfirm] = useState(false)
  const [proxyEmail, setProxyEmail] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // History filters
  const [historyFilterStatus, setHistoryFilterStatus] = useState('')
  const [historyFilterCA, setHistoryFilterCA] = useState('')
  const [historyFilterSource, setHistoryFilterSource] = useState('')

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [accountsRes, settingsRes, casRes, historyRes, clientOrdersRes, clientSettingsRes, dnsProvidersRes, dnsTypesRes, domainsRes, localDomainsRes] = await Promise.all([
        acmeService.getAccounts(),
        acmeService.getSettings(),
        casService.getAll(),
        acmeService.getHistory(),
        acmeService.getClientOrders().catch(() => ({ data: [] })),
        acmeService.getClientSettings().catch(() => ({ data: {} })),
        acmeService.getDnsProviders().catch(() => ({ data: [] })),
        acmeService.getDnsProviderTypes().catch(() => ({ data: [] })),
        acmeService.getDomains().catch(() => ({ data: [] })),
        acmeService.getLocalDomains().catch(() => ({ data: [] }))
      ])
      setAccounts(accountsRes.data || accountsRes.accounts || [])
      setAcmeSettings(settingsRes.data || settingsRes || {})
      setCas(casRes.data || casRes.cas || [])
      setHistory(historyRes.data || [])
      setClientOrders(clientOrdersRes.data || [])
      setClientSettings(clientSettingsRes.data || {})
      setDnsProviders(dnsProvidersRes.data || [])
      setDnsProviderTypes(dnsTypesRes.data || [])
      setAcmeDomains(domainsRes.data || [])
      setLocalDomains(localDomainsRes.data || [])
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.ACME)
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
      showError(error.message || ERRORS.LOAD_FAILED.GENERIC)
    }
  }, [showError])

  // Settings handlers
  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      await acmeService.updateSettings(acmeSettings)
      showSuccess(SUCCESS.UPDATE.SETTINGS)
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.SETTINGS)
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
      showError(ERRORS.VALIDATION.REQUIRED_FIELD)
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

  // =========================================================================
  // Let's Encrypt Client Handlers
  // =========================================================================
  
  const handleUpdateClientSetting = async (key, value) => {
    try {
      const updated = { ...clientSettings, [key]: value }
      setClientSettings(updated)
      await acmeService.updateClientSettings({ [key]: value })
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.SETTINGS)
      loadData() // Revert on error
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
      showError(error.message || ERRORS.UPDATE_FAILED.SETTINGS)
      loadData()
    }
  }
  
  const handleRequestCertificate = async (data) => {
    try {
      const result = await acmeService.requestCertificate(data)
      showSuccess(t('acme.certificateRequestCreated'))
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
      await acmeService.verifyChallenge(order.id)
      showSuccess(t('acme.challengeVerificationStarted'))
      loadData()
    } catch (error) {
      showError(error.message || t('acme.challengeVerificationFailed'))
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
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const domain = order.primary_domain || 'certificate'
      const suffix = includeKey ? '-with-key' : ''
      a.download = `${domain}${suffix}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      
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
      showError(error.message || ERRORS.SAVE_FAILED.GENERIC)
    }
  }
  
  const handleTestDnsProvider = async (provider) => {
    try {
      const result = await acmeService.testDnsProvider(provider.id)
      if (result.success) {
        showSuccess(t('acme.dnsProviderTestSuccess'))
      } else {
        showWarning(result.message || t('common.dnsProviderTestFailed'))
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
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
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
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
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
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
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
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
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
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
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
            <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
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
      <Button variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
        {t('common.refresh')}
      </Button>
      {activeTab === 'accounts' && (
        <Button size="sm" onClick={() => setShowCreateModal(true)}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.newAccount')}</span>
        </Button>
      )}
      {activeTab === 'domains' && (
        <Button size="sm" onClick={() => { setSelectedAcmeDomain(null); setShowDomainModal(true) }}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.addDomain')}</span>
        </Button>
      )}
      {activeTab === 'localdomains' && (
        <Button size="sm" onClick={() => { setSelectedLocalDomain(null); setShowLocalDomainModal(true) }}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.addDomain')}</span>
        </Button>
      )}
    </>
  )

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
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

  // Account detail content for slide-over
  const accountDetailContent = selectedAccount && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Key}
        iconClass={selectedAccount.status === 'valid' ? "bg-status-success/20" : "bg-bg-tertiary"}
        title={selectedAccount.contact?.[0]?.replace('mailto:', '') || selectedAccount.email || t('acme.account')}
        subtitle={`ID: ${selectedAccount.account_id?.substring(0, 24)}...`}
        badge={
          <Badge variant={selectedAccount.status === 'valid' ? 'success' : 'secondary'} size="sm">
            {selectedAccount.status === 'valid' && <CheckCircle size={10} weight="fill" />}
            {selectedAccount.status}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Key, value: selectedAccount.key_type || 'RSA-2048' },
        { icon: Globe, value: `${orders.length} ${t('acme.orders').toLowerCase()}` },
        { icon: ShieldCheck, value: `${challenges.length} ${t('common.challenges').toLowerCase()}` },
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button 
          size="sm" 
          variant="secondary"
          className="flex-1"
          onClick={() => handleDeactivate(selectedAccount.id)}
          disabled={selectedAccount.status !== 'valid'}
        >
          <XCircle size={14} />
          {t('common.deactivate')}
        </Button>
        <Button 
          size="sm" 
          variant="danger"
          onClick={() => handleDelete(selectedAccount.id)}
        >
          <Trash size={14} />
        </Button>
      </div>

      {/* Detail Tabs */}
      <div className="flex gap-1 border-b border-border">
        {detailTabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveDetailTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              activeDetailTab === tab.id
                ? 'border-accent-primary text-accent-primary'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            <tab.icon size={14} />
            {tab.label}
            {tab.count > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-2xs rounded-full bg-bg-tertiary">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeDetailTab === 'account' && (
        <div className="space-y-3">
          <CompactSection title={t('common.accountInformation')}>
            <CompactGrid>
              <CompactField autoIcon="email" label={t('common.email')} value={selectedAccount.contact?.[0]?.replace('mailto:', '') || selectedAccount.email} />
              <CompactField autoIcon="status" label={t('common.status')}>
                <StatusIndicator status={selectedAccount.status === 'valid' ? 'active' : 'inactive'}>
                  {selectedAccount.status}
                </StatusIndicator>
              </CompactField>
              <CompactField autoIcon="keyType" label={t('common.keyType')} value={selectedAccount.key_type || 'RSA-2048'} />
              <CompactField autoIcon="created" label={t('common.created')} value={formatDate(selectedAccount.created_at)} />
            </CompactGrid>
          </CompactSection>

          <CompactSection title={t('acme.accountId')} collapsible defaultOpen={false}>
            <p className="font-mono text-2xs text-text-secondary break-all bg-bg-tertiary/50 p-2 rounded">
              {selectedAccount.account_id}
            </p>
          </CompactSection>

          <CompactSection title={t('acme.termsOfService')}>
            <div className="flex items-center gap-2 text-xs">
              {selectedAccount.terms_of_service_agreed || selectedAccount.tos_agreed ? (
                <>
                  <CheckCircle size={14} className="status-success-text" weight="fill" />
                  <span className="status-success-text">{t('acme.accepted')}</span>
                </>
              ) : (
                <>
                  <XCircle size={14} className="status-danger-text" weight="fill" />
                  <span className="status-danger-text">{t('acme.notAccepted')}</span>
                </>
              )}
            </div>
          </CompactSection>
        </div>
      )}

      {activeDetailTab === 'orders' && (
        <CompactSection title={`${orders.length} ${t('acme.orders')}`}>
          {orders.length === 0 ? (
            <p className="text-xs text-text-tertiary py-4 text-center">{t('acme.noCertificateOrders')}</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
              {orders.map((order, i) => (
                <div key={i} className="p-3 bg-bg-tertiary/50 rounded-lg border border-border/50 hover:border-border transition-colors">
                  {/* Header: Domain + Status */}
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-sm font-medium text-text-primary truncate flex-1">
                      {order.domain || order.identifier || t('common.unknown')}
                    </span>
                    <Badge 
                      variant={
                        order.status?.toLowerCase() === 'valid' ? 'success' : 
                        order.status?.toLowerCase() === 'pending' ? 'warning' :
                        order.status?.toLowerCase() === 'ready' ? 'info' :
                        'error'
                      } 
                      size="sm"
                    >
                      {order.status || t('common.unknown')}
                    </Badge>
                  </div>
                  
                  {/* Details Grid */}
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">{t('acme.method')}</span>
                      <span className="text-text-secondary font-medium">{order.method || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">{t('common.expires')}</span>
                      <span className="text-text-secondary">{order.expires || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between col-span-2">
                      <span className="text-text-tertiary">{t('common.created')}</span>
                      <span className="text-text-secondary">{order.created_at ? formatDate(order.created_at) : 'N/A'}</span>
                    </div>
                    {order.order_id && (
                      <div className="flex justify-between col-span-2 mt-1 pt-1 border-t border-border/30">
                        <span className="text-text-tertiary">{t('acme.orderId')}</span>
                        <span className="text-text-tertiary font-mono text-[10px] truncate max-w-[180px]" title={order.order_id}>
                          {order.order_id}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      )}

      {activeDetailTab === 'challenges' && (
        <CompactSection title={`${challenges.length} ${t('common.challenges')}`}>
          {challenges.length === 0 ? (
            <p className="text-xs text-text-tertiary py-4 text-center">{t('acme.noActiveChallenges')}</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {challenges.map((ch, i) => (
                <div key={i} className="p-2 bg-bg-tertiary/30 rounded text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary" size="sm">{ch.type}</Badge>
                    <Badge 
                      variant={ch.status === 'valid' ? 'success' : ch.status === 'pending' ? 'warning' : 'danger'} 
                      size="sm"
                    >
                      {ch.status}
                    </Badge>
                  </div>
                  <p className="text-text-secondary truncate">{ch.domain}</p>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      )}
    </div>
  )

  // =========================================================================
  // Let's Encrypt Tab Content
  // =========================================================================
  
  const letsEncryptContent = (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.letsEncryptAbout')} compact>
        {t('acme.letsEncryptAboutDesc')}
      </HelpCard>
      
      {/* Request Certificate Button */}
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setShowRequestModal(true)}>
          <Plus size={14} />
          {t('acme.requestCertificate')}
        </Button>
        <Button variant="secondary" onClick={loadData}>
          <ArrowsClockwise size={14} />
          {t('common.refresh')}
        </Button>
      </div>
      
      {/* Info about History tab */}
      <HelpCard variant="info" compact>
        <span className="flex items-center gap-2">
          <ClockCounterClockwise size={16} />
          {t('acme.viewHistoryForCertificates')}
        </span>
      </HelpCard>
      
      {/* Client Settings */}
      <CompactSection title={t('common.settings')} icon={Gear}>
        <div className="space-y-3">
          <Select
            label={t('acme.defaultEnvironment')}
            value={clientSettings.default_environment || 'staging'}
            onChange={(val) => handleUpdateClientSetting('default_environment', val)}
            options={[
              { value: 'staging', label: t('acme.staging') + ' (Test)' },
              { value: 'production', label: t('acme.production') + ' (Live)' }
            ]}
            helperText={t('acme.environmentHelper')}
          />
          
          <Input
            label={t('acme.contactEmail')}
            type="email"
            value={clientSettings.contact_email || ''}
            onChange={(e) => handleUpdateClientSetting('contact_email', e.target.value)}
            helperText={t('acme.contactEmailHelper')}
          />
          
          <ToggleSwitch
            checked={clientSettings.auto_renewal ?? true}
            onChange={(val) => handleUpdateClientSetting('auto_renewal', val)}
            label={t('acme.autoRenewal')}
            description={t('acme.autoRenewalDesc')}
          />
        </div>
      </CompactSection>

      {/* Let's Encrypt Proxy */}
      <CompactSection title={t('acme.letsEncryptProxy')} icon={ShieldCheck}>
        <div className="space-y-3">
          <ToggleSwitch
            checked={clientSettings.proxy_enabled || false}
            onChange={(val) => handleUpdateClientSetting('proxy_enabled', val)}
            label={t('acme.enableLetsEncryptProxy')}
            description={t('acme.enableLetsEncryptProxyDesc')}
          />

          {clientSettings.proxy_enabled && (
            <>
              <CompactGrid columns={1}>
                <CompactField 
                  autoIcon="environment"
                  label={t('acme.proxyEndpoint')} 
                  value={`${window.location.origin}/acme/proxy/directory`}
                  mono
                  copyable
                />
              </CompactGrid>
              
              <div className="p-3 bg-bg-tertiary/50 rounded-lg space-y-2">
                <p className="text-xs font-medium text-text-secondary">{t('acme.proxyUsage')}</p>
                <pre className="text-xs text-text-primary bg-bg-secondary p-2 rounded overflow-x-auto font-mono">
{`certbot certonly \\
  --server ${window.location.origin}/acme/proxy/directory \\
  --preferred-challenges dns \\
  -d example.com`}
                </pre>
                <p className="text-xs text-text-tertiary">{t('acme.proxyUsageNote')}</p>
              </div>
              
              {clientSettings.proxy_registered ? (
                <div className="p-3 rounded-lg status-success-bg status-success-border border">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={18} className="status-success-text" weight="fill" />
                      <div>
                        <p className="text-sm font-medium text-text-primary">{t('acme.proxyRegistered')}</p>
                        <p className="text-xs text-text-secondary">{clientSettings.proxy_email}</p>
                      </div>
                    </div>
                    <Button 
                      variant="ghost" 
                      size="sm"
                      onClick={handleUnregisterProxy}
                      className="status-danger-text hover:status-danger-bg"
                    >
                      <Trash size={14} />
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 p-3 bg-bg-tertiary/30 rounded-lg">
                  <Input
                    label={t('common.emailAddress')}
                    type="email"
                    value={proxyEmail}
                    onChange={(e) => setProxyEmail(e.target.value)}
                    placeholder={t('acme.emailPlaceholder')}
                    helperText={t('common.emailRequired')}
                  />
                  <Button 
                    variant="secondary" 
                    size="sm"
                    onClick={handleRegisterProxy}
                    disabled={!proxyEmail}
                  >
                    <Key size={14} />
                    {t('acme.registerAccount')}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </CompactSection>
    </div>
  )
  
  // =========================================================================
  // DNS Providers Tab Content
  // =========================================================================
  
  const dnsProvidersContent = (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.dnsProviders')} compact>
        {t('acme.dnsProvidersAboutDesc')}
      </HelpCard>
      
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => { setSelectedDnsProvider(null); setShowDnsProviderModal(true) }}>
          <Plus size={14} />
          {t('common.addDnsProvider')}
        </Button>
      </div>
      
      {dnsProviders.length === 0 ? (
        <div className="text-center py-8 text-text-secondary">
          <PlugsConnected size={40} className="mx-auto mb-2 opacity-40" />
          <p>{t('acme.noDnsProviders')}</p>
          <p className="text-sm text-text-tertiary mt-1">{t('acme.noDnsProvidersDesc')}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {dnsProviders.map(provider => (
            <Card key={provider.id} className="p-4">
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    provider.is_default ? "icon-bg-emerald" : "icon-bg-violet"
                  )}>
                    <PlugsConnected size={16} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">{provider.name}</p>
                    <p className="text-xs text-text-tertiary">{provider.provider_type}</p>
                  </div>
                </div>
                {provider.is_default && (
                  <Badge variant="success" size="sm">{t('common.default')}</Badge>
                )}
              </div>
              
              <div className="flex gap-2 mt-3">
                <Button 
                  size="sm" 
                  variant="secondary"
                  onClick={() => handleTestDnsProvider(provider)}
                >
                  <Play size={12} />
                  {t('common.test')}
                </Button>
                <Button 
                  size="sm" 
                  variant="secondary"
                  onClick={() => { setSelectedDnsProvider(provider); setShowDnsProviderModal(true) }}
                >
                  <Gear size={12} />
                  {t('common.edit')}
                </Button>
                <Button 
                  size="sm" 
                  variant="danger"
                  onClick={() => handleDeleteDnsProvider(provider)}
                >
                  <Trash size={12} />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )

  // Domains content - Map domains to DNS providers for ACME Proxy
  const domainsContent = (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.domainsHelp')} compact>
        {t('acme.domainsHelpDesc')}
      </HelpCard>

      {acmeDomains.length === 0 ? (
        <Card className="p-8 text-center">
          <GlobeHemisphereWest size={48} className="mx-auto text-text-tertiary mb-4" />
          <h3 className="text-lg font-medium text-text-primary mb-2">
            {t('acme.noDomainsYet')}
          </h3>
          <p className="text-sm text-text-secondary mb-4">
            {t('acme.noDomainsDesc')}
          </p>
          <Button onClick={() => { setSelectedAcmeDomain(null); setShowDomainModal(true) }}>
            <Plus size={14} />
            {t('acme.addDomain')}
          </Button>
        </Card>
      ) : (
        <ResponsiveDataTable
          data={acmeDomains}
          columns={[
            {
              key: 'domain',
              label: t('acme.domain'),
              sortable: true,
              render: (val) => (
                <span className="font-mono text-sm">{val}</span>
              )
            },
            {
              key: 'dns_provider_name',
              label: t('acme.provider'),
              sortable: true,
              render: (val, row) => (
                <div className="flex items-center gap-2">
                  <PlugsConnected size={14} className="text-accent-primary" />
                  <span>{val || row.dns_provider_type}</span>
                </div>
              )
            },
            {
              key: 'issuing_ca_name',
              label: t('acme.issuingCA'),
              sortable: true,
              render: (val) => (
                <span className={val ? 'text-text-primary' : 'text-text-tertiary'}>
                  {val || t('acme.defaultCA')}
                </span>
              )
            },
            {
              key: 'is_wildcard_allowed',
              label: t('acme.wildcard'),
              render: (val) => (
                <Badge variant={val ? 'success' : 'secondary'}>
                  {val ? t('common.yes') : t('common.no')}
                </Badge>
              )
            },
            {
              key: 'auto_approve',
              label: t('acme.autoApprove'),
              render: (val) => (
                <Badge variant={val ? 'success' : 'warning'}>
                  {val ? t('common.auto') : t('common.manual')}
                </Badge>
              )
            },
            {
              key: 'actions',
              label: '',
              render: (_, row) => (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); handleTestDomainAccess(row) }}
                    title={t('acme.testDnsAccess')}
                  >
                    <Play size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); setSelectedAcmeDomain(row); setShowDomainModal(true) }}
                    title={t('common.edit')}
                  >
                    <Gear size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); handleDeleteDomain(row) }}
                    title={t('common.delete')}
                    className="text-status-error hover:text-status-error"
                  >
                    <Trash size={14} />
                  </Button>
                </div>
              )
            }
          ]}
          onRowClick={(row) => { setSelectedAcmeDomain(row); setShowDomainModal(true) }}
          emptyMessage={t('acme.noDomains')}
        />
      )}
    </div>
  )

  // Configuration content
  const configContent = (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('common.aboutAcme')} compact>
        {t('acme.aboutAcmeDesc')}
      </HelpCard>

      {/* ACME Server */}
      <CompactSection title={t('acme.acmeServer')} icon={Globe}>
        <div className="space-y-3">
          <ToggleSwitch
            checked={acmeSettings.enabled || false}
            onChange={(val) => updateSetting('enabled', val)}
            label={t('acme.enableAcmeServer')}
            description={t('acme.enableAcmeServerDesc')}
          />

          <Select
            label={t('acme.defaultIssuingCA')}
            value={acmeSettings.issuing_ca_id?.toString() || ''}
            onChange={(val) => updateSetting('issuing_ca_id', val ? parseInt(val) : null)}
            disabled={!acmeSettings.enabled}
            placeholder={t('common.acmeSelectCA')}
            options={cas.map(ca => ({ 
              value: ca.id.toString(), 
              label: ca.name || ca.common_name 
            }))}
          />
        </div>
      </CompactSection>

      {/* Certificate Renewal Policy */}
      <CompactSection title={t('acme.renewalPolicy')} icon={ArrowsClockwise}>
        <div className="space-y-2">
          <ToggleSwitch
            checked={acmeSettings.revoke_on_renewal || false}
            onChange={handleToggleRevokeOnRenewal}
            label={t('acme.revokeOnRenewal')}
            description={t('acme.revokeOnRenewalDesc')}
          />
          
          {!acmeSettings.revoke_on_renewal && acmeSettings.superseded_count > 0 && (
            <label className="flex items-center gap-3 cursor-pointer ml-7 p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
              <input
                type="checkbox"
                checked={revokeSuperseded}
                onChange={(e) => setRevokeSuperseded(e.target.checked)}
                className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-warning focus:ring-accent-warning/50"
              />
              <div>
                <p className="text-sm text-accent-warning font-medium">
                  {t('acme.revokeExistingSuperseded', { count: acmeSettings.superseded_count })}
                </p>
                <p className="text-xs text-text-secondary">{t('acme.revokeExistingSupersededDesc')}</p>
              </div>
            </label>
          )}
        </div>
      </CompactSection>

      {/* ACME Endpoints */}
      <CompactSection title={t('acme.endpoints')} icon={Lightning}>
        <CompactGrid columns={1}>
          <CompactField 
            autoIcon="environment"
            label={t('acme.directory')} 
            value={`${window.location.origin}/acme/directory`}
            mono
            copyable
          />
        </CompactGrid>
        <p className="text-xs text-text-tertiary mt-2">
          {t('acme.certbotUsage')} <code className="bg-bg-tertiary px-1 rounded">--server {window.location.origin}/acme/directory</code>
        </p>
      </CompactSection>

      {/* Save Button */}
      <div className="flex gap-2 pt-3 border-t border-border">
        <Button onClick={handleSaveConfig} disabled={saving}>
          <FloppyDisk size={14} />
          {saving ? t('common.saving') : t('common.saveConfiguration')}
        </Button>
      </div>
    </div>
  )

  // Local Domains content — domain to CA mapping
  const localDomainsContent = (
    <ResponsiveDataTable
      data={localDomains}
      columns={[
        {
          key: 'domain',
          label: t('acme.domain'),
          sortable: true,
          render: (val) => (
            <span className="font-mono text-sm">{val}</span>
          )
        },
        {
          key: 'issuing_ca_name',
          label: t('acme.issuingCA'),
          sortable: true,
          render: (val) => (
            <span className="text-text-primary">{val || '-'}</span>
          )
        },
        {
          key: 'auto_approve',
          label: t('acme.autoApprove'),
          render: (val) => (
            <Badge variant={val ? 'success' : 'warning'}>
              {val ? t('common.auto') : t('common.manual')}
            </Badge>
          )
        },
        {
          key: 'actions',
          label: '',
          render: (_, row) => (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => { e.stopPropagation(); setSelectedLocalDomain(row); setShowLocalDomainModal(true) }}
                title={t('common.edit')}
              >
                <PencilSimple size={14} />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => { e.stopPropagation(); handleDeleteLocalDomain(row) }}
                title={t('common.delete')}
                className="text-status-error hover:text-status-error"
              >
                <Trash size={14} />
              </Button>
            </div>
          )
        }
      ]}
      emptyState={{
        icon: GlobeHemisphereWest,
        title: t('acme.noLocalDomains'),
        description: t('acme.noLocalDomainsDesc'),
        action: (
          <Button onClick={() => { setSelectedLocalDomain(null); setShowLocalDomainModal(true) }}>
            <Plus size={14} />
            {t('acme.addDomain')}
          </Button>
        )
      }}
      onRowClick={(row) => { setSelectedLocalDomain(row); setShowLocalDomainModal(true) }}
    />
  )

  // Accounts content with table
  const accountsContent = (
    <ResponsiveDataTable
      data={filteredAccounts}
      columns={accountColumns}
      searchable
      searchPlaceholder={t('acme.searchAccounts')}
      onSearch={setSearchQuery}
      onRowClick={selectAccount}
      selectedRow={selectedAccount}
      getRowId={(row) => row.id}
      pagination={{
        page,
        total: filteredAccounts.length,
        perPage,
        onChange: setPage,
        onPerPageChange: (v) => { setPerPage(v); setPage(1) }
      }}
      emptyState={{
        icon: Key,
        title: t('acme.noAccounts'),
        description: searchQuery ? t('acme.noMatchingAccounts') : t('acme.noAccountsDesc'),
        action: !searchQuery && (
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus size={14} />
            {t('acme.createAccount')}
          </Button>
        )
      }}
    />
  )

  // History content
  const historyColumns = useMemo(() => [
    {
      key: 'common_name',
      header: t('common.commonName'),
      priority: 1,
      sortable: true,
      render: (value, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
            row?.revoked ? "icon-bg-orange" : "icon-bg-blue"
          )}>
            <Certificate size={14} weight="duotone" />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-medium truncate">{value}</span>
            {row?.order?.account && (
              <span className="text-xs text-text-tertiary">via {row.order.account}</span>
            )}
          </div>
        </div>
      ),
      mobileRender: (value, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
              row?.revoked ? "icon-bg-orange" : "icon-bg-blue"
            )}>
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{value}</span>
          </div>
          <Badge 
            variant={row?.revoked ? 'danger' : 'success'} 
            size="sm"
            icon={row?.revoked ? XCircle : CheckCircle}
          >
            {row?.revoked ? t('common.revoked') : t('common.valid')}
          </Badge>
        </div>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 2,
      hideOnMobile: true,
      render: (value, row) => {
        // Show revoked status first if applicable
        if (row?.revoked) {
          return (
            <Badge variant="danger" size="sm" icon={XCircle} dot>
              {t('common.revoked')}
            </Badge>
          );
        }
        // Show order status
        const statusConfig = {
          valid: { variant: 'success', icon: CheckCircle, pulse: true },
          issued: { variant: 'success', icon: CheckCircle, pulse: false },
          pending: { variant: 'warning', icon: Clock, pulse: true },
          processing: { variant: 'info', icon: Clock, pulse: true },
          ready: { variant: 'info', icon: CheckCircle, pulse: false },
          invalid: { variant: 'danger', icon: XCircle, pulse: false },
        };
        const config = statusConfig[value] || statusConfig.valid;
        return (
          <Badge 
            variant={config.variant} 
            size="sm"
            icon={config.icon}
            dot
            pulse={config.pulse}
          >
            {value ? value.charAt(0).toUpperCase() + value.slice(1) : t('common.valid')}
          </Badge>
        );
      }
    },
    {
      key: 'issuer',
      header: t('common.issuer'),
      priority: 3,
      sortable: true,
      hideOnMobile: true,
      render: (value) => (
        <span className="text-sm text-text-secondary">{value || t('common.unknown')}</span>
      ),
      mobileRender: (value) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">CA:</span>
          <span className="text-text-secondary truncate">{value || t('common.unknown')}</span>
        </div>
      )
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      sortable: true,
      render: (value) => {
        if (!value) return <span className="text-text-tertiary">N/A</span>
        const expires = new Date(value)
        const now = new Date()
        const daysLeft = Math.ceil((expires - now) / (1000 * 60 * 60 * 24))
        const isExpiring = daysLeft > 0 && daysLeft < 30
        const isExpired = daysLeft <= 0
        return (
          <div className="flex items-center gap-2">
            <Clock size={14} className={cn(
              isExpired ? "text-status-error" : 
              isExpiring ? "text-status-warning" : 
              "text-text-tertiary"
            )} />
            <div className="flex flex-col">
              <span className="text-xs text-text-secondary whitespace-nowrap">{formatDate(value)}</span>
              <span className={cn(
                "text-xs",
                isExpired ? "text-status-error" : 
                isExpiring ? "text-status-warning" : 
                "text-text-tertiary"
              )}>
                {isExpired ? t('common.expired') : t('acme.daysLeft', { count: daysLeft })}
              </span>
            </div>
          </div>
        )
      },
      mobileRender: (value) => {
        if (!value) return null
        const expires = new Date(value)
        const now = new Date()
        const daysLeft = Math.ceil((expires - now) / (1000 * 60 * 60 * 24))
        const isExpired = daysLeft <= 0
        return (
          <div className="flex items-center gap-2 text-xs">
            <Clock size={12} className="text-text-tertiary" />
            <span className={isExpired ? "text-status-error" : "text-text-secondary"}>
              {isExpired ? t('common.expired') : `${daysLeft}d`}
            </span>
          </div>
        )
      }
    },
    {
      key: 'source',
      header: t('common.source'),
      priority: 3,
      hideOnMobile: true,
      render: (value) => (
        <Badge 
          variant={value === 'letsencrypt' ? 'green' : 'cyan'} 
          size="sm"
          dot
        >
          {value === 'letsencrypt' ? t('acme.letsEncryptLabel') : t('acme.localAcmeLabel')}
        </Badge>
      )
    },
    {
      key: 'challenge_type',
      header: t('acme.method'),
      priority: 4,
      hideOnMobile: true,
      render: (value) => (
        <Badge variant="default" size="sm">
          {value?.toUpperCase() || 'N/A'}
        </Badge>
      )
    },
    {
      key: 'dns_provider',
      header: t('acme.provider'),
      priority: 5,
      hideOnMobile: true,
      render: (value) => (
        <span className="text-sm text-text-secondary">{value || '-'}</span>
      )
    },
    {
      key: 'environment',
      header: t('acme.environment'),
      priority: 5,
      hideOnMobile: true,
      render: (value) => {
        if (!value) return <span className="text-text-tertiary">-</span>
        const isProduction = value === 'production'
        return (
          <Badge 
            variant={isProduction ? 'success' : 'warning'} 
            size="sm"
          >
            {isProduction ? t('acme.production') : t('acme.staging')}
          </Badge>
        )
      }
    },
    {
      key: 'created_at',
      header: t('common.issued'),
      priority: 6,
      sortable: true,
      hideOnMobile: true,
      render: (value) => (
        <span className="text-xs text-text-tertiary whitespace-nowrap">
          {value ? formatDate(value) : 'N/A'}
        </span>
      )
    }
  ], [t])

  // Certificate detail content for history tab
  const certDetailContent = selectedCert && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={ClockCounterClockwise}
        iconClass={selectedCert.revoked ? "bg-status-error/20" : "bg-status-success/20"}
        title={selectedCert.common_name}
        subtitle={`${t('common.issuer')}: ${selectedCert.issuer || t('acme.unknownCA')}`}
        badge={
          <Badge variant={selectedCert.revoked ? 'danger' : 'success'} size="sm">
            {!selectedCert.revoked && <CheckCircle size={10} weight="fill" />}
            {selectedCert.revoked ? t('common.revoked') : t('common.valid')}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Key, value: selectedCert.order?.account || t('common.unknown') },
        { icon: Globe, value: selectedCert.order?.status || t('common.na') },
      ]} />
      
      <CompactSection title={t('common.certificateDetails')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={selectedCert.common_name} copyable />
          <CompactField autoIcon="serialNumber" label={t('common.serialNumber')} value={selectedCert.serial} mono copyable />
          <CompactField autoIcon="issuer" label={t('common.issuer')} value={selectedCert.issuer || t('common.unknown')} />
        </CompactGrid>
      </CompactSection>
      
      <CompactSection title={t('common.validity')}>
        <CompactGrid>
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={selectedCert.valid_from ? formatDate(selectedCert.valid_from) : t('common.na')} />
          <CompactField autoIcon="validTo" label={t('common.validTo')} value={selectedCert.valid_to ? formatDate(selectedCert.valid_to) : t('common.na')} />
          <CompactField autoIcon="issued" label={t('common.issued')} value={selectedCert.created_at ? formatDate(selectedCert.created_at) : t('common.na')} />
        </CompactGrid>
      </CompactSection>
      
      {selectedCert.order && (
        <CompactSection title={t('acme.acmeOrder')}>
          <CompactGrid>
            <CompactField autoIcon="account" label={t('acme.account')} value={selectedCert.order.account} />
            <CompactField autoIcon="orderStatus" label={t('acme.orderStatus')} value={selectedCert.order.status} />
            <CompactField autoIcon="orderId" label={t('acme.orderId')} value={selectedCert.order.order_id} mono copyable />
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
  
  // Let's Encrypt Order Detail Content
  const orderDetailContent = selectedClientOrder && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Certificate}
        iconClass={cn(
          selectedClientOrder.status === 'valid' || selectedClientOrder.status === 'issued' ? "bg-status-success/20" :
          selectedClientOrder.status === 'invalid' ? "bg-status-error/20" :
          selectedClientOrder.status === 'pending' ? "bg-status-warning/20" : "bg-bg-tertiary"
        )}
        title={selectedClientOrder.primary_domain || selectedClientOrder.domains?.[0]}
        subtitle={`${selectedClientOrder.environment} • ${selectedClientOrder.challenge_type}`}
        badge={
          <Badge 
            variant={selectedClientOrder.status === 'valid' || selectedClientOrder.status === 'issued' ? 'success' : 
                     selectedClientOrder.status === 'invalid' ? 'danger' : 
                     selectedClientOrder.status === 'pending' ? 'warning' : 'default'}
            size="sm"
          >
            {selectedClientOrder.status}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Globe, value: `${(selectedClientOrder.domains || []).length} ${t('acme.domains').toLowerCase()}` },
        { icon: PlugsConnected, value: selectedClientOrder.dns_provider_name || t('acme.manualDns') },
      ]} />
      
      {/* Domains */}
      <CompactSection title={t('acme.domains')}>
        <div className="space-y-1">
          {(selectedClientOrder.domains || []).map((domain, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <Globe size={12} className="text-text-tertiary" />
              <span className="text-text-primary">{domain}</span>
            </div>
          ))}
        </div>
      </CompactSection>
      
      {/* Order Info */}
      <CompactSection title={t('acme.orderInfo')}>
        <CompactGrid>
          <CompactField autoIcon="environment" label={t('acme.environment')} value={selectedClientOrder.environment === 'production' ? t('acme.production') : t('acme.staging')} />
          <CompactField autoIcon="method" label={t('acme.method')} value={selectedClientOrder.challenge_type?.toUpperCase()} />
          <CompactField autoIcon="provider" label={t('acme.provider')} value={selectedClientOrder.dns_provider_name || t('acme.manualDns')} />
          <CompactField autoIcon="status" label={t('common.status')} value={selectedClientOrder.status} />
          <CompactField autoIcon="created" label={t('common.created')} value={formatDate(selectedClientOrder.created_at)} />
          {selectedClientOrder.expires_at && (
            <CompactField autoIcon="expires" label={t('common.expires')} value={formatDate(selectedClientOrder.expires_at)} />
          )}
        </CompactGrid>
      </CompactSection>
      
      {/* Challenge Info for pending orders */}
      {selectedClientOrder.status === 'pending' && selectedClientOrder.challenges && (
        <CompactSection title={t('acme.pendingChallenge')}>
          <div className="space-y-3">
            {Object.entries(selectedClientOrder.challenges).map(([domain, data]) => (
              <div key={domain} className="p-2 bg-bg-tertiary/50 rounded-lg border border-border/50">
                <p className="text-sm font-medium text-text-primary mb-2">{domain}</p>
                {selectedClientOrder.challenge_type === 'dns-01' && (
                  <div className="space-y-2 text-xs">
                    <CompactField autoIcon="dnsRecordName" label={t('acme.dnsRecordName')} value={data.dns_txt_name || data.record_name} mono copyable />
                    <CompactField autoIcon="dnsRecordValue" label={t('acme.dnsRecordValue')} value={data.dns_txt_value || data.record_value} mono copyable />
                  </div>
                )}
              </div>
            ))}
          </div>
        </CompactSection>
      )}
      
      {/* Error Message */}
      {selectedClientOrder.error_message && (
        <CompactSection title={t('common.error')}>
          <div className="p-2 bg-status-error/10 border border-status-error/20 rounded-lg">
            <p className="text-sm text-status-error">{selectedClientOrder.error_message}</p>
          </div>
        </CompactSection>
      )}
      
      {/* Certificate Actions - for issued/valid orders */}
      {(selectedClientOrder.status === 'valid' || selectedClientOrder.status === 'issued') && selectedClientOrder.certificate_id && (
        <CompactSection title={t('acme.certificateActions')}>
          <div className="grid grid-cols-2 gap-2">
            <Button size="sm" variant="secondary" onClick={() => handleDownloadCertificate(selectedClientOrder, 'pem', false)}>
              <DownloadSimple size={12} />
              {t('acme.downloadCert')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleDownloadCertificate(selectedClientOrder, 'pem', true)}>
              <LockKey size={12} />
              {t('acme.downloadWithKey')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleViewCertificate(selectedClientOrder)}>
              <Eye size={12} />
              {t('common.viewCertificate')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleRenewCertificate(selectedClientOrder)}>
              <ArrowsClockwise size={12} />
              {t('acme.renewNow')}
            </Button>
          </div>
        </CompactSection>
      )}
      
      {/* Actions */}
      <div className="flex flex-wrap gap-2 pt-2">
        {selectedClientOrder.status === 'pending' && (
          <Button size="sm" onClick={() => handleVerifyChallenge(selectedClientOrder)}>
            <Play size={12} />
            {t('acme.verifyChallenge')}
          </Button>
        )}
        {selectedClientOrder.status === 'processing' && (
          <Button size="sm" onClick={() => handleFinalizeOrder(selectedClientOrder)}>
            <CheckCircle size={12} />
            {t('acme.finalize')}
          </Button>
        )}
        <Button size="sm" variant="danger" onClick={() => handleDeleteClientOrder(selectedClientOrder)}>
          <Trash size={12} />
          {t('common.delete')}
        </Button>
      </div>
    </div>
  )
  
  // Filter history data
  const filteredHistory = useMemo(() => {
    let filtered = history
    if (historyFilterStatus) {
      filtered = filtered.filter(cert => 
        historyFilterStatus === 'revoked' ? cert.revoked : !cert.revoked
      )
    }
    if (historyFilterCA) {
      filtered = filtered.filter(cert => cert.issuer === historyFilterCA)
    }
    if (historyFilterSource) {
      filtered = filtered.filter(cert => cert.source === historyFilterSource)
    }
    return filtered
  }, [history, historyFilterStatus, historyFilterCA, historyFilterSource])

  // Get unique CAs from history for filter
  const historyCAs = useMemo(() => {
    const cas = [...new Set(history.map(c => c.issuer).filter(Boolean))]
    return cas.map(ca => ({ value: ca, label: ca }))
  }, [history])
  
  const historyContent = (
    <ResponsiveDataTable
      data={filteredHistory}
      columns={historyColumns}
      columnStorageKey="acme-history-columns"
      searchable
      searchPlaceholder={t('common.searchCertificates')}
      searchKeys={['common_name', 'serial', 'issuer']}
      getRowId={(row) => row.id}
      onRowClick={setSelectedCert}
      selectedRow={selectedCert}
      sortable
      defaultSort={{ key: 'created_at', direction: 'desc' }}
      exportEnabled
      exportFilename="acme-certificates"
      toolbarFilters={[
        {
          key: 'source',
          value: historyFilterSource,
          onChange: setHistoryFilterSource,
          placeholder: t('acme.allSources'),
          options: [
            { value: 'acme', label: t('acme.localAcme') },
            { value: 'letsencrypt', label: t('acme.letsEncrypt') }
          ]
        },
        {
          key: 'status',
          value: historyFilterStatus,
          onChange: setHistoryFilterStatus,
          placeholder: t('common.allStatus'),
          options: [
            { value: 'valid', label: t('common.valid') },
            { value: 'revoked', label: t('common.revoked') }
          ]
        },
        {
          key: 'ca',
          value: historyFilterCA,
          onChange: setHistoryFilterCA,
          placeholder: t('acme.allCAs'),
          options: historyCAs
        }
      ]}
      emptyState={{
        icon: ClockCounterClockwise,
        title: t('acme.noCertificates'),
        description: t('acme.noCertificatesDesc')
      }}
    />
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
          { labelKey: 'acme.groups.localAcme', tabs: ['config', 'localdomains', 'accounts', 'history'], color: 'icon-bg-violet' },
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
          activeTab === 'letsencrypt' ? orderDetailContent :
          activeTab === 'accounts' ? accountDetailContent : 
          certDetailContent
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
        {activeTab === 'letsencrypt' && letsEncryptContent}
        {activeTab === 'dns' && dnsProvidersContent}
        {activeTab === 'domains' && domainsContent}
        {activeTab === 'config' && configContent}
        {activeTab === 'localdomains' && localDomainsContent}
        {activeTab === 'accounts' && accountsContent}
        {activeTab === 'history' && historyContent}
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
          <div className="flex items-start gap-3 p-3 rounded-lg bg-accent-warning/10 border border-accent-warning/30">
            <Warning size={20} className="text-accent-warning flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-accent-warning">{t('common.warning')}</p>
              <p className="text-text-secondary mt-1">
                {t('acme.revokeSupersededConfirmDesc', { count: acmeSettings.superseded_count })}
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowRevokeConfirm(false)}>
              {t('common.cancel')}
            </Button>
            <Button variant="danger" onClick={handleConfirmRevokeSuperseded}>
              {t('acme.revokeSupersededConfirmAction', { count: acmeSettings.superseded_count })}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

// Create Account Form Component
function CreateAccountForm({ onSubmit, onCancel }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    email: '',
    key_type: 'RSA-2048',
    agree_tos: false,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!formData.agree_tos) {
      showWarning(t('acme.agreeToTermsRequired'))
      return
    }
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('common.emailAddress')}
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText={t('acme.contactEmailHelper')}
      />
      
      <Select
        label={t('common.keyType')}
        value={formData.key_type}
        onChange={(val) => setFormData(prev => ({ ...prev, key_type: val }))}
        options={[
          { value: 'RSA-2048', label: 'RSA 2048-bit' },
          { value: 'RSA-4096', label: 'RSA 4096-bit' },
          { value: 'EC-P256', label: 'ECDSA P-256' },
          { value: 'EC-P384', label: 'ECDSA P-384' },
        ]}
      />
      
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={formData.agree_tos}
          onChange={(e) => setFormData(prev => ({ ...prev, agree_tos: e.target.checked }))}
          className="rounded border-border bg-bg-tertiary mt-1"
        />
        <span className="text-sm text-text-primary">
          {t('acme.agreeToTerms')}
        </span>
      </label>
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <Plus size={14} />
          {t('acme.createAccount')}
        </Button>
      </div>
    </form>
  )
}

// Request Certificate Form Component (Let's Encrypt)
function RequestCertificateForm({ onSubmit, onCancel, dnsProviders, defaultEnvironment, defaultEmail }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    domains: '',
    email: defaultEmail,
    challenge_type: 'dns-01',
    environment: defaultEnvironment,
    dns_provider_id: dnsProviders.find(p => p.is_default)?.id || null
  })
  
  const handleSubmit = (e) => {
    e.preventDefault()
    
    // Parse domains
    const domainList = formData.domains
      .split(/[,\n]/)
      .map(d => d.trim())
      .filter(d => d)
    
    if (domainList.length === 0) {
      showWarning(t('acme.atLeastOneDomainRequired'))
      return
    }
    
    // Validate domain format
    const domainRegex = /^(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/i
    const invalidDomains = domainList.filter(d => !domainRegex.test(d))
    if (invalidDomains.length > 0) {
      showWarning(t('acme.invalidDomainFormat', { domains: invalidDomains.join(', ') }))
      return
    }
    
    // Check for wildcards with HTTP-01
    if (formData.challenge_type === 'http-01' && domainList.some(d => d.startsWith('*.'))) {
      showWarning(t('acme.wildcardRequiresDns01'))
      return
    }
    
    if (!formData.email) {
      showWarning(t('common.emailRequired'))
      return
    }
    
    onSubmit({
      ...formData,
      domains: domainList
    })
  }
  
  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      {formData.environment === 'production' && (
        <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg flex items-start gap-2">
          <Warning size={18} className="text-yellow-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-yellow-600 dark:text-yellow-400">{t('acme.productionWarningTitle')}</p>
            <p className="text-xs text-text-secondary mt-1">{t('acme.productionWarningDesc')}</p>
          </div>
        </div>
      )}
      
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1">
          {t('acme.domains')} <span className="text-red-500">*</span>
        </label>
        <textarea
          className="w-full h-24 px-3 py-2 rounded-lg border border-border bg-bg-primary text-text-primary text-sm resize-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary"
          value={formData.domains}
          onChange={(e) => setFormData(prev => ({ ...prev, domains: e.target.value }))}
          placeholder="example.com&#10;*.example.com&#10;sub.example.com"
          required
        />
        <p className="text-xs text-text-tertiary mt-1">{t('acme.domainsHelper')}</p>
      </div>
      
      <Input
        label={t('acme.contactEmail')}
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText={t('acme.contactEmailHelper')}
      />
      
      <Select
        label={t('acme.challengeType')}
        value={formData.challenge_type}
        onChange={(val) => setFormData(prev => ({ ...prev, challenge_type: val }))}
        options={[
          { value: 'dns-01', label: 'DNS-01 - ' + t('acme.dns01Desc') },
          { value: 'http-01', label: 'HTTP-01 - ' + t('acme.http01Desc') }
        ]}
        helperText={t('acme.challengeTypeHelper')}
      />
      
      {formData.challenge_type === 'dns-01' && (
        <Select
          label={t('acme.provider')}
          value={formData.dns_provider_id?.toString() || ''}
          onChange={(val) => setFormData(prev => ({ ...prev, dns_provider_id: val ? parseInt(val) : null }))}
          placeholder={t('acme.selectDnsProvider')}
          options={[
            { value: '', label: t('acme.manualDns') },
            ...dnsProviders.map(p => ({ 
              value: p.id.toString(), 
              label: p.name + (p.is_default ? ' (' + t('common.default') + ')' : '')
            }))
          ]}
          helperText={t('acme.dnsProviderHelper')}
        />
      )}
      
      <Select
        label={t('acme.environment')}
        value={formData.environment}
        onChange={(val) => setFormData(prev => ({ ...prev, environment: val }))}
        options={[
          { value: 'staging', label: t('acme.staging') + ' - ' + t('acme.stagingDesc') },
          { value: 'production', label: t('acme.production') + ' - ' + t('acme.productionDesc') }
        ]}
      />
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <CloudArrowUp size={14} />
          {t('acme.requestCertificate')}
        </Button>
      </div>
    </form>
  )
}

// Provider icon/color mapping is now in components/ProviderIcons.jsx

function ProviderTypeGrid({ label, providers, value, onChange, disabled }) {
  const [search, setSearch] = useState('')
  const { t } = useTranslation()

  const filtered = providers.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase())
  )

  // Group: Manual first, then Popular (sorted by rank), then Other alphabetical
  const popularOrder = ['cloudflare', 'route53', 'azure', 'gcloud', 'ovh', 'hetzner', 'digitalocean', 'gandi', 'porkbun']
  const manualProvider = filtered.find(p => p.type === 'manual')
  const rfc2136Provider = filtered.find(p => p.type === 'rfc2136')
  const popularProviders = popularOrder
    .map(type => filtered.find(p => p.type === type))
    .filter(Boolean)
  const otherProviders = filtered
    .filter(p => p.type !== 'manual' && p.type !== 'rfc2136' && !popularOrder.includes(p.type))
    .sort((a, b) => a.name.localeCompare(b.name))

  const renderCard = (pt) => {
    const brandColor = getProviderColor(pt.type)
    const isSelected = value === pt.type
    return (
      <button
        key={pt.type}
        type="button"
        disabled={disabled}
        onClick={() => !disabled && onChange(pt.type)}
        className={cn(
          "flex flex-col items-center gap-1.5 p-2.5 rounded-lg border text-center transition-all duration-200 min-h-[72px]",
          "hover:scale-[1.03] hover:shadow-md",
          disabled && "opacity-50 cursor-not-allowed",
          isSelected
            ? "border-accent-primary bg-accent-primary/10 ring-2 ring-accent-primary/40 shadow-sm"
            : "border-border/50 bg-bg-tertiary/40 hover:border-text-secondary/40 hover:bg-bg-tertiary/70"
        )}
      >
        <span className="w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-sm"
          style={{ backgroundColor: brandColor }}>
          <ProviderIcon type={pt.type} size={18} />
        </span>
        <span className={cn("text-[11px] font-medium leading-tight", isSelected ? "text-accent-primary" : "text-text-primary")}>
          {pt.name}
        </span>
      </button>
    )
  }

  return (
    <div className="space-y-2">
      {label && <label className="block text-sm font-medium text-text-primary">{label}</label>}

      {/* Search */}
      {providers.length > 6 && (
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
          <input
            type="text"
            className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent-primary transition-colors"
            placeholder={t('common.search') + '...'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      )}

      {/* Grid */}
      <div className="max-h-80 overflow-y-auto space-y-2 pr-1 scrollbar-thin">
        {/* Manual & RFC2136 — always visible on top when not searching */}
        {search === '' && (manualProvider || rfc2136Provider) && (
          <div className="grid grid-cols-3 gap-2">
            {manualProvider && renderCard(manualProvider)}
            {rfc2136Provider && renderCard(rfc2136Provider)}
          </div>
        )}
        {search === '' && popularProviders.length > 0 && (
          <>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">{t('common.popular', 'Popular')}</p>
            <div className="grid grid-cols-3 gap-2">
              {popularProviders.map(renderCard)}
            </div>
          </>
        )}
        {search === '' && otherProviders.length > 0 && (
          <>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary pt-1">{t('common.other', 'Other')}</p>
            <div className="grid grid-cols-3 gap-2">
              {otherProviders.map(renderCard)}
            </div>
          </>
        )}
        {search !== '' && (
          <div className="grid grid-cols-3 gap-2">
            {filtered.map(renderCard)}
          </div>
        )}
        {filtered.length === 0 && (
          <p className="text-xs text-text-tertiary text-center py-4">{t('common.noResults', 'No results')}</p>
        )}
      </div>
    </div>
  )
}

// DNS Provider Form Component
function DnsProviderForm({ provider, providerTypes, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    provider_type: provider?.provider_type || 'manual',
    credentials: {},  // Always start empty - backend will merge
    is_default: provider?.is_default || false
  })
  
  // Track which credentials already exist (from credential_keys)
  const existingCredentialKeys = provider?.credential_keys || []
  
  const selectedType = providerTypes.find(pt => pt.type === formData.provider_type)
  
  const handleSubmit = (e) => {
    e.preventDefault()
    
    if (!formData.name.trim()) {
      showWarning(t('acme.providerNameRequired'))
      return
    }
    
    // Validate required credentials using schema
    // Only check if it's a NEW provider or if the field is not already set
    if (selectedType?.credentials_schema && !provider) {
      const missing = selectedType.credentials_schema
        .filter(field => field.required && !formData.credentials[field.name])
        .map(field => field.label)
      if (missing.length > 0) {
        showWarning(t('acme.missingCredentials', { fields: missing.join(', ') }))
        return
      }
    }
    
    onSubmit({
      ...formData,
      credentials: JSON.stringify(formData.credentials)
    })
  }
  
  const updateCredential = (key, value) => {
    setFormData(prev => ({
      ...prev,
      credentials: { ...prev.credentials, [key]: value }
    }))
  }
  
  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('common.providerName')}
        value={formData.name}
        onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
        required
        placeholder={t('acme.providerNamePlaceholder')}
      />
      
      <ProviderTypeGrid
        label={t('common.providerType')}
        providers={providerTypes}
        value={formData.provider_type}
        onChange={(val) => setFormData(prev => ({ ...prev, provider_type: val, credentials: {} }))}
        disabled={!!provider}
      />
      
      {/* Dynamic credential fields based on provider type schema */}
      {selectedType?.credentials_schema?.length > 0 && (
        <div className="space-y-3 p-3 bg-bg-tertiary/50 rounded-lg">
          <p className="text-sm font-medium text-text-secondary">{t('acme.credentials')}</p>
          {selectedType.credentials_schema.map(field => {
            const hasExistingValue = existingCredentialKeys.includes(field.name)
            const isPasswordType = field.type === 'password'
            
            return (
              <div key={field.name}>
                {field.type === 'select' ? (
                  <Select
                    label={field.label}
                    value={formData.credentials[field.name] || field.default || ''}
                    onChange={(val) => updateCredential(field.name, val)}
                    options={field.options || []}
                    required={field.required && !hasExistingValue}
                  />
                ) : (
                  <Input
                    label={field.label}
                    type={isPasswordType ? 'password' : 'text'}
                    autoComplete={isPasswordType ? 'new-password' : 'off'}
                    value={formData.credentials[field.name] || ''}
                    onChange={(e) => updateCredential(field.name, e.target.value)}
                    required={field.required}
                    placeholder={field.placeholder}
                    hasExistingValue={hasExistingValue}
                    helperText={field.help}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
      
      {formData.provider_type === 'manual' && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <p className="text-sm text-text-secondary">{t('acme.manualDnsInfo')}</p>
        </div>
      )}
      
      <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
        <input
          type="checkbox"
          checked={formData.is_default}
          onChange={(e) => setFormData(prev => ({ ...prev, is_default: e.target.checked }))}
          className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
        />
        <span className="text-sm text-text-primary">{t('acme.setAsDefault')}</span>
      </label>
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <FloppyDisk size={14} />
          {provider ? t('common.update') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}

// Domain Form Component
function DomainForm({ domain, dnsProviders, cas, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    domain: domain?.domain || '',
    dns_provider_id: domain?.dns_provider_id || (dnsProviders[0]?.id || ''),
    issuing_ca_id: domain?.issuing_ca_id || '',
    is_wildcard_allowed: domain?.is_wildcard_allowed ?? true,
    auto_approve: domain?.auto_approve ?? true,
  })

  // Filter CAs that have private keys (can sign)
  const signingCas = (cas || []).filter(ca => ca.has_private_key)

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      ...formData,
      issuing_ca_id: formData.issuing_ca_id || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('acme.domainName')}
        value={formData.domain}
        onChange={(e) => setFormData(prev => ({ ...prev, domain: e.target.value.toLowerCase() }))}
        required
        placeholder="example.com"
        helperText={t('acme.domainNameHelper')}
        disabled={!!domain}
      />
      
      <Select
        label={t('acme.provider')}
        value={formData.dns_provider_id}
        onChange={(val) => setFormData(prev => ({ ...prev, dns_provider_id: parseInt(val) }))}
        options={dnsProviders.map(p => ({
          value: p.id,
          label: `${p.name} (${p.provider_type})`
        }))}
        required
      />

      <Select
        label={t('acme.issuingCA')}
        value={formData.issuing_ca_id}
        onChange={(val) => setFormData(prev => ({ ...prev, issuing_ca_id: val ? parseInt(val) : '' }))}
        options={[
          { value: '', label: t('acme.useDefaultCA') },
          ...signingCas.map(ca => ({
            value: ca.id,
            label: ca.common_name || ca.descr || `CA #${ca.id}`
          }))
        ]}
      />

      <ToggleSwitch
        checked={formData.is_wildcard_allowed}
        onChange={(val) => setFormData(prev => ({ ...prev, is_wildcard_allowed: val }))}
        label={t('acme.allowWildcard')}
        description={t('acme.allowWildcardDesc')}
      />

      <ToggleSwitch
        checked={formData.auto_approve}
        onChange={(val) => setFormData(prev => ({ ...prev, auto_approve: val }))}
        label={t('acme.autoApproveRequests')}
        description={t('acme.autoApproveDesc')}
      />
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <FloppyDisk size={14} />
          {domain ? t('common.update') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}


function LocalDomainForm({ domain, cas, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    domain: domain?.domain || '',
    issuing_ca_id: domain?.issuing_ca_id || '',
    auto_approve: domain?.auto_approve ?? true,
  })

  const signingCas = (cas || []).filter(ca => ca.has_private_key)

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      ...formData,
      issuing_ca_id: formData.issuing_ca_id ? parseInt(formData.issuing_ca_id) : null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('acme.domainName')}
        value={formData.domain}
        onChange={(e) => setFormData(prev => ({ ...prev, domain: e.target.value.toLowerCase() }))}
        required
        placeholder="example.com"
        helperText={t('acme.localDomainHelper')}
        disabled={!!domain}
      />

      <Select
        label={t('acme.issuingCA')}
        value={formData.issuing_ca_id}
        onChange={(val) => setFormData(prev => ({ ...prev, issuing_ca_id: val }))}
        options={signingCas.map(ca => ({
          value: ca.id,
          label: ca.common_name || ca.descr || `CA #${ca.id}`
        }))}
        required
      />

      <ToggleSwitch
        checked={formData.auto_approve}
        onChange={(val) => setFormData(prev => ({ ...prev, auto_approve: val }))}
        label={t('acme.autoApproveRequests')}
        description={t('acme.autoApproveDesc')}
      />

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <FloppyDisk size={14} />
          {domain ? t('common.update') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}
