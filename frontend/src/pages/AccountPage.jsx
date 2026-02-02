/**
 * Account Page (User Profile)
 * Uses PageLayout for consistent structure + DetailCard components
 */
import { useState, useEffect } from 'react'
import { User, LockKey, Key, FloppyDisk, Fingerprint, Certificate, Gear, Pulse, PencilSimple, SignOut } from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Input, Badge, Card,
  LoadingSpinner, Modal, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent, DetailTabs
} from '../components'
import { accountService } from '../services'
import { useAuth, useNotification } from '../contexts'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'

export default function AccountPage() {
  const { user } = useAuth()
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [accountData, setAccountData] = useState({})
  const [apiKeys, setApiKeys] = useState([])
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [qrData, setQrData] = useState(null)
  const [confirmCode, setConfirmCode] = useState('')
  const [activeTab, setActiveTab] = useState('profile')
  
  // WebAuthn state
  const [webauthnCredentials, setWebauthnCredentials] = useState([])
  const [showWebAuthnModal, setShowWebAuthnModal] = useState(false)
  const [webauthnName, setWebauthnName] = useState('')
  const [webauthnRegistering, setWebauthnRegistering] = useState(false)
  
  // mTLS state
  const [mtlsCertificates, setMtlsCertificates] = useState([])
  const [showMTLSModal, setShowMTLSModal] = useState(false)
  const [mtlsMode, setMtlsMode] = useState('create') // 'create' or 'enroll'
  const [mtlsFormData, setMtlsFormData] = useState({ cn: '', email: '', validity_days: 365 })

  useEffect(() => {
    loadAccount()
    loadApiKeys()
    loadWebAuthnCredentials()
    loadMTLSCertificates()
  }, [])

  const loadAccount = async () => {
    setLoading(true)
    try {
      const response = await accountService.getProfile()
      setAccountData(response.data || response)
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.GENERIC)
    } finally {
      setLoading(false)
    }
  }

  const loadApiKeys = async () => {
    try {
      const response = await accountService.getApiKeys()
      setApiKeys(response.data || response || [])
    } catch (error) {
      console.error('Failed to load API keys:', error)
    }
  }

  const loadWebAuthnCredentials = async () => {
    try {
      const response = await accountService.getWebAuthnCredentials()
      setWebauthnCredentials(response.data || [])
    } catch (error) {
      console.error('Failed to load WebAuthn credentials:', error)
    }
  }

  const loadMTLSCertificates = async () => {
    try {
      const response = await accountService.getMTLSCertificates()
      setMtlsCertificates(response.data || [])
    } catch (error) {
      console.error('Failed to load mTLS certificates:', error)
    }
  }

  const handleUpdateProfile = async () => {
    try {
      await accountService.updateProfile(accountData)
      showSuccess(SUCCESS.UPDATE.USER)
      setEditing(false)
      loadAccount()
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.USER)
    }
  }

  const handleChangePassword = async (passwordData) => {
    try {
      await accountService.changePassword(passwordData)
      showSuccess(SUCCESS.OTHER.PASSWORD_CHANGED)
      setShowPasswordModal(false)
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.GENERIC)
    }
  }

  const handleCreateApiKey = async (keyData) => {
    try {
      const created = await accountService.createApiKey(keyData)
      showSuccess(`API key created: ${created.key}`)
      setShowApiKeyModal(false)
      loadApiKeys()
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.GENERIC)
    }
  }

  const handleDeleteApiKey = async (keyId) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.GENERIC, {
      title: 'Delete API Key',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await accountService.deleteApiKey(keyId)
      showSuccess(SUCCESS.DELETE.GENERIC)
      loadApiKeys()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
    }
  }

  const handleToggle2FA = async () => {
    try {
      if (accountData.two_factor_enabled) {
        // Disable 2FA - ask for confirmation code
        const code = await showPrompt('Enter your 2FA code to disable:', {
          title: 'Disable Two-Factor Authentication',
          placeholder: '123456',
          confirmText: 'Disable 2FA'
        })
        if (!code) return
        await accountService.disable2FA(code)
        showSuccess(SUCCESS.OTHER.TWO_FACTOR_DISABLED)
        loadAccount()
      } else {
        // Enable 2FA - show QR modal
        const response = await accountService.enable2FA()
        // API returns {data: {qr_code, secret, backup_codes}, message}
        setQrData(response.data || response)
        setShow2FAModal(true)
      }
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.GENERIC)
    }
  }

  const handleConfirm2FA = async () => {
    try {
      await accountService.confirm2FA(confirmCode)
      showSuccess(SUCCESS.OTHER.TWO_FACTOR_ENABLED)
      setShow2FAModal(false)
      setQrData(null)
      setConfirmCode('')
      loadAccount()
    } catch (error) {
      showError(error.message || ERRORS.VALIDATION.REQUIRED_FIELD)
    }
  }

  // ============ WebAuthn Handlers ============
  const handleRegisterWebAuthn = async () => {
    if (!webauthnName.trim()) {
      showError(ERRORS.VALIDATION.REQUIRED_FIELD)
      return
    }
    
    setWebauthnRegistering(true)
    try {
      // Step 1: Get registration options
      const response = await accountService.startWebAuthnRegistration()
      const options = response.data  // Extract data from API response
      
      // Helper to decode base64url to Uint8Array
      const base64urlToUint8Array = (base64url) => {
        // Add padding if needed
        let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/')
        while (base64.length % 4) base64 += '='
        return Uint8Array.from(atob(base64), c => c.charCodeAt(0))
      }
      
      // Helper to convert string to Uint8Array (for user.id which is just a number string)
      const stringToUint8Array = (str) => {
        return new TextEncoder().encode(str)
      }
      
      // Convert challenge (base64url) and userId (plain string)
      const challenge = base64urlToUint8Array(options.challenge)
      const userId = stringToUint8Array(options.user.id)
      
      // Step 2: Create credential using browser API
      const credential = await navigator.credentials.create({
        publicKey: {
          ...options,
          challenge,
          user: { ...options.user, id: userId },
          excludeCredentials: (options.excludeCredentials || []).map(cred => ({
            ...cred,
            id: base64urlToUint8Array(cred.id)
          }))
        }
      })
      
      // Step 3: Encode credential for server
      const credentialData = {
        id: credential.id,
        rawId: btoa(String.fromCharCode(...new Uint8Array(credential.rawId))),
        type: credential.type,
        response: {
          clientDataJSON: btoa(String.fromCharCode(...new Uint8Array(credential.response.clientDataJSON))),
          attestationObject: btoa(String.fromCharCode(...new Uint8Array(credential.response.attestationObject)))
        }
      }
      
      // Step 4: Send to server
      await accountService.completeWebAuthnRegistration(credentialData, webauthnName)
      
      showSuccess(SUCCESS.CREATE.GENERIC)
      setShowWebAuthnModal(false)
      setWebauthnName('')
      loadAccount()
      loadWebAuthnCredentials()
    } catch (error) {
      console.error('WebAuthn registration failed:', error)
      if (error.name === 'NotAllowedError') {
        showError(ERRORS.AUTH.CANCELLED)
      } else {
        showError(error.message || ERRORS.CREATE_FAILED.GENERIC)
      }
    } finally {
      setWebauthnRegistering(false)
    }
  }
  
  const handleDeleteWebAuthn = async (credentialId) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.GENERIC, {
      title: 'Delete Security Key',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await accountService.deleteWebAuthnCredential(credentialId)
      showSuccess(SUCCESS.DELETE.GENERIC)
      loadAccount()
      loadWebAuthnCredentials()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
    }
  }

  // ============ mTLS Handlers ============
  const handleCreateMTLS = async () => {
    if (!mtlsFormData.cn.trim()) {
      showError(ERRORS.VALIDATION.REQUIRED_FIELD)
      return
    }
    
    try {
      const response = await accountService.createMTLSCertificate({
        cn: mtlsFormData.cn,
        email: mtlsFormData.email || accountData.email,
        validity_days: mtlsFormData.validity_days,
        self_signed: false
      })
      
      showSuccess(SUCCESS.CREATE.CERTIFICATE)
      
      // Auto-download the certificate and key
      if (response.cert_pem) {
        downloadFile(response.cert_pem, `${mtlsFormData.cn}-cert.pem`)
      }
      if (response.key_pem) {
        downloadFile(response.key_pem, `${mtlsFormData.cn}-key.pem`)
      }
      
      setShowMTLSModal(false)
      setMtlsFormData({ cn: '', email: '', validity_days: 365 })
      loadAccount()
      loadMTLSCertificates()
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.CERTIFICATE)
    }
  }
  
  const handleDeleteMTLS = async (certId) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.CERTIFICATE, {
      title: 'Delete Certificate',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await accountService.deleteMTLSCertificate(certId)
      showSuccess(SUCCESS.DELETE.CERTIFICATE)
      loadAccount()
      loadMTLSCertificates()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.CERTIFICATE)
    }
  }
  
  const downloadFile = (content, filename) => {
    const blob = new Blob([content], { type: 'application/x-pem-file' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const updateField = (field, value) => {
    setAccountData(prev => ({ ...prev, [field]: value }))
  }

  // Tabs for DetailTabs component
  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'security', label: 'Security', icon: LockKey },
    { id: 'api-keys', label: 'API Keys', icon: Key, count: apiKeys.length },
  ]

  // Profile sections for focus panel
  const profileSections = [
    { id: 'profile', title: 'Personal Info', subtitle: 'Username, email, name', icon: User },
    { id: 'security', title: 'Security', subtitle: 'Password, 2FA, keys', icon: LockKey },
    { id: 'api-keys', title: 'API Keys', subtitle: `${apiKeys.length} key(s)`, icon: Key },
    { id: 'activity', title: 'Pulse', subtitle: 'Sessions & logins', icon: Pulse },
  ]

  // Render Profile Tab Content
  const renderProfileTab = () => (
    <>
      <DetailSection title="Personal Information">
        {editing ? (
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
            />
            <Input
              label="Full Name"
              value={accountData.full_name || ''}
              onChange={(e) => updateField('full_name', e.target.value)}
            />
            <div className="flex gap-3 pt-2">
              <Button size="sm" onClick={handleUpdateProfile}>
                <FloppyDisk size={16} />
                Save Changes
              </Button>
              <Button size="sm" variant="ghost" onClick={() => {
                setEditing(false)
                loadAccount()
              }}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <DetailGrid>
            <DetailField label="Username" value={accountData.username} />
            <DetailField label="Email" value={accountData.email} copyable />
            <DetailField label="Full Name" value={accountData.full_name || '—'} />
            <DetailField 
              label="Role" 
              value={<Badge variant="primary">{accountData.role}</Badge>}
            />
          </DetailGrid>
        )}
      </DetailSection>

      <DetailSection title="Account Information">
        <DetailGrid>
          <DetailField 
            label="Account Created" 
            value={accountData.created_at ? new Date(accountData.created_at).toLocaleDateString() : '—'} 
          />
          <DetailField 
            label="Last Login" 
            value={accountData.last_login ? new Date(accountData.last_login).toLocaleString() : '—'} 
          />
          <DetailField 
            label="Total Logins" 
            value={accountData.login_count || 0} 
          />
          <DetailField 
            label="Status" 
            value={
              <Badge variant={accountData.active ? 'success' : 'danger'}>
                {accountData.active ? 'Active' : 'Inactive'}
              </Badge>
            }
          />
        </DetailGrid>
      </DetailSection>
    </>
  )

  // Render Security Tab Content
  const renderSecurityTab = () => (
    <>
      <HelpCard variant="tip" title="Security Best Practices" items={[
        'Enable 2FA for additional protection',
        'Use security keys (WebAuthn) for passwordless login',
        'Rotate API keys regularly'
      ]} />

      <DetailSection title="Password">
        <div className="flex items-center justify-between">
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
      </DetailSection>

      <DetailSection title="Two-Factor Authentication">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-text-primary">Authenticator App (TOTP)</p>
            <div className="mt-1">
              {accountData.two_factor_enabled ? (
                <Badge variant="success">Enabled</Badge>
              ) : (
                <Badge variant="secondary">Disabled</Badge>
              )}
            </div>
          </div>
          <Button size="sm" variant={accountData.two_factor_enabled ? 'danger' : 'primary'} onClick={handleToggle2FA}>
            {accountData.two_factor_enabled ? 'Disable 2FA' : 'Enable 2FA'}
          </Button>
        </div>
      </DetailSection>

      <DetailSection title="Security Keys (WebAuthn/FIDO2)">
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowWebAuthnModal(true)}>
              Add Key
            </Button>
          </div>
          {webauthnCredentials.length === 0 ? (
            <div className="p-4 bg-bg-tertiary border border-border rounded-lg text-center">
              <Fingerprint size={32} className="mx-auto mb-2 opacity-50" />
              <p className="text-sm text-text-secondary">No security keys registered</p>
              <p className="text-xs text-text-secondary mt-1">Add a YubiKey, TouchID, or Windows Hello for passwordless login</p>
            </div>
          ) : (
            <div className="space-y-2">
              {webauthnCredentials.map(cred => (
                <div key={cred.id} className="flex items-center justify-between p-3 bg-bg-tertiary border border-border rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{cred.name || 'Security Key'}</p>
                    <p className="text-xs text-text-secondary">
                      Added {new Date(cred.created_at).toLocaleDateString()}
                      {cred.last_used_at && ` · Last used ${new Date(cred.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <Button size="sm" variant="danger" onClick={() => handleDeleteWebAuthn(cred.id)}>
                    Delete
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </DetailSection>

      <DetailSection title="Client Certificates (mTLS)">
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowMTLSModal(true)}>
              Create Certificate
            </Button>
          </div>
          {mtlsCertificates.length === 0 ? (
            <div className="p-4 bg-bg-tertiary border border-border rounded-lg text-center">
              <Certificate size={32} className="mx-auto mb-2 opacity-50" />
              <p className="text-sm text-text-secondary">No certificates enrolled</p>
              <p className="text-xs text-text-secondary mt-1">Create a client certificate for mutual TLS authentication</p>
            </div>
          ) : (
            <div className="space-y-2">
              {mtlsCertificates.map(cert => (
                <div key={cert.id} className="flex items-center justify-between p-3 bg-bg-tertiary border border-border rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{cert.name || cert.cert_subject}</p>
                    <p className="text-xs text-text-secondary">
                      Expires {new Date(cert.valid_until).toLocaleDateString()}
                      {' · '}
                      <Badge variant={cert.enabled ? 'success' : 'secondary'} className="text-xs">
                        {cert.enabled ? 'Active' : 'Disabled'}
                      </Badge>
                    </p>
                  </div>
                  <Button size="sm" variant="danger" onClick={() => handleDeleteMTLS(cert.id)}>
                    Delete
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </DetailSection>

      <DetailSection title="Active Sessions">
        <div className="flex items-center justify-between p-3 bg-bg-tertiary border border-border rounded-lg">
          <div>
            <p className="text-sm font-medium text-text-primary">Current Session</p>
            <p className="text-xs text-text-secondary">Started {new Date().toLocaleString()}</p>
          </div>
          <Badge variant="success">Active</Badge>
        </div>
      </DetailSection>
    </>
  )

  // Render API Keys Tab Content
  const renderApiKeysTab = () => (
    <>
      <DetailSection title="API Keys" noBorder>
        <div className="space-y-4">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowApiKeyModal(true)}>
              <Key size={16} />
              Create API Key
            </Button>
          </div>

          {apiKeys.length === 0 ? (
            <div className="text-center py-12 text-text-secondary bg-bg-tertiary border border-border rounded-lg">
              <Key size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No API keys</p>
              <p className="text-xs mt-1">Create an API key for programmatic access</p>
            </div>
          ) : (
            <div className="space-y-2">
              {apiKeys.map(key => (
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
              ))}
            </div>
          )}

          <div className="p-4 status-warning-bg status-warning-border border rounded-lg">
            <p className="text-sm status-warning-text font-medium">⚠️ API Key Security</p>
            <p className="text-xs text-text-secondary mt-1">
              API keys provide full access to your account. Keep them secure and never share them.
            </p>
          </div>
        </div>
      </DetailSection>
    </>
  )

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* Account Overview */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <User size={16} className="text-accent-primary" />
          Account Overview
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{apiKeys.length}</p>
            <p className="text-xs text-text-secondary">API Keys</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{webauthnCredentials.length}</p>
            <p className="text-xs text-text-secondary">Security Keys</p>
          </div>
        </div>
      </Card>

      {/* Security Status */}
      <Card className={`p-4 space-y-3 ${accountData.two_factor_enabled ? 'stat-card-success' : 'stat-card-warning'}`}>
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <LockKey size={16} className="text-accent-primary" />
          Security Status
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">2FA</span>
            <Badge variant={accountData.two_factor_enabled ? 'success' : 'warning'}>
              {accountData.two_factor_enabled ? 'Enabled' : 'Disabled'}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">mTLS Certs</span>
            <span className="text-sm font-medium text-text-primary">{mtlsCertificates.length}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Role</span>
            <Badge variant={user?.role === 'admin' ? 'primary' : 'secondary'}>
              {user?.role || 'User'}
            </Badge>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="Account Management">
          Manage your profile information, security settings, and API access from this page.
          Keep your contact information up to date for important notifications.
        </HelpCard>
        
        <HelpCard variant="tip" title="Security Best Practices">
          Enable two-factor authentication and use security keys (WebAuthn) for maximum protection.
          Rotate API keys regularly and never share them.
        </HelpCard>

        <HelpCard variant="warning" title="API Key Security">
          API keys provide full access to your account. Keep them secure, store them safely,
          and delete unused keys immediately.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (profile sections list)
  const focusContent = (
    <div className="p-2 space-y-1.5">
      {profileSections.map((section) => (
        <FocusItem
          key={section.id}
          icon={section.icon}
          title={section.title}
          subtitle={section.subtitle}
          badge={section.id === 'security' && accountData.two_factor_enabled ? (
            <Badge variant="success" size="sm">2FA</Badge>
          ) : section.id === 'api-keys' && apiKeys.length > 0 ? (
            <Badge variant="primary" size="sm">{apiKeys.length}</Badge>
          ) : null}
          selected={activeTab === section.id}
          onClick={() => setActiveTab(section.id)}
        />
      ))}
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading account..." />
      </div>
    )
  }

  return (
    <PageLayout
      title="My Account"
      focusTitle="Profile"
      focusContent={focusContent}
      focusFooter={`${user?.username || 'User'} • ${user?.role || 'User'}`}
      helpContent={helpContent}
      
    >
      {/* Detail Header */}
      <div className="p-4 md:p-6">
        <DetailHeader
          icon={User}
          title={accountData.username || 'User'}
          subtitle={accountData.email}
          badge={<Badge variant={accountData.role === 'admin' ? 'primary' : 'secondary'}>{accountData.role}</Badge>}
          stats={[
            { label: 'API Keys:', value: apiKeys.length },
            { label: 'Security Keys:', value: webauthnCredentials.length },
            { label: '2FA:', value: accountData.two_factor_enabled ? 'Enabled' : 'Disabled' },
          ]}
          actions={editing ? [] : [
            { 
              label: 'Edit Profile', 
              icon: PencilSimple, 
              onClick: () => setEditing(true) 
            },
          ]}
        />
      </div>

      {/* Detail Tabs */}
      <DetailTabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      {/* Tab Content */}
      <DetailContent>
        {activeTab === 'profile' && renderProfileTab()}
        {activeTab === 'security' && renderSecurityTab()}
        {activeTab === 'api-keys' && renderApiKeysTab()}
      </DetailContent>

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

      {/* WebAuthn Registration Modal */}
      <Modal
        open={showWebAuthnModal}
        onClose={() => {
          setShowWebAuthnModal(false)
          setWebauthnName('')
        }}
        title="Register Security Key"
      >
        <div className="space-y-4">
          <Input
            label="Key Name"
            value={webauthnName}
            onChange={(e) => setWebauthnName(e.target.value)}
            placeholder="YubiKey 5 NFC"
            helperText="Give your security key a recognizable name"
          />
          <p className="text-sm text-text-secondary">
            Click Register and follow your browser's prompts to activate your security key (YubiKey, TouchID, Windows Hello, etc.)
          </p>
          <div className="flex gap-2 pt-2">
            <Button variant="secondary" onClick={() => {
              setShowWebAuthnModal(false)
              setWebauthnName('')
            }} className="flex-1">
              Cancel
            </Button>
            <Button 
              variant="primary" 
              onClick={handleRegisterWebAuthn}
              disabled={!webauthnName.trim() || webauthnRegistering}
              className="flex-1"
            >
              {webauthnRegistering ? 'Registering...' : 'Register Key'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* mTLS Certificate Modal */}
      <Modal
        open={showMTLSModal}
        onClose={() => {
          setShowMTLSModal(false)
          setMtlsFormData({ cn: '', email: '', validity_days: 365 })
        }}
        title="Create Client Certificate"
      >
        <div className="space-y-4">
          <Input
            label="Common Name (CN)"
            value={mtlsFormData.cn}
            onChange={(e) => setMtlsFormData(prev => ({ ...prev, cn: e.target.value }))}
            placeholder="john.doe"
            helperText="Usually your username or identifier"
          />
          <Input
            label="Email (optional)"
            type="email"
            value={mtlsFormData.email}
            onChange={(e) => setMtlsFormData(prev => ({ ...prev, email: e.target.value }))}
            placeholder="john@example.com"
          />
          <Input
            label="Validity (days)"
            type="number"
            value={mtlsFormData.validity_days}
            onChange={(e) => setMtlsFormData(prev => ({ ...prev, validity_days: parseInt(e.target.value) || 365 }))}
            min="1"
            max="3650"
          />
          <p className="text-sm text-text-secondary">
            A new client certificate will be generated. Download and install it in your browser for mTLS authentication.
          </p>
          <div className="flex gap-2 pt-2">
            <Button variant="secondary" onClick={() => {
              setShowMTLSModal(false)
              setMtlsFormData({ cn: '', email: '', validity_days: 365 })
            }} className="flex-1">
              Cancel
            </Button>
            <Button 
              variant="primary" 
              onClick={handleCreateMTLS}
              disabled={!mtlsFormData.cn.trim()}
              className="flex-1"
            >
              Create Certificate
            </Button>
          </div>
        </div>
      </Modal>
    </PageLayout>
  )
}

function ChangePasswordForm({ onSubmit, onCancel }) {
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (formData.new_password !== formData.confirm_password) {
      showWarning('New passwords do not match')
      return
    }
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
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
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit">Change Password</Button>
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
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
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
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit">Create Key</Button>
      </div>
    </form>
  )
}
