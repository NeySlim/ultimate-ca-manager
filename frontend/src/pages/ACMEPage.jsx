/**
 * ACME Page
 */
import { useState, useEffect } from 'react'
import { Key, Plus, Trash, CheckCircle, XCircle, FloppyDisk, ShieldCheck, HourglassHigh, Globe, Lightning } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Table, Button, Badge, Card,
  Input, Modal, Tabs, Select,
  LoadingSpinner, EmptyState, StatusIndicator
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
      loadAcmeSettings() // Reload to show registered state
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
      loadAcmeSettings() // Reload to show unregistered state
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

  const accountColumns = [
    { 
      key: 'email', 
      label: 'Email',
      render: (val) => <span className="font-medium">{val}</span>
    },
    {
      key: 'status',
      label: 'Status',
      render: (val) => (
        <div className="flex items-center gap-2">
          <StatusIndicator status={val === 'valid' ? 'active' : 'inactive'} />
          <Badge variant={val === 'valid' ? 'success' : 'secondary'}>{val}</Badge>
        </div>
      )
    },
    {
      key: 'orders_count',
      label: 'Orders',
      render: (val) => val || 0
    },
    {
      key: 'created_at',
      label: 'Created',
      render: (val) => new Date(val).toLocaleDateString()
    },
  ]

  const orderColumns = [
    { key: 'domain', label: 'Domain' },
    {
      key: 'status',
      label: 'Status',
      render: (val) => <Badge variant={val === 'valid' ? 'success' : 'warning'}>{val}</Badge>
    },
    { key: 'created_at', label: 'Created', render: (val) => new Date(val).toLocaleString() },
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

  const detailTabs = selectedAccount ? [
    {
      id: 'info',
      label: 'Account Info',
      icon: <Key size={16} />,
      content: (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Email</p>
              <p className="text-sm text-text-primary">{selectedAccount.email}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
              <div className="flex items-center gap-2">
                <StatusIndicator status={selectedAccount.status === 'valid' ? 'active' : 'inactive'} />
                <span className="text-sm">{selectedAccount.status}</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Key Type</p>
              <p className="text-sm text-text-primary">{selectedAccount.key_type || 'RSA-2048'}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Created</p>
              <p className="text-sm text-text-primary">
                {new Date(selectedAccount.created_at).toLocaleString()}
              </p>
            </div>
            <div className="col-span-2">
              <p className="text-xs text-text-secondary uppercase mb-1">Account ID</p>
              <p className="text-xs font-mono text-text-primary break-all">
                {selectedAccount.account_id}
              </p>
            </div>
            <div className="col-span-2">
              <p className="text-xs text-text-secondary uppercase mb-1">Terms of Service</p>
              <div className="flex items-center gap-2">
                {selectedAccount.tos_agreed ? (
                  <>
                    <CheckCircle size={16} className="text-green-500" />
                    <span className="text-sm text-green-500">Agreed</span>
                  </>
                ) : (
                  <>
                    <XCircle size={16} className="text-red-500" />
                    <span className="text-sm text-red-500">Not Agreed</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'orders',
      label: 'Active Orders',
      content: (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-text-secondary">
              {orders.length} active orders
            </p>
          </div>
          
          {orders.length === 0 ? (
            <EmptyState
              title="No active orders"
              description="No pending certificate orders for this account"
            />
          ) : (
            <Table
              columns={orderColumns}
              data={orders}
            />
          )}
        </div>
      )
    },
    {
      id: 'challenges',
      label: 'Challenges',
      content: (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-text-secondary">
              {challenges.length} challenges
            </p>
          </div>
          
          {challenges.length === 0 ? (
            <EmptyState
              title="No challenges"
              description="No active ACME challenges"
            />
          ) : (
            <Table
              columns={challengeColumns}
              data={challenges}
            />
          )}
        </div>
      )
    },
  ] : []

  const configTabs = [
    {
      id: 'config',
      label: 'Server Configuration',
      content: (
        <div className="space-y-6 max-w-2xl p-4">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">ACME Server Configuration</h3>
            <div className="space-y-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={acmeSettings.enabled || false}
                  onChange={(e) => updateAcmeSetting('enabled', e.target.checked)}
                  className="rounded border-border bg-bg-tertiary"
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

              <Input
                label="ACME Directory URL"
                value={`${window.location.origin}/acme/directory`}
                readOnly
                helperText="Use this URL with ACME clients like certbot or acme.sh"
                className="bg-bg-tertiary"
              />
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="text-sm font-semibold text-text-primary mb-4">Let's Encrypt Proxy</h3>
            <div className="space-y-4">
              <p className="text-sm text-text-secondary">
                Register a proxy account to use UCM as a Let's Encrypt proxy for external certificate issuance.
              </p>

              <Input
                label="Proxy Endpoint URL"
                value={`${window.location.origin}/api/v2/acme/proxy`}
                readOnly
                helperText="External ACME clients can use this URL to proxy requests to Let's Encrypt"
                className="bg-bg-tertiary"
              />
              
              {acmeSettings.proxy_registered ? (
                <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-full bg-emerald-500/20">
                        <CheckCircle size={20} className="text-emerald-500" weight="fill" />
                      </div>
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
                      <Trash size={16} />
                      Unregister
                    </Button>
                  </div>
                </div>
              ) : (
                <>
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
                    onClick={handleRegisterProxy}
                    disabled={!proxyEmail}
                  >
                    <Key size={16} />
                    Register Proxy Account
                  </Button>
                </>
              )}
            </div>
          </div>

          <div className="flex gap-3 pt-4 border-t border-border">
            <Button onClick={handleSaveConfig} disabled={saving}>
              <FloppyDisk size={16} />
              Save Configuration
            </Button>
          </div>
        </div>
      )
    }
  ]

  // Stats computed from accounts
  const stats = {
    total: accounts.length,
    active: accounts.filter(a => a.status === 'valid').length,
    orders: orders.length,
    challenges: challenges.filter(c => c.status === 'pending').length
  }

  return (
    <>
      <ExplorerPanel
        title="ACME"
        footer={
          <div className="text-xs text-text-secondary">
            {accounts.length} accounts
          </div>
        }
      >
        <div className="space-y-4">
          {/* Stats Cards */}
          <div className="px-3 pt-2 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Overview
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <Card className="p-2.5 text-center bg-gradient-to-br from-blue-500/10 to-transparent border-blue-500/20">
                <div className="flex items-center justify-center gap-1.5">
                  <Key size={16} weight="duotone" className="text-blue-500" />
                  <span className="text-lg font-bold text-blue-500">{stats.total}</span>
                </div>
                <div className="text-xs text-text-secondary">Accounts</div>
              </Card>
              <Card className="p-2.5 text-center bg-gradient-to-br from-emerald-500/10 to-transparent border-emerald-500/20">
                <div className="flex items-center justify-center gap-1.5">
                  <CheckCircle size={16} weight="duotone" className="text-emerald-500" />
                  <span className="text-lg font-bold text-emerald-500">{stats.active}</span>
                </div>
                <div className="text-xs text-text-secondary">Active</div>
              </Card>
            </div>
          </div>

          {/* Server Status */}
          <div className="px-3 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Server Status
            </h3>
            <Card className="p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Lightning size={14} weight="duotone" className={acmeSettings.enabled ? 'text-emerald-500' : 'text-gray-500'} />
                  <span className="text-sm">ACME Server</span>
                </div>
                <Badge variant={acmeSettings.enabled ? 'emerald' : 'gray'} size="sm">
                  {acmeSettings.enabled ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Globe size={14} weight="duotone" className="text-purple-500" />
                  <span className="text-sm">Directory</span>
                </div>
                <Badge variant="purple" size="sm">Ready</Badge>
              </div>
            </Card>
          </div>

          {/* Actions */}
          <div className="px-3 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Actions
            </h3>
            <Button onClick={() => setShowCreateModal(true)} className="w-full justify-start">
              <span className="p-1 rounded bg-accent/20">
                <Plus size={16} weight="bold" className="text-accent" />
              </span>
              Create Account
            </Button>
          </div>

          {/* Account List */}
          {accounts.length > 0 && (
            <div className="px-3 space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
                Accounts
              </h3>
              <div className="space-y-1">
                {accounts.slice(0, 5).map(account => (
                  <button
                    key={account.id}
                    onClick={() => selectAccount(account)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition-colors ${
                      selectedAccount?.id === account.id 
                        ? 'bg-accent/10 text-accent border-l-2 border-accent' 
                        : 'hover:bg-bg-tertiary/50'
                    }`}
                  >
                    <Key size={14} weight="duotone" className={account.status === 'valid' ? 'text-emerald-500' : 'text-gray-500'} />
                    <span className="text-sm truncate flex-1">{account.email}</span>
                    <Badge variant={account.status === 'valid' ? 'emerald' : 'gray'} size="sm">
                      {account.status}
                    </Badge>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'ACME' },
          { label: selectedAccount?.email || 'Configuration' }
        ]}
        title={selectedAccount?.email || 'ACME Configuration'}
        actions={selectedAccount && (
          <>
            <Button 
              variant="secondary" 
              size="sm" 
              onClick={() => handleDeactivate(selectedAccount.id)}
              disabled={selectedAccount.status !== 'valid'}
            >
              Deactivate
            </Button>
            <Button variant="danger" size="sm" onClick={() => handleDelete(selectedAccount.id)}>
              <Trash size={16} />
              Delete
            </Button>
          </>
        )}
      >
        {!selectedAccount ? (
          <Tabs tabs={configTabs} defaultTab="config" />
        ) : (
          <Tabs tabs={detailTabs} defaultTab="info" />
        )}
      </DetailsPanel>

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
