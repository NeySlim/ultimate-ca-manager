/**
 * Account Page - User Profile & Security Settings
 * Uses DetailCard design system like SettingsPage
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  User, Key, FloppyDisk, Fingerprint, Certificate, 
  PencilSimple, Trash, Plus, Warning, ShieldCheck
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Badge, Modal, FormModal, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent,
  LoadingSpinner
} from '../components'
import { accountService } from '../services'
import { useAuth, useNotification, useMobile } from '../contexts'
import { ERRORS, SUCCESS, CONFIRM } from '../lib/messages'
import { formatDate } from '../lib/utils'

export default function AccountPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()

  // Tab configuration - inside component to use translations
  const TABS = [
    { id: 'profile', label: t('account.profile'), icon: User },
    { id: 'security', label: t('common.security'), icon: ShieldCheck },
    { id: 'api-keys', label: t('account.apiKeys'), icon: Key },
  ]
  
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
    }
  }

  const loadWebAuthnCredentials = async () => {
    try {
      const response = await accountService.getWebAuthnCredentials()
      setWebauthnCredentials(response.data || [])
    } catch (error) {
    }
  }

  const loadMTLSCertificates = async () => {
    try {
      const response = await accountService.getMTLSCertificates()
      setMtlsCertificates(response.data || [])
    } catch (error) {
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
        const code = await showPrompt(t('account.enterCodeToDisable'), {
          title: t('account.disableTwoFactor'),
          placeholder: '123456',
          confirmText: t('common.disable2FA')
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
      
      showSuccess(t('account.keyRegistered'))
      setShowWebAuthnModal(false)
      setWebauthnName('')
      await loadWebAuthnCredentials()
    } catch (error) {
      if (error.name === 'NotAllowedError') {
        showError(t('account.registrationCancelled'))
      } else {
        showError(error.message || t('account.registrationFailed'))
      }
    } finally {
      setWebauthnRegistering(false)
    }
  }

  const handleDeleteWebAuthn = async (credentialId) => {
    const confirmed = await showConfirm(t('account.deleteKeyConfirm'), {
      title: t('account.deleteSecurityKey'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await accountService.deleteWebAuthnCredential(credentialId)
      showSuccess(t('account.keyDeleted'))
      await loadWebAuthnCredentials()
    } catch (error) {
      showError(error.message || t('account.deleteKeyFailed'))
    }
  }

  // API Key handlers
  const handleCreateApiKey = async (keyData) => {
    try {
      const created = await accountService.createApiKey(keyData)
      showSuccess(t('account.apiKeyCreated', { key: created.key || created.data?.key }))
      setShowApiKeyModal(false)
      await loadApiKeys()
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.GENERIC)
    }
  }

  const handleDeleteApiKey = async (keyId) => {
    const confirmed = await showConfirm(t('account.deleteAPIKeyConfirm'), {
      title: t('account.deleteAPIKey'),
      confirmText: t('common.delete'),
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
    const confirmed = await showConfirm(t('account.deleteCertConfirm'), {
      title: t('common.deleteCertificate'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await accountService.deleteMTLSCertificate(certId)
      showSuccess(t('account.certificateDeleted'))
      await loadMTLSCertificates()
    } catch (error) {
      showError(error.message || t('account.deleteCertFailed'))
    }
  }

  // ============ RENDER TAB CONTENT ============

  const renderProfileContent = () => (
    <DetailContent>
      <DetailHeader
        icon={User}
        title={t('account.profileInfo')}
        subtitle={t('account.personalDetails')}
        actions={editMode ? [
          { label: t('common.cancel'), variant: 'secondary', onClick: () => setEditMode(false) },
          { label: saving ? t('common.saving') : t('common.save'), icon: FloppyDisk, onClick: handleSaveProfile, disabled: saving }
        ] : [
          { label: t('common.edit'), icon: PencilSimple, variant: 'secondary', onClick: () => setEditMode(true) }
        ]}
      />
      
      <DetailSection title={t('common.accountInformation')}>
        {editMode ? (
          <div className="space-y-4">
            <Input
              label={t('account.fullName')}
              value={formData.full_name}
              onChange={(e) => setFormData(p => ({ ...p, full_name: e.target.value }))}
              placeholder={t('account.enterYourName')}
            />
            <Input
              label={t('common.email')}
              type="email"
              value={formData.email}
              onChange={(e) => setFormData(p => ({ ...p, email: e.target.value }))}
            />
          </div>
        ) : (
          <DetailGrid>
            <DetailField label={t('common.username')} value={accountData.username || '—'} />
            <DetailField label={t('account.fullName')} value={accountData.full_name || accountData.username || '—'} />
            <DetailField label={t('common.email')} value={accountData.email || '—'} />
            <DetailField 
              label={t('common.role')} 
              value={
                <Badge variant={accountData.role === 'admin' ? 'primary' : 'secondary'}>
                  {accountData.role || t('common.user')}
                </Badge>
              } 
            />
          </DetailGrid>
        )}
      </DetailSection>
      
      <DetailSection title={t('account.accountActivity')}>
        <DetailGrid>
          <DetailField 
            label={t('account.accountCreated')} 
            value={accountData.created_at ? formatDate(accountData.created_at) : '—'} 
          />
          <DetailField 
            label={t('common.lastLogin')} 
            value={accountData.last_login ? formatDate(accountData.last_login, true) : '—'} 
          />
          <DetailField 
            label={t('account.totalLogins')} 
            value={accountData.login_count || 0} 
          />
          <DetailField 
            label={t('common.status')} 
            value={
              <Badge variant={accountData.active ? 'success' : 'danger'}>
                {accountData.active ? t('common.active') : t('common.inactive')}
              </Badge>
            } 
          />
        </DetailGrid>
      </DetailSection>
    </DetailContent>
  )

  const renderSecurityContent = () => (
    <DetailContent>
      <DetailHeader
        icon={ShieldCheck}
        title={t('common.securitySettings')}
        subtitle={t('account.manageAccountSecurity')}
      />
      
      {/* Password */}
      <DetailSection title={t('common.password')}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-text-primary">{t('account.changeYourPassword')}</p>
            <p className="text-xs text-text-tertiary mt-0.5">
              {t('account.lastChanged')}: {accountData.password_changed_at 
                ? formatDate(accountData.password_changed_at)
                : t('common.never')}
            </p>
          </div>
          <Button size="sm" onClick={() => setShowPasswordModal(true)}>
            {t('common.changePassword')}
          </Button>
        </div>
      </DetailSection>

      {/* 2FA */}
      <DetailSection title={t('common.twoFactorAuth')}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-text-primary">{t('account.authenticatorApp')}</p>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant={accountData.two_factor_enabled ? 'success' : 'secondary'}>
                {accountData.two_factor_enabled ? t('common.enabled') : t('common.disabled')}
              </Badge>
            </div>
          </div>
          <Button 
            size="sm" 
            variant={accountData.two_factor_enabled ? 'danger' : 'primary'} 
            onClick={handleToggle2FA}
          >
            {accountData.two_factor_enabled ? t('common.disable2FA') : t('common.enable2FA')}
          </Button>
        </div>
      </DetailSection>

      {/* WebAuthn */}
      <DetailSection 
        title={t('account.securityKeys')}
        subtitle={t('account.webauthnDescription')}
        actions={
          <Button size="sm" onClick={() => setShowWebAuthnModal(true)}>
            <Plus size={14} className="mr-1" />
            {t('account.addKey')}
          </Button>
        }
      >
        {webauthnCredentials.length === 0 ? (
          <div className="p-4 bg-bg-tertiary/50 border border-border rounded-lg text-center">
            <Fingerprint size={28} className="mx-auto mb-2 text-text-tertiary" />
            <p className="text-sm text-text-secondary">{t('account.noSecurityKeys')}</p>
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
                    <p className="text-sm font-medium text-text-primary">{cred.name || t('account.securityKey')}</p>
                    <p className="text-xs text-text-tertiary">
                      {t('account.added')} {formatDate(cred.created_at)}
                      {cred.last_used_at && ` • ${t('common.used')} ${formatDate(cred.last_used_at)}`}
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
      </DetailSection>

      {/* mTLS Certificates */}
      <DetailSection 
        title={t('account.clientCertificates')}
        actions={
          <Button size="sm" onClick={() => setShowMTLSModal(true)}>
            <Plus size={14} className="mr-1" />
            {t('account.addCertificate')}
          </Button>
        }
      >
        <p className="text-sm text-text-secondary mb-3">
          {t('account.useMTLSCerts')}
        </p>
        
        {mtlsCertificates.length === 0 ? (
          <div className="p-4 bg-bg-tertiary/50 border border-border rounded-lg text-center">
            <Certificate size={28} className="mx-auto mb-2 text-text-tertiary" />
            <p className="text-sm text-text-secondary">{t('account.noCertificatesEnrolled')}</p>
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
                      {t('common.expires')} {formatDate(cert.not_after)}
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
      </DetailSection>
    </DetailContent>
  )

  const renderApiKeysContent = () => (
    <DetailContent>
      <DetailHeader
        icon={Key}
        title={t('account.apiKeys')}
        subtitle={t('common.aboutAPIKeys')}
        actions={[
          { label: t('account.createKey'), icon: Plus, onClick: () => setShowApiKeyModal(true) }
        ]}
      />
      
      <HelpCard 
        variant="tip" 
        title={t('common.aboutAPIKeys')} 
        items={t('account.apiKeyTips', { returnObjects: true })} 
      />

      <DetailSection title={t('account.yourAPIKeys')}>
        {apiKeys.length === 0 ? (
          <div className="p-4 bg-bg-tertiary/50 border border-border rounded-lg text-center">
            <Key size={28} className="mx-auto mb-2 text-text-tertiary" />
            <p className="text-sm text-text-secondary">{t('account.noAPIKeys')}</p>
            <p className="text-xs text-text-tertiary mt-1">{t('account.createKeyToAccess')}</p>
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
                      {!key.is_active && <Badge variant="secondary" size="xs">{t('common.inactive')}</Badge>}
                    </div>
                    <p className="text-xs text-text-tertiary font-mono">{key.key_prefix}...</p>
                    <p className="text-xs text-text-tertiary">
                      {t('common.created')} {formatDate(key.created_at)}
                      {key.expires_at && ` • ${t('common.expires')} ${formatDate(key.expires_at)}`}
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
      </DetailSection>
    </DetailContent>
  )

  // Render content based on active tab
  const renderContent = () => {
    switch (activeTab) {
      case 'profile':
        return renderProfileContent()
      case 'security':
        return renderSecurityContent()
      case 'api-keys':
        return renderApiKeysContent()
      default:
        return renderProfileContent()
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message={t('account.loadingAccount')} />
      </div>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title={t('common.account')}
        subtitle={accountData.email || user?.username}
        icon={User}
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        tabLayout="sidebar"
        helpPageKey="account"
      >
        {renderContent()}
      </ResponsiveLayout>

      {/* ============ MODALS ============ */}

      {/* Change Password Modal */}
      <FormModal
        open={showPasswordModal}
        onOpenChange={setShowPasswordModal}
        title={t('common.changePassword')}
        onSubmit={handleChangePassword}
        submitLabel={t('common.changePassword')}
      >
        <Input
          label={t('common.currentPassword')}
          type="password"
          name="current_password"
          autoComplete="current-password"
          required
        />
        <Input
          label={t('common.newPassword')}
          type="password"
          name="new_password"
          autoComplete="new-password"
          showStrength
          required
        />
        <Input
          label={t('common.confirmNewPassword')}
          type="password"
          name="confirm_password"
          autoComplete="new-password"
          required
        />
      </FormModal>

      {/* Create API Key Modal */}
      <FormModal
        open={showApiKeyModal}
        onOpenChange={setShowApiKeyModal}
        title={t('account.createAPIKey')}
        onSubmit={handleCreateApiKey}
        submitLabel={t('account.createKey')}
      >
        <Input
          label={t('account.apiKeyName')}
          name="name"
          placeholder={t('account.keyNameExample')}
          required
        />
        <Input
          label={t('account.expiresInDays')}
          type="number"
          name="expires_in_days"
          placeholder={t('common.validityPlaceholder')}
          helperText={t('account.noExpiration')}
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
        title={t('account.enableTwoFactor')}
      >
        {qrData && (
          <div className="p-4 space-y-4">
            <div>
              <p className="text-sm text-text-secondary mb-3">
                {t('account.scanQRCode')}
              </p>
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <img src={qrData.qr_code} alt="2FA QR Code" className="w-48 h-48" />
              </div>
            </div>
            
            <div>
              <p className="text-sm text-text-secondary mb-2">
                {t('account.enterDigitCode')}
              </p>
              <Input
                type="text"
                placeholder={t('account.codePlaceholder')}
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
                  {t('account.backupCodes')}
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
                {t('common.cancel')}
              </Button>
              <Button onClick={handleConfirm2FA} disabled={confirmCode.length !== 6}>
                {t('account.verifyAndEnable')}
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
        title={t('account.registerSecurityKey')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('account.addHardwareKey')}
          </p>
          
          <Input
            label={t('account.keyName')}
            value={webauthnName}
            onChange={(e) => setWebauthnName(e.target.value)}
            placeholder={t('account.keyNamePlaceholder')}
          />
          
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => setShowWebAuthnModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button 
              onClick={handleRegisterWebAuthn} 
              disabled={webauthnRegistering || !webauthnName.trim()}
            >
              {webauthnRegistering ? t('account.waitingForKey') : t('account.registerKey')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* mTLS Certificate Modal */}
      <Modal
        open={showMTLSModal}
        onOpenChange={setShowMTLSModal}
        title={t('account.addCertificate')}
      >
        <div className="p-4">
          <p className="text-sm text-text-secondary">
            {t('account.mtlsComingSoon')}
          </p>
          <div className="flex justify-end pt-4 border-t border-border mt-4">
            <Button variant="secondary" onClick={() => setShowMTLSModal(false)}>
              {t('common.close')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
