/**
 * Account Page - User Profile & Security Settings
 * Redesigned to match Settings page pattern (horizontal tabs)
 */
import { useState, useEffect } from 'react'
import { 
  User, LockKey, Key, FloppyDisk, Fingerprint, Certificate, 
  PencilSimple, Trash, Plus, Eye, EyeSlash, Copy, Check,
  ShieldCheck, Clock, Warning
} from '@phosphor-icons/react'
import {
  Button, Input, Badge, Modal, FormModal, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactHeader,
  UnifiedPageHeader, LoadingSpinner
} from '../components'
import { accountService } from '../services'
import { useAuth, useNotification, useMobile } from '../contexts'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'
import { formatDate, cn } from '../lib/utils'

// Tab configuration
const TABS = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'security', label: 'Security', icon: ShieldCheck },
  { id: 'api-keys', label: 'API Keys', icon: Key },
]

export default function AccountPage() {
  const { user } = useAuth()
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  
  // State
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')
  const [accountData, setAccountData] = useState({})
  const [editMode, setEditMode] = useState(false)
  const [formData, setFormData] = useState({ full_name: '', email: '' })
  
  // Security state
  const [apiKeys, setApiKeys] = useState([])
  const [webauthnCredentials, setWebauthnCredentials] = useState([])
  const [mtlsCertificates, setMtlsCertificates] = useState([])
  
  // Modals
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [showWebAuthnModal, setShowWebAuthnModal] = useState(false)
  const [showMTLSModal, setShowMTLSModal] = useState(false)
  
  // 2FA state
  const [qrData, setQrData] = useState(null)
  const [confirmCode, setConfirmCode] = useState('')
  
  // WebAuthn state
  const [webauthnName, setWebauthnName] = useState('')
  const [webauthnRegistering, setWebauthnRegistering] = useState(false)

  // Load data
  useEffect(() => {
    loadAll()
  }, [])

  const loadAll = async () => {
    setLoading(true)
    try {
      await Promise.all([
        loadAccount(),
        loadApiKeys(),
        loadWebAuthnCredentials(),
        loadMTLSCertificates()
      ])
    } finally {
      setLoading(false)
    }
  }

  const loadAccount = async () => {
    try {
      const response = await accountService.getProfile()
      const data = response.data || response
      setAccountData(data)
      setFormData({ full_name: data.full_name || '', email: data.email || '' })
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.GENERIC)
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

  // Profile handlers
  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      await accountService.updateProfile(formData)
      showSuccess(SUCCESS.UPDATE.USER)
      setEditMode(false)
      await loadAccount()
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.USER)
    } finally {
      setSaving(false)
    }
  }

  // Password handlers
  const handleChangePassword = async (passwordData) => {
    try {
      await accountService.changePassword(passwordData)
      showSuccess(SUCCESS.OTHER.PASSWORD_CHANGED)
      setShowPasswordModal(false)
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.GENERIC)
    }
  }

  // 2FA handlers
  const handleToggle2FA = async () => {
    try {
      if (accountData.two_factor_enabled) {
        const code = await showPrompt('Enter your 2FA code to disable:', {
          title: 'Disable Two-Factor Authentication',
          placeholder: '123456',
          confirmText: 'Disable 2FA'
        })
        if (!code) return
        await accountService.disable2FA(code)
        showSuccess(SUCCESS.OTHER.TWO_FACTOR_DISABLED)
        await loadAccount()
      } else {
        const response = await accountService.enable2FA()
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
      await loadAccount()
    } catch (error) {
      showError(error.message || ERRORS.VALIDATION.REQUIRED_FIELD)
    }
  }

  // WebAuthn handlers
  const handleRegisterWebAuthn = async () => {
    if (!webauthnName.trim()) {
      showError(ERRORS.VALIDATION.REQUIRED_FIELD)
      return
    }
    
    setWebauthnRegistering(true)
    try {
      const response = await accountService.startWebAuthnRegistration()
      const options = response.data
      
      const base64urlToUint8Array = (base64url) => {
        let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/')
        while (base64.length % 4) base64 += '='
        return Uint8Array.from(atob(base64), c => c.charCodeAt(0))
      }
      
      const stringToUint8Array = (str) => new TextEncoder().encode(str)
      
      const publicKeyOptions = {
        challenge: base64urlToUint8Array(options.challenge),
        rp: options.rp,
        user: {
          id: stringToUint8Array(String(options.user.id)),
          name: options.user.name,
          displayName: options.user.displayName
        },
        pubKeyCredParams: options.pubKeyCredParams,
        timeout: options.timeout || 60000,
        authenticatorSelection: options.authenticatorSelection,
        attestation: options.attestation || 'none'
      }
      
      if (options.excludeCredentials?.length > 0) {
        publicKeyOptions.excludeCredentials = options.excludeCredentials.map(c => ({
          type: c.type,
          id: base64urlToUint8Array(c.id),
          transports: c.transports
        }))
      }
      
      const credential = await navigator.credentials.create({ publicKey: publicKeyOptions })
      
      const uint8ArrayToBase64url = (arr) => {
        const str = String.fromCharCode.apply(null, new Uint8Array(arr))
        return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
      }
      
      const attestationResponse = {
        id: credential.id,
        rawId: uint8ArrayToBase64url(credential.rawId),
        type: credential.type,
        response: {
          clientDataJSON: uint8ArrayToBase64url(credential.response.clientDataJSON),
          attestationObject: uint8ArrayToBase64url(credential.response.attestationObject)
        }
      }
      
      await accountService.completeWebAuthnRegistration({
        credential: attestationResponse,
        name: webauthnName
      })
      
      showSuccess('Security key registered successfully')
      setShowWebAuthnModal(false)
      setWebauthnName('')
      await loadWebAuthnCredentials()
    } catch (error) {
      if (error.name === 'NotAllowedError') {
        showError('Registration cancelled or timed out')
      } else {
        showError(error.message || 'Failed to register security key')
      }
    } finally {
      setWebauthnRegistering(false)
    }
  }

  const handleDeleteWebAuthn = async (credentialId) => {
    const confirmed = await showConfirm('Delete this security key?', {
      title: 'Delete Security Key',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await accountService.deleteWebAuthnCredential(credentialId)
      showSuccess('Security key deleted')
      await loadWebAuthnCredentials()
    } catch (error) {
      showError(error.message || 'Failed to delete security key')
    }
  }

  // API Key handlers
  const handleCreateApiKey = async (keyData) => {
    try {
      const created = await accountService.createApiKey(keyData)
      showSuccess(`API key created. Key: ${created.key || created.data?.key}`)
      setShowApiKeyModal(false)
      await loadApiKeys()
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
      await loadApiKeys()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.GENERIC)
    }
  }

  // mTLS handlers
  const handleDeleteMTLS = async (certId) => {
    const confirmed = await showConfirm('Delete this client certificate?', {
      title: 'Delete Certificate',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await accountService.deleteMTLSCertificate(certId)
      showSuccess('Certificate deleted')
      await loadMTLSCertificates()
    } catch (error) {
      showError(error.message || 'Failed to delete certificate')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  // ============ RENDER TABS ============

  const renderProfileTab = () => (
    <div className="p-4 md:p-6 space-y-6">
      {/* Edit Mode Toggle */}
      <div className="flex justify-end">
        {editMode ? (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditMode(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSaveProfile} disabled={saving}>
              <FloppyDisk size={16} className="mr-1" />
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        ) : (
          <Button variant="secondary" size="sm" onClick={() => setEditMode(true)}>
            <PencilSimple size={16} className="mr-1" />
            Edit Profile
          </Button>
        )}
      </div>

      {/* Account Info */}
      <CompactSection title="Account Information" icon={User} defaultOpen>
        <CompactGrid>
          <CompactField label="Username" value={accountData.username || '—'} />
          <CompactField 
            label="Email" 
            value={editMode ? (
              <Input
                value={formData.email}
                onChange={(e) => setFormData(p => ({ ...p, email: e.target.value }))}
                className="mt-1"
              />
            ) : (accountData.email || '—')} 
          />
          <CompactField 
            label="Full Name" 
            value={editMode ? (
              <Input
                value={formData.full_name}
                onChange={(e) => setFormData(p => ({ ...p, full_name: e.target.value }))}
                placeholder="Enter your name"
                className="mt-1"
              />
            ) : (accountData.full_name || '—')} 
          />
          <CompactField 
            label="Role" 
            value={
              <Badge variant={accountData.role === 'admin' ? 'primary' : 'secondary'}>
                {accountData.role || 'User'}
              </Badge>
            } 
          />
        </CompactGrid>
      </CompactSection>

      {/* Account Stats */}
      <CompactSection title="Account Activity" icon={Clock} defaultOpen>
        <CompactGrid>
          <CompactField 
            label="Account Created" 
            value={accountData.created_at ? formatDate(accountData.created_at) : '—'} 
          />
          <CompactField 
            label="Last Login" 
            value={accountData.last_login ? formatDate(accountData.last_login, true) : '—'} 
          />
          <CompactField 
            label="Total Logins" 
            value={accountData.login_count || 0} 
          />
          <CompactField 
            label="Status" 
            value={
              <Badge variant={accountData.active ? 'success' : 'danger'}>
                {accountData.active ? 'Active' : 'Inactive'}
              </Badge>
            } 
          />
        </CompactGrid>
      </CompactSection>
    </div>
  )

  const renderSecurityTab = () => (
    <div className="p-4 md:p-6 space-y-6">
      {/* Password */}
      <CompactSection title="Password" icon={LockKey} defaultOpen>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-text-primary">Change your password</p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Last changed: {accountData.password_changed_at 
                ? formatDate(accountData.password_changed_at)
                : 'Never'}
            </p>
          </div>
          <Button size="sm" onClick={() => setShowPasswordModal(true)}>
            Change Password
          </Button>
        </div>
      </CompactSection>

      {/* 2FA */}
      <CompactSection title="Two-Factor Authentication" icon={ShieldCheck} defaultOpen>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-text-primary">Authenticator App (TOTP)</p>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant={accountData.two_factor_enabled ? 'success' : 'secondary'}>
                {accountData.two_factor_enabled ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
          </div>
          <Button 
            size="sm" 
            variant={accountData.two_factor_enabled ? 'danger' : 'primary'} 
            onClick={handleToggle2FA}
          >
            {accountData.two_factor_enabled ? 'Disable 2FA' : 'Enable 2FA'}
          </Button>
        </div>
      </CompactSection>

      {/* WebAuthn / Security Keys */}
      <CompactSection 
        title="Security Keys (WebAuthn/FIDO2)" 
        icon={Fingerprint} 
        badge={webauthnCredentials.length > 0 ? String(webauthnCredentials.length) : undefined}
        defaultOpen
      >
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <p className="text-sm text-text-secondary">
              Use YubiKey, TouchID, or Windows Hello for passwordless login
            </p>
            <Button size="sm" onClick={() => setShowWebAuthnModal(true)}>
              <Plus size={14} className="mr-1" />
              Add Key
            </Button>
          </div>
          
          {webauthnCredentials.length === 0 ? (
            <div className="p-4 bg-bg-tertiary/50 border border-border rounded-lg text-center">
              <Fingerprint size={28} className="mx-auto mb-2 text-text-tertiary" />
              <p className="text-sm text-text-secondary">No security keys registered</p>
            </div>
          ) : (
            <div className="space-y-2">
              {webauthnCredentials.map(cred => (
                <div 
                  key={cred.id} 
                  className="flex items-center justify-between p-3 bg-bg-tertiary/50 border border-border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <Fingerprint size={20} className="text-accent-primary" />
                    <div>
                      <p className="text-sm font-medium text-text-primary">{cred.name || 'Security Key'}</p>
                      <p className="text-xs text-text-tertiary">
                        Added {formatDate(cred.created_at)}
                        {cred.last_used_at && ` • Used ${formatDate(cred.last_used_at)}`}
                      </p>
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => handleDeleteWebAuthn(cred.id)}>
                    <Trash size={16} className="text-status-danger" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CompactSection>

      {/* mTLS Certificates */}
      <CompactSection 
        title="Client Certificates (mTLS)" 
        icon={Certificate}
        badge={mtlsCertificates.length > 0 ? String(mtlsCertificates.length) : undefined}
        defaultOpen
      >
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <p className="text-sm text-text-secondary">
              Use X.509 client certificates for mutual TLS authentication
            </p>
            <Button size="sm" onClick={() => setShowMTLSModal(true)}>
              <Plus size={14} className="mr-1" />
              Add Certificate
            </Button>
          </div>
          
          {mtlsCertificates.length === 0 ? (
            <div className="p-4 bg-bg-tertiary/50 border border-border rounded-lg text-center">
              <Certificate size={28} className="mx-auto mb-2 text-text-tertiary" />
              <p className="text-sm text-text-secondary">No client certificates enrolled</p>
            </div>
          ) : (
            <div className="space-y-2">
              {mtlsCertificates.map(cert => (
                <div 
                  key={cert.id} 
                  className="flex items-center justify-between p-3 bg-bg-tertiary/50 border border-border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <Certificate size={20} className="text-accent-primary" />
                    <div>
                      <p className="text-sm font-medium text-text-primary">{cert.cn || cert.subject}</p>
                      <p className="text-xs text-text-tertiary">
                        Expires {formatDate(cert.not_after)}
                      </p>
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => handleDeleteMTLS(cert.id)}>
                    <Trash size={16} className="text-status-danger" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CompactSection>
    </div>
  )

  const renderApiKeysTab = () => (
    <div className="p-4 md:p-6 space-y-6">
      <HelpCard 
        variant="tip" 
        title="API Keys" 
        items={[
          'API keys allow programmatic access to UCM',
          'Keep your keys secret and rotate them regularly',
          'Each key can have a custom expiration date'
        ]} 
      />

      <CompactSection 
        title="Your API Keys" 
        icon={Key}
        badge={apiKeys.length > 0 ? String(apiKeys.length) : undefined}
        defaultOpen
      >
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowApiKeyModal(true)}>
              <Plus size={14} className="mr-1" />
              Create Key
            </Button>
          </div>
          
          {apiKeys.length === 0 ? (
            <div className="p-4 bg-bg-tertiary/50 border border-border rounded-lg text-center">
              <Key size={28} className="mx-auto mb-2 text-text-tertiary" />
              <p className="text-sm text-text-secondary">No API keys created</p>
              <p className="text-xs text-text-tertiary mt-1">Create a key to access UCM API</p>
            </div>
          ) : (
            <div className="space-y-2">
              {apiKeys.map(key => (
                <div 
                  key={key.id} 
                  className="flex items-center justify-between p-3 bg-bg-tertiary/50 border border-border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <Key size={20} className={key.is_active ? 'text-accent-primary' : 'text-text-tertiary'} />
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-text-primary">{key.name}</p>
                        {!key.is_active && <Badge variant="secondary" size="xs">Inactive</Badge>}
                      </div>
                      <p className="text-xs text-text-tertiary font-mono">{key.key_prefix}...</p>
                      <p className="text-xs text-text-tertiary">
                        Created {formatDate(key.created_at)}
                        {key.expires_at && ` • Expires ${formatDate(key.expires_at)}`}
                      </p>
                    </div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => handleDeleteApiKey(key.id)}>
                    <Trash size={16} className="text-status-danger" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CompactSection>
    </div>
  )

  return (
    <div className="h-full flex flex-col">
      {/* Header with tabs */}
      <UnifiedPageHeader
        icon={User}
        title="My Account"
        subtitle={accountData.email || user?.username}
        badge={
          <Badge variant={accountData.role === 'admin' ? 'primary' : 'secondary'}>
            {accountData.role || 'User'}
          </Badge>
        }
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'profile' && renderProfileTab()}
        {activeTab === 'security' && renderSecurityTab()}
        {activeTab === 'api-keys' && renderApiKeysTab()}
      </div>

      {/* ============ MODALS ============ */}

      {/* Change Password Modal */}
      <FormModal
        open={showPasswordModal}
        onOpenChange={setShowPasswordModal}
        title="Change Password"
        onSubmit={handleChangePassword}
        submitLabel="Change Password"
      >
        <Input
          label="Current Password"
          type="password"
          name="current_password"
          required
        />
        <Input
          label="New Password"
          type="password"
          name="new_password"
          required
        />
        <Input
          label="Confirm New Password"
          type="password"
          name="confirm_password"
          required
        />
      </FormModal>

      {/* Create API Key Modal */}
      <FormModal
        open={showApiKeyModal}
        onOpenChange={setShowApiKeyModal}
        title="Create API Key"
        onSubmit={handleCreateApiKey}
        submitLabel="Create Key"
      >
        <Input
          label="Key Name"
          name="name"
          placeholder="e.g., CI/CD Pipeline"
          required
        />
        <Input
          label="Expires In (days)"
          type="number"
          name="expires_in_days"
          placeholder="365"
          helperText="Leave empty for no expiration"
        />
      </FormModal>

      {/* 2FA Setup Modal */}
      <Modal
        open={show2FAModal}
        onOpenChange={(open) => {
          if (!open) {
            setShow2FAModal(false)
            setQrData(null)
            setConfirmCode('')
          }
        }}
        title="Enable Two-Factor Authentication"
      >
        {qrData && (
          <div className="p-4 space-y-4">
            <div>
              <p className="text-sm text-text-secondary mb-3">
                1. Scan this QR code with your authenticator app:
              </p>
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <img src={qrData.qr_code} alt="2FA QR Code" className="w-48 h-48" />
              </div>
            </div>
            
            <div>
              <p className="text-sm text-text-secondary mb-2">
                2. Enter the 6-digit code:
              </p>
              <Input
                type="text"
                placeholder="000000"
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                className="text-center text-2xl tracking-widest font-mono"
              />
            </div>
            
            {qrData.backup_codes && (
              <div className="p-3 bg-status-warning/10 border border-status-warning/30 rounded-lg">
                <p className="text-sm font-medium text-status-warning flex items-center gap-2">
                  <Warning size={16} />
                  Backup Codes - Save These!
                </p>
                <div className="mt-2 grid grid-cols-2 gap-1 font-mono text-xs">
                  {qrData.backup_codes.map((code, i) => (
                    <span key={i} className="text-text-secondary">{code}</span>
                  ))}
                </div>
              </div>
            )}
            
            <div className="flex justify-end gap-2 pt-4 border-t border-border">
              <Button variant="secondary" onClick={() => setShow2FAModal(false)}>
                Cancel
              </Button>
              <Button onClick={handleConfirm2FA} disabled={confirmCode.length !== 6}>
                Verify & Enable
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* WebAuthn Registration Modal */}
      <Modal
        open={showWebAuthnModal}
        onOpenChange={(open) => {
          if (!open) {
            setShowWebAuthnModal(false)
            setWebauthnName('')
          }
        }}
        title="Register Security Key"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            Add a hardware security key (YubiKey, TouchID, Windows Hello) for passwordless login.
          </p>
          
          <Input
            label="Key Name"
            value={webauthnName}
            onChange={(e) => setWebauthnName(e.target.value)}
            placeholder="e.g., YubiKey 5, MacBook TouchID"
          />
          
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => setShowWebAuthnModal(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleRegisterWebAuthn} 
              disabled={webauthnRegistering || !webauthnName.trim()}
            >
              {webauthnRegistering ? 'Waiting for key...' : 'Register Key'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* mTLS Certificate Modal - TODO: Implement */}
      <Modal
        open={showMTLSModal}
        onOpenChange={setShowMTLSModal}
        title="Add Client Certificate"
      >
        <div className="p-4">
          <p className="text-sm text-text-secondary">
            mTLS certificate enrollment coming soon.
          </p>
          <div className="flex justify-end pt-4 border-t border-border mt-4">
            <Button variant="secondary" onClick={() => setShowMTLSModal(false)}>
              Close
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
