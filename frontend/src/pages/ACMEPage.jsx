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
import { 
  Key, Plus, Trash, CheckCircle, XCircle, FloppyDisk, ShieldCheck, 
  Globe, Lightning, MagnifyingGlass, Database, Gear, ListBullets,
  ArrowsClockwise, Copy, Question
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Badge, Card, Input, Modal, Select, HelpCard,
  LoadingSpinner, EmptyState, StatusIndicator,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { acmeService, casService } from '../services'
import { useNotification } from '../contexts'
import { formatDate } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'

export default function ACMEPage() {
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  
  // Data states
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [orders, setOrders] = useState([])
  const [challenges, setChallenges] = useState([])
  const [acmeSettings, setAcmeSettings] = useState({})
  const [cas, setCas] = useState([])
  
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

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [accountsRes, settingsRes, casRes] = await Promise.all([
        acmeService.getAccounts(),
        acmeService.getSettings(),
        casService.getAll()
      ])
      setAccounts(accountsRes.data || accountsRes.accounts || [])
      setAcmeSettings(settingsRes.data || settingsRes || {})
      setCas(casRes.data || casRes.cas || [])
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
      showSuccess('Proxy account registered successfully')
      setProxyEmail('')
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to register proxy account')
    }
  }

  const handleUnregisterProxy = async () => {
    const confirmed = await showConfirm('Unregister Let\'s Encrypt proxy account?')
    if (!confirmed) return
    try {
      await acmeService.unregisterProxy()
      showSuccess('Proxy account unregistered successfully')
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to unregister proxy account')
    }
  }

  // Account handlers
  const handleCreate = async (data) => {
    try {
      const created = await acmeService.createAccount(data)
      showSuccess('ACME account created successfully')
      setShowCreateModal(false)
      loadData()
      selectAccount(created)
    } catch (error) {
      showError(error.message || 'Failed to create ACME account')
    }
  }

  const handleDeactivate = async (id) => {
    const confirmed = await showConfirm('Deactivate this ACME account?', {
      title: 'Deactivate Account',
      confirmText: 'Deactivate',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await acmeService.deactivateAccount(id)
      showSuccess('Account deactivated successfully')
      setSelectedAccount(null)
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to deactivate account')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Delete this ACME account?', {
      title: 'Delete Account',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await acmeService.deleteAccount(id)
      showSuccess(SUCCESS.DELETE.GENERIC || 'Account deleted successfully')
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
      label: 'Email',
      render: (_, row) => (
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 bg-blue-500/15 text-blue-500">
            <Key size={14} weight="duotone" />
          </div>
          <span className="font-medium text-text-primary">
            {row.contact?.[0]?.replace('mailto:', '') || row.email || `Account #${row.id}`}
          </span>
        </div>
      )
    },
    {
      key: 'status',
      label: 'Status',
      render: (val) => (
        <Badge variant={val === 'valid' ? 'success' : 'orange'} size="sm" dot pulse={val === 'valid'}>
          {val === 'valid' && <CheckCircle size={10} weight="fill" />}
          {val}
        </Badge>
      )
    },
    {
      key: 'created_at',
      label: 'Created',
      render: (val) => formatDate(val)
    }
  ], [])

  // Main tabs
  const tabs = [
    { id: 'config', label: 'Configuration', icon: Gear },
    { id: 'accounts', label: 'Accounts', icon: Key, count: accounts.length }
  ]

  // Detail tabs (when account selected)
  const detailTabs = [
    { id: 'account', label: 'Details', icon: Key },
    { id: 'orders', label: 'Orders', icon: Globe, count: orders.length },
    { id: 'challenges', label: 'Challenges', icon: ShieldCheck, count: challenges.length }
  ]

  // Header actions
  const headerActions = (
    <>
      <Button variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
        Refresh
      </Button>
      {activeTab === 'accounts' && (
        <Button size="sm" onClick={() => setShowCreateModal(true)}>
          <Plus size={14} />
          <span className="hidden sm:inline">New Account</span>
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
          ACME Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
            <p className="text-xs text-text-secondary">Accounts</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-success-text">{stats.active}</p>
            <p className="text-xs text-text-secondary">Active</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-accent-primary">{stats.orders}</p>
            <p className="text-xs text-text-secondary">Orders</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-warning-text">{stats.pending}</p>
            <p className="text-xs text-text-secondary">Pending</p>
          </div>
        </div>
      </Card>

      <Card className={`p-4 space-y-3 ${acmeSettings.enabled ? 'stat-card-success' : 'stat-card-warning'}`}>
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Lightning size={16} className="text-accent-primary" />
          Server Status
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">ACME Server</span>
            <StatusIndicator status={acmeSettings.enabled ? 'success' : 'warning'}>
              {acmeSettings.enabled ? 'Enabled' : 'Disabled'}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">LE Proxy</span>
            <StatusIndicator status={acmeSettings.proxy_enabled ? (acmeSettings.proxy_registered ? 'success' : 'warning') : 'inactive'}>
              {acmeSettings.proxy_enabled ? (acmeSettings.proxy_registered ? 'Active' : 'Setup Required') : 'Disabled'}
            </StatusIndicator>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        <HelpCard variant="info" title="About ACME">
          ACME (Automatic Certificate Management Environment) enables automated certificate 
          issuance. Compatible with certbot, acme.sh, and other ACME clients.
        </HelpCard>
        
        <HelpCard variant="tip" title="Let's Encrypt Proxy">
          Enable the LE Proxy to forward requests to Let's Encrypt while maintaining 
          centralized audit logging and control.
        </HelpCard>

        <HelpCard variant="warning" title="Account Security">
          ACME accounts contain private keys. Deactivate or delete unused accounts 
          to minimize security exposure.
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
        title={selectedAccount.contact?.[0]?.replace('mailto:', '') || selectedAccount.email || 'Account'}
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
        { icon: Globe, value: `${orders.length} orders` },
        { icon: ShieldCheck, value: `${challenges.length} challenges` },
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
          Deactivate
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
              <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-bg-tertiary">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeDetailTab === 'account' && (
        <div className="space-y-3">
          <CompactSection title="Account Information">
            <CompactGrid>
              <CompactField label="Email" value={selectedAccount.contact?.[0]?.replace('mailto:', '') || selectedAccount.email} />
              <CompactField label="Status">
                <StatusIndicator status={selectedAccount.status === 'valid' ? 'active' : 'inactive'}>
                  {selectedAccount.status}
                </StatusIndicator>
              </CompactField>
              <CompactField label="Key Type" value={selectedAccount.key_type || 'RSA-2048'} />
              <CompactField label="Created" value={formatDate(selectedAccount.created_at)} />
            </CompactGrid>
          </CompactSection>

          <CompactSection title="Account ID" collapsible defaultOpen={false}>
            <p className="font-mono text-[10px] text-text-secondary break-all bg-bg-tertiary/50 p-2 rounded">
              {selectedAccount.account_id}
            </p>
          </CompactSection>

          <CompactSection title="Terms of Service">
            <div className="flex items-center gap-2 text-xs">
              {selectedAccount.terms_of_service_agreed || selectedAccount.tos_agreed ? (
                <>
                  <CheckCircle size={14} className="status-success-text" weight="fill" />
                  <span className="status-success-text">Accepted</span>
                </>
              ) : (
                <>
                  <XCircle size={14} className="status-danger-text" weight="fill" />
                  <span className="status-danger-text">Not Accepted</span>
                </>
              )}
            </div>
          </CompactSection>
        </div>
      )}

      {activeDetailTab === 'orders' && (
        <CompactSection title={`${orders.length} Orders`}>
          {orders.length === 0 ? (
            <p className="text-xs text-text-tertiary py-4 text-center">No certificate orders</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {orders.map((order, i) => (
                <div key={i} className="flex items-center justify-between p-2 bg-bg-tertiary/30 rounded text-xs">
                  <span className="text-text-primary truncate flex-1">{order.domain || order.identifier}</span>
                  <Badge variant={order.status === 'valid' ? 'success' : 'warning'} size="sm">
                    {order.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      )}

      {activeDetailTab === 'challenges' && (
        <CompactSection title={`${challenges.length} Challenges`}>
          {challenges.length === 0 ? (
            <p className="text-xs text-text-tertiary py-4 text-center">No active challenges</p>
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
      <HelpCard variant="info" title="About ACME Protocol" compact>
        ACME enables automated certificate issuance. Configure the server below, then use 
        the directory URL with any ACME client (certbot, acme.sh, etc.).
      </HelpCard>

      {/* ACME Server */}
      <CompactSection title="ACME Server" icon={Globe}>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
            <input
              type="checkbox"
              checked={acmeSettings.enabled || false}
              onChange={(e) => updateSetting('enabled', e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
            />
            <div>
              <p className="text-sm text-text-primary font-medium">Enable ACME Server</p>
              <p className="text-xs text-text-secondary">Allow automated certificate issuance via ACME</p>
            </div>
          </label>

          <Select
            label="Default Issuing CA"
            value={acmeSettings.issuing_ca_id?.toString() || ''}
            onChange={(val) => updateSetting('issuing_ca_id', val ? parseInt(val) : null)}
            disabled={!acmeSettings.enabled}
            placeholder="Select a CA..."
            options={cas.map(ca => ({ 
              value: ca.id.toString(), 
              label: ca.name || ca.common_name 
            }))}
          />
        </div>
      </CompactSection>

      {/* ACME Endpoints */}
      <CompactSection title="ACME Endpoints" icon={Lightning}>
        <CompactGrid columns={1}>
          <CompactField 
            label="Directory URL" 
            value={`${window.location.origin}/acme/directory`}
            mono
            copyable
          />
        </CompactGrid>
        <p className="text-xs text-text-tertiary mt-2">
          Use this URL with certbot: <code className="bg-bg-tertiary px-1 rounded">--server {window.location.origin}/acme/directory</code>
        </p>
      </CompactSection>

      {/* Let's Encrypt Proxy */}
      <CompactSection title="Let's Encrypt Proxy" icon={ShieldCheck}>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
            <input
              type="checkbox"
              checked={acmeSettings.proxy_enabled || false}
              onChange={(e) => updateSetting('proxy_enabled', e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
            />
            <div>
              <p className="text-sm text-text-primary font-medium">Enable Let's Encrypt Proxy</p>
              <p className="text-xs text-text-secondary">Forward requests to Let's Encrypt with audit logging</p>
            </div>
          </label>

          {acmeSettings.proxy_enabled && (
            <>
              <CompactGrid columns={1}>
                <CompactField 
                  label="Proxy Endpoint" 
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
                        <p className="text-sm font-medium text-text-primary">Proxy Registered</p>
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
                    label="Email Address"
                    type="email"
                    value={proxyEmail}
                    onChange={(e) => setProxyEmail(e.target.value)}
                    placeholder="admin@example.com"
                    helperText="Required for Let's Encrypt account registration"
                  />
                  <Button 
                    variant="secondary" 
                    size="sm"
                    onClick={handleRegisterProxy}
                    disabled={!proxyEmail}
                  >
                    <Key size={14} />
                    Register Account
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
          {saving ? 'Saving...' : 'Save Configuration'}
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
      searchPlaceholder="Search accounts..."
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
        title: 'No ACME Accounts',
        description: searchQuery ? 'No accounts match your search' : 'Create your first ACME account to get started',
        action: !searchQuery && (
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus size={14} />
            Create Account
          </Button>
        )
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
        title="ACME Protocol"
        subtitle={`${accounts.length} account${accounts.length !== 1 ? 's' : ''}`}
        icon={Lightning}
        stats={[
          { icon: Key, label: 'Accounts', value: accounts.length },
          { icon: CheckCircle, label: 'Active', value: stats.active, variant: 'success' },
          { icon: Globe, label: 'Orders', value: stats.orders, variant: 'primary' },
        ]}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab)
          if (tab === 'config') {
            setSelectedAccount(null)
          }
        }}
        actions={headerActions}
        helpContent={helpContent}
        helpTitle="ACME Help"
        
        // Split view for accounts tab
        splitView={activeTab === 'accounts'}
        slideOverOpen={!!selectedAccount}
        slideOverTitle={selectedAccount?.email || 'Account Details'}
        slideOverContent={accountDetailContent}
        onSlideOverClose={() => setSelectedAccount(null)}
      >
        {activeTab === 'config' ? configContent : accountsContent}
      </ResponsiveLayout>

      {/* Create Account Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create ACME Account"
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
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    email: '',
    key_type: 'RSA-2048',
    agree_tos: false,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!formData.agree_tos) {
      showWarning('You must agree to the Terms of Service')
      return
    }
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label="Email Address"
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText="Contact email for certificate expiry notifications"
      />
      
      <Select
        label="Key Type"
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
          I agree to the ACME Terms of Service
        </span>
      </label>
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">
          <Plus size={14} />
          Create Account
        </Button>
      </div>
    </form>
  )
}
