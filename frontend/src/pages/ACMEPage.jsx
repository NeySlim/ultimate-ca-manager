/**
 * ACME Page - Using PageLayout
 * ACME Protocol management for automated certificate issuance
 */
import { useState, useEffect } from 'react'
import { 
  Key, Plus, Trash, CheckCircle, XCircle, FloppyDisk, ShieldCheck, 
  Globe, Lightning, MagnifyingGlass, Database
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Table, Button, Badge, Card,
  Input, Modal, Tabs, Select, HelpCard,
  LoadingSpinner, EmptyState, StatusIndicator,
  ContentHeader, ContentBody, ResponsiveContentSection as ContentSection, 
  DataGrid, DataField, TabsResponsive, DetailTabs,
  DetailSection, DetailGrid, DetailField,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { acmeService, casService } from '../services'
import { useNotification } from '../contexts'

export default function ACMEPage() {
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [orders, setOrders] = useState([])
  const [challenges, setChallenges] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [acmeSettings, setAcmeSettings] = useState({})
  const [cas, setCas] = useState([])
  const [proxyEmail, setProxyEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    loadAccounts()
    loadAcmeSettings()
    loadCAs()
  }, [])

  const loadCAs = async () => {
    try {
      const data = await casService.getAll()
      setCas(data.data || data.cas || [])
    } catch (error) {
      // Silent fail
    }
  }

  const loadAcmeSettings = async () => {
    try {
      const response = await acmeService.getSettings()
      setAcmeSettings(response.data || response || {})
    } catch (error) {
      // Silent fail
    }
  }

  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      await acmeService.updateSettings(acmeSettings)
      showSuccess('ACME settings saved successfully')
    } catch (error) {
      showError(error.message || 'Failed to save ACME settings')
    } finally {
      setSaving(false)
    }
  }

  const handleRegisterProxy = async () => {
    if (!proxyEmail) {
      showError('Email is required')
      return
    }
    try {
      await acmeService.registerProxy(proxyEmail)
      showSuccess('Proxy account registered successfully')
      setProxyEmail('')
      loadAcmeSettings()
    } catch (error) {
      showError(error.message || 'Failed to register proxy account')
    }
  }

  const handleUnregisterProxy = async () => {
    const confirmed = await showConfirm('Are you sure you want to unregister the proxy account?')
    if (!confirmed) return
    
    try {
      await acmeService.unregisterProxy()
      showSuccess('Proxy account unregistered')
      loadAcmeSettings()
    } catch (error) {
      showError(error.message || 'Failed to unregister proxy account')
    }
  }

  const updateAcmeSetting = (key, value) => {
    setAcmeSettings(prev => ({ ...prev, [key]: value }))
  }

  const loadAccounts = async () => {
    setLoading(true)
    try {
      const data = await acmeService.getAccounts()
      setAccounts(data.accounts || [])
      if (data.accounts?.length > 0 && !selectedAccount) {
        selectAccount(data.accounts[0])
      }
    } catch (error) {
      showError(error.message || 'Failed to load ACME accounts')
    } finally {
      setLoading(false)
    }
  }

  const selectAccount = async (account) => {
    try {
      const [accountData, ordersData, challengesData] = await Promise.all([
        acmeService.getAccountById(account.id),
        acmeService.getOrders(account.id),
        acmeService.getChallenges(account.id),
      ])
      
      setSelectedAccount(accountData)
      setOrders(ordersData.orders || [])
      setChallenges(challengesData.challenges || [])
    } catch (error) {
      showError(error.message || 'Failed to load account details')
    }
  }

  const handleCreate = async (accountData) => {
    try {
      const created = await acmeService.createAccount(accountData)
      showSuccess('ACME account created successfully')
      setShowCreateModal(false)
      loadAccounts()
      selectAccount(created)
    } catch (error) {
      showError(error.message || 'Failed to create ACME account')
    }
  }

  const handleDeactivate = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to deactivate this ACME account?', {
      title: 'Deactivate Account',
      confirmText: 'Deactivate',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await acmeService.deactivateAccount(id)
      showSuccess('ACME account deactivated')
      loadAccounts()
    } catch (error) {
      showError(error.message || 'Failed to deactivate account')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to delete this ACME account?', {
      title: 'Delete Account',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await acmeService.deleteAccount(id)
      showSuccess('ACME account deleted')
      setSelectedAccount(null)
      loadAccounts()
    } catch (error) {
      showError(error.message || 'Failed to delete account')
    }
  }

  const orderColumns = [
    { key: 'domain', label: 'Domain' },
    {
      key: 'status',
      label: 'Status',
      render: (val) => <Badge variant={val === 'valid' ? 'success' : 'warning'}>{val}</Badge>
    },
    { key: 'created_at', label: 'Created', render: (val) => val ? new Date(val).toLocaleString() : '-' },
  ]

  const challengeColumns = [
    { key: 'type', label: 'Type', render: (val) => <Badge variant="secondary">{val}</Badge> },
    { key: 'domain', label: 'Domain' },
    {
      key: 'status',
      label: 'Status',
      render: (val) => (
        <Badge variant={
          val === 'valid' ? 'success' :
          val === 'pending' ? 'warning' :
          'danger'
        }>
          {val}
        </Badge>
      )
    },
    { key: 'validated_at', label: 'Validated', render: (val) => val ? new Date(val).toLocaleString() : '-' },
  ]

  const [activeDetailTab, setActiveDetailTab] = useState('account')

  // Note: Detail tabs content is now inline in the render below

  const configContent = (
    <div className="space-y-4 p-4">
      <HelpCard variant="info" title="About ACME Protocol" compact>
        ACME (Automatic Certificate Management Environment) enables automated certificate issuance. 
        Compatible with certbot, acme.sh, and other ACME clients.
      </HelpCard>

      {/* ACME Server Configuration */}
      <DetailSection title="ACME Server Configuration" icon={Globe}>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
            <input
              type="checkbox"
              checked={acmeSettings.enabled || false}
              onChange={(e) => updateAcmeSetting('enabled', e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
            />
            <div>
              <p className="text-sm text-text-primary font-medium">Enable ACME Server</p>
              <p className="text-xs text-text-secondary">Allow automated certificate issuance via ACME protocol</p>
            </div>
          </label>

          <Select
            label="Default CA for ACME"
            value={acmeSettings.issuing_ca_id?.toString() || undefined}
            onChange={(val) => updateAcmeSetting('issuing_ca_id', val ? parseInt(val) : null)}
            disabled={!acmeSettings.enabled}
            placeholder="Select a CA..."
            options={cas.map(ca => ({ value: ca.id.toString(), label: ca.name || ca.common_name || ca.descr }))}
          />
        </div>
      </DetailSection>

      {/* ACME Endpoints */}
      <DetailSection title="ACME Endpoints" icon={Lightning}>
        <DetailGrid columns={1}>
          <DetailField 
            label="ACME Directory URL" 
            value={`${window.location.origin}/acme/directory`}
            mono
            copyable
            fullWidth
            helperText="Use this URL with ACME clients like certbot or acme.sh"
          />
        </DetailGrid>
      </DetailSection>

      {/* Let's Encrypt Proxy */}
      <DetailSection title="Let's Encrypt Proxy" icon={ShieldCheck}>
        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
            <input
              type="checkbox"
              checked={acmeSettings.proxy_enabled || false}
              onChange={(e) => updateAcmeSetting('proxy_enabled', e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50"
            />
            <span className="text-sm font-medium text-text-primary">Enable Let's Encrypt Proxy</span>
          </label>

          {acmeSettings.proxy_enabled && (
            <>
              <DetailGrid columns={1}>
                <DetailField 
                  label="Proxy Endpoint URL" 
                  value={`${window.location.origin}/api/v2/acme/proxy`}
                  mono
                  copyable
                  fullWidth
                  helperText="External ACME clients can use this URL to proxy requests to Let's Encrypt"
                />
              </DetailGrid>
              
              {acmeSettings.proxy_registered ? (
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={18} className="text-emerald-500" weight="fill" />
                      <div>
                        <p className="text-sm font-medium text-text-primary">Proxy Account Registered</p>
                        <p className="text-xs text-text-secondary">{acmeSettings.proxy_email}</p>
                      </div>
                    </div>
                    <Button 
                      variant="ghost" 
                      size="sm"
                      onClick={handleUnregisterProxy}
                      className="text-red-500 hover:bg-red-500/10"
                    >
                      <Trash size={14} />
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <Input
                    label="Email Address"
                    type="email"
                    value={proxyEmail}
                    onChange={(e) => setProxyEmail(e.target.value)}
                    placeholder="admin@example.com"
                    helperText="Email for Let's Encrypt account registration"
                  />

                  <Button 
                    variant="secondary" 
                    size="sm"
                    onClick={handleRegisterProxy}
                    disabled={!proxyEmail}
                  >
                    <Key size={14} />
                    Register Proxy Account
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </DetailSection>

      <div className="flex gap-2 pt-3 border-t border-border">
        <Button size="sm" onClick={handleSaveConfig} disabled={saving}>
          <FloppyDisk size={14} />
          Save Configuration
        </Button>
      </div>
    </div>
  )

  // Stats computed from accounts
  const stats = {
    total: accounts.length,
    active: accounts.filter(a => a.status === 'valid').length,
    orders: orders.length,
    challenges: challenges.filter(c => c.status === 'pending').length
  }

  // Filtered accounts
  const filteredAccounts = accounts.filter(account => {
    const matchesSearch = !searchTerm || 
      account.email?.toLowerCase().includes(searchTerm.toLowerCase())
    const matchesStatus = statusFilter === 'all' || account.status === statusFilter
    return matchesSearch && matchesStatus
  })

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* ACME Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          ACME Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
            <p className="text-xs text-text-secondary">Total Accounts</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-success">{stats.active}</p>
            <p className="text-xs text-text-secondary">Active</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-accent-primary">{stats.orders}</p>
            <p className="text-xs text-text-secondary">Orders</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-warning">{stats.challenges}</p>
            <p className="text-xs text-text-secondary">Pending</p>
          </div>
        </div>
      </Card>

      {/* Server Status */}
      <Card className={`p-4 space-y-3 bg-gradient-to-br ${acmeSettings.enabled ? 'from-emerald-500/10' : 'from-amber-500/10'}`}>
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
              {acmeSettings.proxy_enabled ? (acmeSettings.proxy_registered ? 'Active' : 'Not Registered') : 'Disabled'}
            </StatusIndicator>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About ACME">
          ACME (Automatic Certificate Management Environment) is a protocol for automating 
          certificate issuance and renewal. It powers services like Let's Encrypt.
        </HelpCard>
        
        <HelpCard variant="tip" title="Let's Encrypt Integration">
          Enable the LE Proxy to forward certificate requests to Let's Encrypt while 
          maintaining centralized audit logging and management control.
        </HelpCard>

        <HelpCard variant="warning" title="Account Security">
          ACME accounts contain private keys. Keep accounts secure and deactivate 
          or delete unused accounts to minimize security exposure.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (account list with search/filter)
  const focusContent = (
    <div className="flex flex-col h-full">
      {/* Search and Filter */}
      <div className="p-3 space-y-2 border-b border-border">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search accounts..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-border bg-bg-tertiary focus:border-accent-primary focus:ring-1 focus:ring-accent-primary/20"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-full px-2.5 py-1.5 text-sm rounded-md border border-border bg-bg-tertiary"
        >
          <option value="all">All Status</option>
          <option value="valid">Valid</option>
          <option value="deactivated">Deactivated</option>
        </select>
      </div>

      {/* Account List */}
      <div className="flex-1 overflow-auto p-2 space-y-1.5">
        {filteredAccounts.length === 0 ? (
          <EmptyState 
            icon={Key}
            title="No Accounts"
            description={searchTerm ? "No matching accounts found" : "Create your first ACME account"}
          />
        ) : (
          filteredAccounts.map((account) => (
            <FocusItem
              key={account.id}
              icon={Key}
              title={account.email}
              subtitle={`Created ${account.created_at ? new Date(account.created_at).toLocaleDateString() : '-'}`}
              badge={
                <Badge variant={account.status === 'valid' ? 'success' : 'secondary'} size="sm">
                  {account.status}
                </Badge>
              }
              selected={selectedAccount?.id === account.id}
              onClick={() => selectAccount(account)}
            />
          ))
        )}
      </div>
    </div>
  )

  // Focus actions (create button)
  const focusActions = (
    <Button onClick={() => setShowCreateModal(true)} size="sm" className="w-full">
      <Plus size={14} />
      Create Account
    </Button>
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
      <PageLayout
        title="ACME Protocol"
        focusTitle="Accounts"
        focusContent={focusContent}
        focusActions={focusActions}
        focusFooter={`${filteredAccounts.length} of ${accounts.length} account(s)`}
        helpContent={helpContent}
        
      >
        {/* Main Content */}
        {!selectedAccount ? (
          configContent
        ) : (
          <div className="p-3 space-y-3">
            {/* Header */}
            <CompactHeader
              icon={Globe}
              iconClass={selectedAccount.status === 'valid' ? "bg-status-success/20" : "bg-bg-tertiary"}
              title={selectedAccount.email}
              subtitle={`Account ID: ${selectedAccount.account_id?.substring(0, 20)}...`}
              badge={
                <Badge 
                  variant={selectedAccount.status === 'valid' ? 'success' : 'secondary'} 
                  size="sm"
                >
                  {selectedAccount.status === 'valid' && <CheckCircle size={12} weight="fill" />}
                  {selectedAccount.status}
                </Badge>
              }
            />

            {/* Stats */}
            <CompactStats stats={[
              { icon: Key, value: selectedAccount.key_type || 'RSA-2048' },
              { icon: Lightning, value: `${orders.length} orders` },
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

            {/* Tabs Navigation */}
            <DetailTabs
              tabs={[
                { id: 'account', label: 'Account', icon: Key, count: null },
                { id: 'orders', label: 'Orders', icon: Globe, count: orders.length },
                { id: 'challenges', label: 'Challenges', icon: ShieldCheck, count: challenges.length },
              ]}
              activeTab={activeDetailTab}
              onChange={setActiveDetailTab}
            />

            {/* Tab Content */}
            <div className="min-h-0">
              {/* Account Tab */}
              {activeDetailTab === 'account' && (
                <div className="space-y-3">
                  <CompactSection title="Account Information">
                    <CompactGrid>
                      <CompactField label="Email" value={selectedAccount.email} />
                      <div className="text-xs">
                        <span className="text-text-tertiary">Status:</span>
                        <StatusIndicator status={selectedAccount.status === 'valid' ? 'active' : 'inactive'} className="ml-1 inline-flex">
                          {selectedAccount.status}
                        </StatusIndicator>
                      </div>
                      <CompactField label="Key Type" value={selectedAccount.key_type || 'RSA-2048'} />
                      <CompactField label="Created" value={selectedAccount.created_at ? new Date(selectedAccount.created_at).toLocaleDateString() : '-'} />
                    </CompactGrid>
                    <div className="mt-2 text-xs">
                      <span className="text-text-tertiary block mb-0.5">Account ID:</span>
                      <p className="font-mono text-[10px] text-text-secondary break-all bg-bg-tertiary/50 p-1.5 rounded">
                        {selectedAccount.account_id || '-'}
                      </p>
                    </div>
                  </CompactSection>

                  <CompactSection title="Terms of Service">
                    <div className="flex items-center gap-2 text-xs">
                      {selectedAccount.tos_agreed ? (
                        <>
                          <CheckCircle size={14} className="text-green-500" />
                          <span className="text-green-500">Agreed</span>
                        </>
                      ) : (
                        <>
                          <XCircle size={14} className="text-red-500" />
                          <span className="text-red-500">Not Agreed</span>
                        </>
                      )}
                    </div>
                  </CompactSection>
                </div>
              )}

              {/* Orders Tab */}
              {activeDetailTab === 'orders' && (
                <CompactSection title={`${orders.length} Active Orders`}>
                  {orders.length === 0 ? (
                    <p className="text-xs text-text-tertiary py-4 text-center">No pending certificate orders</p>
                  ) : (
                    <div className="max-h-48 overflow-y-auto">
                      <Table
                        columns={orderColumns}
                        data={orders}
                        compact
                      />
                    </div>
                  )}
                </CompactSection>
              )}

              {/* Challenges Tab */}
              {activeDetailTab === 'challenges' && (
                <CompactSection title={`${challenges.length} Challenges`}>
                  {challenges.length === 0 ? (
                    <p className="text-xs text-text-tertiary py-4 text-center">No active ACME challenges</p>
                  ) : (
                    <div className="max-h-48 overflow-y-auto">
                      <Table
                        columns={challengeColumns}
                        data={challenges}
                        compact
                      />
                    </div>
                  )}
                </CompactSection>
              )}
            </div>
          </div>
        )}
      </PageLayout>

      {/* Create Account Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create ACME Account"
      >
        <CreateACMEAccountForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreateModal(false)}
        />
      </Modal>
    </>
  )
}

function CreateACMEAccountForm({ onSubmit, onCancel }) {
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Email Address"
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText="Contact email for certificate expiry notifications"
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
      
      <div className="flex gap-3 pt-4">
        <Button type="submit">Create Account</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}
