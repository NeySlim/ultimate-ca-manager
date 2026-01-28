/**
 * Account Page (User Profile)
 */
import { useState, useEffect } from 'react'
import { User, LockKey, Key, FloppyDisk } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, Input, Badge, Tabs,
  LoadingSpinner, Modal
} from '../components'
import { accountService } from '../services'
import { useAuth, useNotification } from '../contexts'

export default function AccountPage() {
  const { user } = useAuth()
  const { showSuccess, showError } = useNotification()
  
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [accountData, setAccountData] = useState({})
  const [apiKeys, setApiKeys] = useState([])
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [qrData, setQrData] = useState(null)
  const [confirmCode, setConfirmCode] = useState('')

  useEffect(() => {
    loadAccount()
    loadApiKeys()
  }, [])

  const loadAccount = async () => {
    setLoading(true)
    try {
      const data = await accountService.getProfile()
      setAccountData(data)
    } catch (error) {
      showError(error.message || 'Failed to load account')
    } finally {
      setLoading(false)
    }
  }

  const loadApiKeys = async () => {
    try {
      const data = await accountService.getApiKeys()
      setApiKeys(data.keys || [])
    } catch (error) {
      console.error('Failed to load API keys:', error)
    }
  }

  const handleUpdateProfile = async () => {
    try {
      await accountService.updateProfile(accountData)
      showSuccess('Profile updated successfully')
      setEditing(false)
      loadAccount()
    } catch (error) {
      showError(error.message || 'Failed to update profile')
    }
  }

  const handleChangePassword = async (passwordData) => {
    try {
      await accountService.changePassword(passwordData)
      showSuccess('Password changed successfully')
      setShowPasswordModal(false)
    } catch (error) {
      showError(error.message || 'Failed to change password')
    }
  }

  const handleCreateApiKey = async (keyData) => {
    try {
      const created = await accountService.createApiKey(keyData)
      showSuccess(`API key created: ${created.key}`)
      setShowApiKeyModal(false)
      loadApiKeys()
    } catch (error) {
      showError(error.message || 'Failed to create API key')
    }
  }

  const handleDeleteApiKey = async (keyId) => {
    if (!confirm('Are you sure you want to delete this API key?')) return
    
    try {
      await accountService.deleteApiKey(keyId)
      showSuccess('API key deleted')
      loadApiKeys()
    } catch (error) {
      showError(error.message || 'Failed to delete API key')
    }
  }

  const handleToggle2FA = async () => {
    try {
      if (accountData.two_factor_enabled) {
        // Disable 2FA - ask for confirmation code
        const code = prompt('Enter your 2FA code to disable:')
        if (!code) return
        await accountService.disable2FA(code)
        showSuccess('Two-factor authentication disabled')
        loadAccount()
      } else {
        // Enable 2FA - show QR modal
        const response = await accountService.enable2FA()
        setQrData(response)
        setShow2FAModal(true)
      }
    } catch (error) {
      showError(error.message || 'Failed to toggle 2FA')
    }
  }

  const handleConfirm2FA = async () => {
    try {
      await accountService.confirm2FA(confirmCode)
      showSuccess('2FA enabled successfully! Save your backup codes.')
      setShow2FAModal(false)
      setQrData(null)
      setConfirmCode('')
      loadAccount()
    } catch (error) {
      showError(error.message || 'Invalid code. Please try again.')
    }
  }

  const updateField = (field, value) => {
    setAccountData(prev => ({ ...prev, [field]: value }))
  }

  const tabs = [
    {
      id: 'profile',
      label: 'Profile',
      icon: <User size={16} />,
      content: (
        <div className="space-y-6 max-w-2xl">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Personal Information</h3>
            <div className="space-y-4">
              <Input
                label="Username"
                value={accountData.username || ''}
                disabled
                helperText="Username cannot be changed"
              />
              <Input
                label="Email"
                type="email"
                value={accountData.email || ''}
                onChange={(e) => updateField('email', e.target.value)}
                disabled={!editing}
              />
              <Input
                label="Full Name"
                value={accountData.full_name || ''}
                onChange={(e) => updateField('full_name', e.target.value)}
                disabled={!editing}
              />
              
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Role</p>
                <Badge variant="primary">{accountData.role}</Badge>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Account Information</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Account Created</p>
                <p className="text-sm text-text-primary">
                  {accountData.created_at ? new Date(accountData.created_at).toLocaleDateString() : '-'}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Last Login</p>
                <p className="text-sm text-text-primary">
                  {accountData.last_login ? new Date(accountData.last_login).toLocaleString() : '-'}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Total Logins</p>
                <p className="text-sm text-text-primary">{accountData.login_count || 0}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
                <Badge variant={accountData.active ? 'success' : 'danger'}>
                  {accountData.active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
            </div>
          </div>

          <div className="flex gap-3 pt-4 border-t border-border">
            {editing ? (
              <>
                <Button onClick={handleUpdateProfile}>
                  <FloppyDisk size={16} />
                  Save Changes
                </Button>
                <Button variant="ghost" onClick={() => {
                  setEditing(false)
                  loadAccount()
                }}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button onClick={() => setEditing(true)}>
                Edit Profile
              </Button>
            )}
          </div>
        </div>
      )
    },
    {
      id: 'security',
      label: 'Security',
      icon: <LockKey size={16} />,
      content: (
        <div className="space-y-6 max-w-2xl">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Password</h3>
            <div className="flex items-center justify-between p-4 bg-bg-tertiary border border-border rounded-lg">
              <div>
                <p className="text-sm font-medium text-text-primary">Change Password</p>
                <p className="text-xs text-text-secondary mt-1">
                  Last changed: {accountData.password_changed_at 
                    ? new Date(accountData.password_changed_at).toLocaleDateString()
                    : 'Never'}
                </p>
              </div>
              <Button size="sm" onClick={() => setShowPasswordModal(true)}>
                Change Password
              </Button>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Two-Factor Authentication</h3>
            <div className="flex items-center justify-between p-4 bg-bg-tertiary border border-border rounded-lg">
              <div>
                <p className="text-sm font-medium text-text-primary">2FA Status</p>
                <p className="text-xs text-text-secondary mt-1">
                  {accountData.two_factor_enabled ? (
                    <Badge variant="success">Enabled</Badge>
                  ) : (
                    <Badge variant="secondary">Disabled</Badge>
                  )}
                </p>
              </div>
              <Button size="sm" variant={accountData.two_factor_enabled ? 'danger' : 'primary'} onClick={handleToggle2FA}>
                {accountData.two_factor_enabled ? 'Disable 2FA' : 'Enable 2FA'}
              </Button>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Active Sessions</h3>
            <div className="space-y-2">
              <div className="p-3 bg-bg-tertiary border border-border rounded">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-text-primary">Current Session</p>
                    <p className="text-xs text-text-secondary">Started {new Date().toLocaleString()}</p>
                  </div>
                  <Badge variant="success">Active</Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'api-keys',
      label: 'API Keys',
      icon: <Key size={16} />,
      content: (
        <div className="space-y-6 max-w-2xl">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary">API Keys</h3>
            <Button size="sm" onClick={() => setShowApiKeyModal(true)}>
              <Key size={16} />
              Create API Key
            </Button>
          </div>

          <div className="space-y-2">
            {apiKeys.length === 0 ? (
              <div className="text-center py-12 text-text-secondary">
                <Key size={48} className="mx-auto mb-3 opacity-50" />
                <p className="text-sm">No API keys</p>
                <p className="text-xs mt-1">Create an API key for programmatic access</p>
              </div>
            ) : (
              apiKeys.map(key => (
                <div key={key.id} className="p-4 bg-bg-tertiary border border-border rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-text-primary">{key.name}</p>
                      <p className="text-xs font-mono text-text-secondary mt-1">
                        {key.key_preview}••••••••
                      </p>
                      <p className="text-xs text-text-secondary mt-1">
                        Created: {new Date(key.created_at).toLocaleDateString()}
                        {key.last_used && ` • Last used: ${new Date(key.last_used).toLocaleDateString()}`}
                      </p>
                    </div>
                    <Button 
                      variant="danger" 
                      size="sm" 
                      onClick={() => handleDeleteApiKey(key.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="text-sm text-amber-500 font-medium">⚠️ API Key Security</p>
            <p className="text-xs text-text-secondary mt-1">
              API keys provide full access to your account. Keep them secure and never share them.
            </p>
          </div>
        </div>
      )
    },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading account..." />
      </div>
    )
  }

  return (
    <>
      <ExplorerPanel title="My Account">
        <div className="p-3 space-y-3">
          {/* User Info */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">User Info</h3>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Username</span>
                <span className="text-text-primary font-medium">{user?.username || 'N/A'}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Email</span>
                <span className="text-text-primary font-medium truncate">{user?.email || 'N/A'}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Role</span>
                <Badge variant={user?.is_admin ? 'success' : 'default'}>
                  {user?.is_admin ? 'Admin' : 'User'}
                </Badge>
              </div>
            </div>
          </div>

          {/* Session Info */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">Session Info</h3>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Status</span>
                <span className="text-green-500 font-medium">Active</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">API Keys</span>
                <span className="text-text-primary font-medium">{apiKeys.length}</span>
              </div>
            </div>
          </div>

          {/* Quick Help */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">Quick Help</h3>
            <div className="text-xs text-text-secondary space-y-1.5">
              <p>• Update your profile information</p>
              <p>• Change your password regularly</p>
              <p>• Manage API keys for automation</p>
              <p>• Review your activity history</p>
            </div>
          </div>
        </div>
      </ExplorerPanel>

      <DetailsPanel>
        <Tabs tabs={tabs} defaultTab="profile" />
      </DetailsPanel>

      {/* Change Password Modal */}
      <Modal
        open={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        title="Change Password"
      >
        <ChangePasswordForm
          onSubmit={handleChangePassword}
          onCancel={() => setShowPasswordModal(false)}
        />
      </Modal>

      {/* Create API Key Modal */}
      <Modal
        open={showApiKeyModal}
        onClose={() => setShowApiKeyModal(false)}
        title="Create API Key"
      >
        <CreateApiKeyForm
          onSubmit={handleCreateApiKey}
          onCancel={() => setShowApiKeyModal(false)}
        />
      </Modal>

      {/* 2FA Setup Modal */}
      <Modal
        open={show2FAModal}
        onClose={() => {
          setShow2FAModal(false)
          setQrData(null)
          setConfirmCode('')
        }}
        title="Enable Two-Factor Authentication"
      >
        {qrData && (
          <div className="space-y-4">
            <div className="text-sm text-text-secondary">
              <p className="mb-2">1. Scan this QR code with Google Authenticator, Authy, or any TOTP app:</p>
              <div className="flex justify-center p-4 bg-surface-elevated rounded-lg">
                <img src={qrData.qr_code} alt="2FA QR Code" className="w-48 h-48" />
              </div>
            </div>
            
            <div className="text-sm text-text-secondary">
              <p className="mb-2">2. Enter the 6-digit code from your authenticator app:</p>
              <Input
                type="text"
                placeholder="000000"
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                className="text-center text-2xl tracking-widest"
              />
            </div>

            {qrData.backup_codes && qrData.backup_codes.length > 0 && (
              <div className="text-sm">
                <p className="font-semibold text-text-primary mb-2">⚠️ Save these backup codes:</p>
                <div className="bg-surface-elevated rounded p-3 space-y-1 font-mono text-xs">
                  {qrData.backup_codes.map((code, i) => (
                    <div key={i}>{code}</div>
                  ))}
                </div>
                <p className="text-text-secondary mt-2 text-xs">Keep these codes safe! You'll need them if you lose access to your authenticator app.</p>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button variant="secondary" onClick={() => {
                setShow2FAModal(false)
                setQrData(null)
                setConfirmCode('')
              }} className="flex-1">
                Cancel
              </Button>
              <Button 
                variant="primary" 
                onClick={handleConfirm2FA}
                disabled={confirmCode.length !== 6}
                className="flex-1"
              >
                Confirm & Enable
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

function ChangePasswordForm({ onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (formData.new_password !== formData.confirm_password) {
      alert('New passwords do not match')
      return
    }
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Current Password"
        type="password"
        value={formData.current_password}
        onChange={(e) => setFormData(prev => ({ ...prev, current_password: e.target.value }))}
        required
      />
      <Input
        label="New Password"
        type="password"
        value={formData.new_password}
        onChange={(e) => setFormData(prev => ({ ...prev, new_password: e.target.value }))}
        required
      />
      <Input
        label="Confirm New Password"
        type="password"
        value={formData.confirm_password}
        onChange={(e) => setFormData(prev => ({ ...prev, confirm_password: e.target.value }))}
        required
      />
      
      <div className="flex gap-3 pt-4">
        <Button type="submit">Change Password</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}

function CreateApiKeyForm({ onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    name: '',
    expires_in_days: 90,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Key Name"
        value={formData.name}
        onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
        placeholder="My API Key"
        required
        helperText="A descriptive name to identify this key"
      />
      <Input
        label="Expires in (days)"
        type="number"
        value={formData.expires_in_days}
        onChange={(e) => setFormData(prev => ({ ...prev, expires_in_days: parseInt(e.target.value) }))}
        min="1"
        max="365"
        helperText="Key will expire after this many days (1-365)"
      />
      
      <div className="flex gap-3 pt-4">
        <Button type="submit">Create Key</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}
