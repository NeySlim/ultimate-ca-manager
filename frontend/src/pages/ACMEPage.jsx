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
  ArrowsClockwise
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Badge, Card, Input, Modal, Select, HelpCard,
  LoadingSpinner, StatusIndicator,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { acmeService, casService } from '../services'
import { useNotification } from '../contexts'
import { formatDate, cn } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'

export default function ACMEPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  
  // Data states
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [selectedCert, setSelectedCert] = useState(null)
  const [orders, setOrders] = useState([])
  const [challenges, setChallenges] = useState([])
  const [acmeSettings, setAcmeSettings] = useState({})
  const [cas, setCas] = useState([])
  const [history, setHistory] = useState([])
  
  // UI states
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('config')
  const [activeDetailTab, setActiveDetailTab] = useState('account')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [proxyEmail, setProxyEmail] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // History filters
  const [historyFilterStatus, setHistoryFilterStatus] = useState('')
  const [historyFilterCA, setHistoryFilterCA] = useState('')

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [accountsRes, settingsRes, casRes, historyRes] = await Promise.all([
        acmeService.getAccounts(),
        acmeService.getSettings(),
        casService.getAll(),
        acmeService.getHistory()
      ])
      setAccounts(accountsRes.data || accountsRes.accounts || [])
      setAcmeSettings(settingsRes.data || settingsRes || {})
      setCas(casRes.data || casRes.cas || [])
      setHistory(historyRes.data || [])
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
      title: t('acme.deactivateAccount'),
      confirmText: t('acme.deactivate'),
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
      title: t('acme.deleteAccount'),
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
      header: t('acme.email'),
      priority: 1,
      render: (_, row) => (
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-blue">
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
            <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-blue">
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
      header: t('acme.status'),
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
      header: t('acme.created'),
      priority: 3,
      hideOnMobile: true,
      render: (val) => formatDate(val),
      mobileRender: (val) => (
        <div className="text-xs text-text-tertiary">
          {t('acme.created')}: <span className="text-text-secondary">{formatDate(val)}</span>
        </div>
      )
    }
  ], [t])

  // Main tabs
  const tabs = [
    { id: 'config', label: t('acme.config'), icon: Gear },
    { id: 'accounts', label: t('acme.accounts'), icon: Key, count: accounts.length },
    { id: 'history', label: t('acme.history'), icon: ClockCounterClockwise, count: history.length }
  ]

  // Detail tabs (when account selected)
  const detailTabs = [
    { id: 'account', label: t('acme.details'), icon: Key },
    { id: 'orders', label: t('acme.orders'), icon: Globe, count: orders.length },
    { id: 'challenges', label: t('acme.challenges'), icon: ShieldCheck, count: challenges.length }
  ]

  // Header actions
  const headerActions = (
    <>
      <Button variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
        {t('acme.refresh')}
      </Button>
      {activeTab === 'accounts' && (
        <Button size="sm" onClick={() => setShowCreateModal(true)}>
          <Plus size={14} />
          <span className="hidden sm:inline">{t('acme.newAccount')}</span>
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
            <p className="text-xs text-text-secondary">{t('acme.active')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-accent-primary">{stats.orders}</p>
            <p className="text-xs text-text-secondary">{t('acme.orders')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-warning-text">{stats.pending}</p>
            <p className="text-xs text-text-secondary">{t('acme.pending')}</p>
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
              {acmeSettings.enabled ? t('acme.enabled') : t('acme.disabled')}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{t('acme.leProxy')}</span>
            <StatusIndicator status={acmeSettings.proxy_enabled ? (acmeSettings.proxy_registered ? 'success' : 'warning') : 'inactive'}>
              {acmeSettings.proxy_enabled ? (acmeSettings.proxy_registered ? t('acme.active') : t('acme.setupRequired')) : t('acme.disabled')}
            </StatusIndicator>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        <HelpCard variant="info" title={t('acme.aboutAcme')}>
          {t('acme.aboutAcmeInfo')}
        </HelpCard>
        
        <HelpCard variant="tip" title={t('acme.letsEncryptProxy')}>
          {t('acme.letsEncryptProxyTip')}
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
        { icon: ShieldCheck, value: `${challenges.length} ${t('acme.challenges').toLowerCase()}` },
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
          {t('acme.deactivate')}
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
          <CompactSection title={t('acme.accountInformation')}>
            <CompactGrid>
              <CompactField label={t('acme.email')} value={selectedAccount.contact?.[0]?.replace('mailto:', '') || selectedAccount.email} />
              <CompactField label={t('acme.status')}>
                <StatusIndicator status={selectedAccount.status === 'valid' ? 'active' : 'inactive'}>
                  {selectedAccount.status}
                </StatusIndicator>
              </CompactField>
              <CompactField label={t('acme.keyType')} value={selectedAccount.key_type || 'RSA-2048'} />
              <CompactField label={t('acme.created')} value={formatDate(selectedAccount.created_at)} />
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
                      <span className="text-text-tertiary">{t('acme.expires')}</span>
                      <span className="text-text-secondary">{order.expires || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between col-span-2">
                      <span className="text-text-tertiary">{t('acme.created')}</span>
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
        <CompactSection title={`${challenges.length} ${t('acme.challenges')}`}>
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

  // Configuration content
  const configContent = (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.aboutAcme')} compact>
        {t('acme.aboutAcmeDesc')}
      </HelpCard>

      {/* ACME Server */}
      <CompactSection title={t('acme.acmeServer')} icon={Globe}>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
            <input
              type="checkbox"
              checked={acmeSettings.enabled || false}
              onChange={(e) => updateSetting('enabled', e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
            />
            <div>
              <p className="text-sm text-text-primary font-medium">{t('acme.enableAcmeServer')}</p>
              <p className="text-xs text-text-secondary">{t('acme.enableAcmeServerDesc')}</p>
            </div>
          </label>

          <Select
            label={t('acme.defaultIssuingCA')}
            value={acmeSettings.issuing_ca_id?.toString() || ''}
            onChange={(val) => updateSetting('issuing_ca_id', val ? parseInt(val) : null)}
            disabled={!acmeSettings.enabled}
            placeholder={t('acme.selectCA')}
            options={cas.map(ca => ({ 
              value: ca.id.toString(), 
              label: ca.name || ca.common_name 
            }))}
          />
        </div>
      </CompactSection>

      {/* ACME Endpoints */}
      <CompactSection title={t('acme.endpoints')} icon={Lightning}>
        <CompactGrid columns={1}>
          <CompactField 
            label={t('acme.directoryUrl')} 
            value={`${window.location.origin}/acme/directory`}
            mono
            copyable
          />
        </CompactGrid>
        <p className="text-xs text-text-tertiary mt-2">
          {t('acme.certbotUsage')} <code className="bg-bg-tertiary px-1 rounded">--server {window.location.origin}/acme/directory</code>
        </p>
      </CompactSection>

      {/* Let's Encrypt Proxy */}
      <CompactSection title={t('acme.letsEncryptProxy')} icon={ShieldCheck}>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
            <input
              type="checkbox"
              checked={acmeSettings.proxy_enabled || false}
              onChange={(e) => updateSetting('proxy_enabled', e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
            />
            <div>
              <p className="text-sm text-text-primary font-medium">{t('acme.enableLetsEncryptProxy')}</p>
              <p className="text-xs text-text-secondary">{t('acme.enableLetsEncryptProxyDesc')}</p>
            </div>
          </label>

          {acmeSettings.proxy_enabled && (
            <>
              <CompactGrid columns={1}>
                <CompactField 
                  label={t('acme.proxyEndpoint')} 
                  value={`${window.location.origin}/api/v2/acme/proxy`}
                  mono
                  copyable
                />
              </CompactGrid>
              
              {acmeSettings.proxy_registered ? (
                <div className="p-3 rounded-lg status-success-bg status-success-border border">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={18} className="status-success-text" weight="fill" />
                      <div>
                        <p className="text-sm font-medium text-text-primary">{t('acme.proxyRegistered')}</p>
                        <p className="text-xs text-text-secondary">{acmeSettings.proxy_email}</p>
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
                    label={t('acme.emailAddress')}
                    type="email"
                    value={proxyEmail}
                    onChange={(e) => setProxyEmail(e.target.value)}
                    placeholder={t('acme.emailPlaceholder')}
                    helperText={t('acme.emailRequired')}
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

      {/* Save Button */}
      <div className="flex gap-2 pt-3 border-t border-border">
        <Button onClick={handleSaveConfig} disabled={saving}>
          <FloppyDisk size={14} />
          {saving ? t('acme.saving') : t('acme.saveConfiguration')}
        </Button>
      </div>
    </div>
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
      header: t('acme.commonName'),
      priority: 1,
      sortable: true,
      render: (value, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
            row?.revoked ? "icon-bg-red" : "icon-bg-blue"
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
              row?.revoked ? "icon-bg-red" : "icon-bg-blue"
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
            {row?.revoked ? t('acme.revoked') : t('acme.valid')}
          </Badge>
        </div>
      )
    },
    {
      key: 'revoked',
      header: t('acme.status'),
      priority: 2,
      hideOnMobile: true,
      render: (value) => (
        <Badge 
          variant={value ? 'danger' : 'success'} 
          size="sm"
          icon={value ? XCircle : CheckCircle}
          dot
          pulse={!value}
        >
          {value ? t('acme.revoked') : t('acme.valid')}
        </Badge>
      )
    },
    {
      key: 'issuer',
      header: t('acme.issuer'),
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
      header: t('acme.expires'),
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
                {isExpired ? t('acme.expired') : t('acme.daysLeft', { count: daysLeft })}
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
              {isExpired ? t('acme.expired') : `${daysLeft}d`}
            </span>
          </div>
        )
      }
    },
    {
      key: 'created_at',
      header: t('acme.issued'),
      priority: 5,
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
        subtitle={`${t('acme.issuer')}: ${selectedCert.issuer || t('acme.unknownCA')}`}
        badge={
          <Badge variant={selectedCert.revoked ? 'danger' : 'success'} size="sm">
            {!selectedCert.revoked && <CheckCircle size={10} weight="fill" />}
            {selectedCert.revoked ? t('acme.revoked') : t('acme.valid')}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Key, value: selectedCert.order?.account || t('common.unknown') },
        { icon: Globe, value: selectedCert.order?.status || t('common.na') },
      ]} />
      
      <CompactSection title={t('acme.certificateDetails')}>
        <CompactGrid>
          <CompactField label={t('acme.commonName')} value={selectedCert.common_name} copyable />
          <CompactField label={t('acme.serialNumber')} value={selectedCert.serial} mono copyable />
          <CompactField label={t('acme.issuer')} value={selectedCert.issuer || t('common.unknown')} />
        </CompactGrid>
      </CompactSection>
      
      <CompactSection title={t('acme.validity')}>
        <CompactGrid>
          <CompactField label={t('acme.validFrom')} value={selectedCert.valid_from ? formatDate(selectedCert.valid_from) : t('common.na')} />
          <CompactField label={t('acme.validTo')} value={selectedCert.valid_to ? formatDate(selectedCert.valid_to) : t('common.na')} />
          <CompactField label={t('acme.issued')} value={selectedCert.created_at ? formatDate(selectedCert.created_at) : t('common.na')} />
        </CompactGrid>
      </CompactSection>
      
      {selectedCert.order && (
        <CompactSection title={t('acme.acmeOrder')}>
          <CompactGrid>
            <CompactField label={t('acme.account')} value={selectedCert.order.account} />
            <CompactField label={t('acme.orderStatus')} value={selectedCert.order.status} />
            <CompactField label={t('acme.orderId')} value={selectedCert.order.order_id} mono copyable />
          </CompactGrid>
        </CompactSection>
      )}
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
    return filtered
  }, [history, historyFilterStatus, historyFilterCA])

  // Get unique CAs from history for filter
  const historyCAs = useMemo(() => {
    const cas = [...new Set(history.map(c => c.issuer).filter(Boolean))]
    return cas.map(ca => ({ value: ca, label: ca }))
  }, [history])
  
  const historyContent = (
    <ResponsiveDataTable
      data={filteredHistory}
      columns={historyColumns}
      searchable
      searchPlaceholder={t('acme.searchCertificates')}
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
          key: 'status',
          value: historyFilterStatus,
          onChange: setHistoryFilterStatus,
          placeholder: t('acme.allStatus'),
          options: [
            { value: 'valid', label: t('acme.valid') },
            { value: 'revoked', label: t('acme.revoked') }
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
        subtitle={`${accounts.length} ${t('acme.account')}${accounts.length !== 1 ? 's' : ''}`}
        icon={Lightning}
        stats={[
          { icon: Key, label: t('acme.accounts'), value: accounts.length },
          { icon: CheckCircle, label: t('acme.active'), value: stats.active, variant: 'success' },
          { icon: ClockCounterClockwise, label: t('acme.certificates'), value: history.length, variant: 'primary' },
        ]}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab)
          if (tab === 'config') {
            setSelectedAccount(null)
            setSelectedCert(null)
          } else if (tab === 'accounts') {
            setSelectedCert(null)
          } else if (tab === 'history') {
            setSelectedAccount(null)
          }
        }}
        actions={headerActions}
        helpPageKey="acme"
        
        // Split view for accounts and history tabs
        splitView={activeTab === 'accounts' || activeTab === 'history'}
        slideOverOpen={activeTab === 'accounts' ? !!selectedAccount : !!selectedCert}
        slideOverTitle={
          activeTab === 'accounts' 
            ? (selectedAccount?.email || t('acme.details'))
            : (selectedCert?.common_name || t('acme.certificateDetails'))
        }
        slideOverContent={activeTab === 'accounts' ? accountDetailContent : certDetailContent}
        onSlideOverClose={() => {
          if (activeTab === 'accounts') {
            setSelectedAccount(null)
          } else {
            setSelectedCert(null)
          }
        }}
      >
        {activeTab === 'config' && configContent}
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
        label={t('acme.emailAddress')}
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText={t('acme.contactEmailHelper')}
      />
      
      <Select
        label={t('acme.keyType')}
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
          {t('acme.cancel')}
        </Button>
        <Button type="submit">
          <Plus size={14} />
          {t('acme.createAccount')}
        </Button>
      </div>
    </form>
  )
}
