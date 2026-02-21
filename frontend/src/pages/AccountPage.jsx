/**
 * Account Page - User Profile & Security Settings
 * Uses DetailCard design system like SettingsPage
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  User, Key, FloppyDisk, Fingerprint, Certificate, 
  PencilSimple, Trash, Plus, Warning, ShieldCheck, Download
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Badge, Modal, FormModal, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent,
  LoadingSpinner
} from '../components'
import { accountService, casService, userCertificatesService } from '../services'
import { useAuth, useNotification, useMobile } from '../contexts'
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
  const [cas, setCas] = useState([])
  
  // Modals
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [showWebAuthnModal, setShowWebAuthnModal] = useState(false)
  const [showMTLSModal, setShowMTLSModal] = useState(false)
  const [mtlsCreating, setMtlsCreating] = useState(false)
  const [mtlsResult, setMtlsResult] = useState(null)
  const [mtlsForm, setMtlsForm] = useState({ name: '', validity_days: 365, ca_id: '' })
  const [mtlsTab, setMtlsTab] = useState('generate')
  const [mtlsImportForm, setMtlsImportForm] = useState({ name: '', pem: '' })
  
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
        loadMTLSCertificates(),
        loadCAs(),
      ])
    } finally {
      setLoading(false)
    }
  }

  const loadCAs = async () => {
    try {
      const response = await casService.getAll()
      setCas(response.data || [])
    } catch {}
  }

  const loadAccount = async () => {
    try {
      const response = await accountService.getProfile()
      const data = response.data || response
      setAccountData(data)
      setFormData({ full_name: data.full_name || '', email: data.email || '' })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
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
      showSuccess(t('messages.success.update.user'))
      setEditMode(false)
      await loadAccount()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.user'))
    } finally {
      setSaving(false)
    }
  }

  // Password handlers
  const handleChangePassword = async (passwordData) => {
    try {
      await accountService.changePassword(passwordData)
      showSuccess(t('messages.success.other.passwordChanged'))
      setShowPasswordModal(false)
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
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
        showSuccess(t('messages.success.other.twoFactorDisabled'))
        await loadAccount()
      } else {
        const response = await accountService.enable2FA()
        setQrData(response.data || response)
        setShow2FAModal(true)
      }
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  const handleConfirm2FA = async () => {
    try {
      await accountService.confirm2FA(confirmCode)
      showSuccess(t('messages.success.other.twoFactorEnabled'))
      setShow2FAModal(false)
      setQrData(null)
      setConfirmCode('')
      await loadAccount()
    } catch (error) {
      showError(error.message || t('messages.errors.validation.requiredField'))
    }
  }

  // WebAuthn handlers
  const handleRegisterWebAuthn = async () => {
    if (!webauthnName.trim()) {
      showError(t('messages.errors.validation.requiredField'))
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
      showError(error.message || t('messages.errors.createFailed.generic'))
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
      showSuccess(t('messages.success.delete.generic'))
      await loadApiKeys()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
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

  const handleCreateMTLS = async () => {
    setMtlsCreating(true)
    setMtlsResult(null)
    try {
      const response = await accountService.createMTLSCertificate({
        name: mtlsForm.name || undefined,
        validity_days: mtlsForm.validity_days,
        ca_id: mtlsForm.ca_id || undefined,
      })
      const data = response.data || {}
      setMtlsResult(data)
      showSuccess(t('account.mtlsCertCreated'))
      await loadMTLSCertificates()
    } catch (error) {
      showError(error.message || t('account.mtlsCertCreateFailed'))
    } finally {
      setMtlsCreating(false)
    }
  }

  const handleCloseMTLSModal = () => {
    setShowMTLSModal(false)
    setMtlsResult(null)
    setMtlsForm({ name: '', validity_days: 365, ca_id: '' })
    setMtlsImportForm({ name: '', pem: '' })
    setMtlsTab('generate')
  }

  const handleImportMTLS = async () => {
    if (!mtlsImportForm.pem.trim()) {
      showError(t('account.mtlsPemRequired'))
      return
    }
    setMtlsCreating(true)
    try {
      await accountService.importMTLSCertificate(mtlsImportForm.pem, mtlsImportForm.name)
      showSuccess(t('account.mtlsCertImported'))
      await loadMTLSCertificates()
      handleCloseMTLSModal()
    } catch (error) {
      showError(error.message || t('account.mtlsCertImportFailed'))
    } finally {
      setMtlsCreating(false)
    }
  }

  const handlePemFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (evt) => {
      setMtlsImportForm(prev => ({ ...prev, pem: evt.target.result }))
    }
    reader.readAsText(file)
  }

  const handleExportCert = async (certId, format) => {
    try {
      const blob = await userCertificatesService.export(certId, format)
      const ext = format === 'pkcs12' ? 'p12' : 'pem'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `certificate.${ext}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      showSuccess(t('userCertificates.exportSuccess'))
    } catch (error) {
      showError(error.message || t('userCertificates.exportError'))
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
          <Button type="button" size="sm" onClick={() => setShowPasswordModal(true)}>
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
          <Button type="button" size="sm" onClick={() => setShowWebAuthnModal(true)}>
            <Plus size={14} className="mr-1" />
            {t('account.addKey')}
          </Button>
        }
      >
        {webauthnCredentials.length === 0 ? (
          <div className="p-4 bg-tertiary-50 border border-border rounded-lg text-center">
            <Fingerprint size={28} className="mx-auto mb-2 text-text-tertiary" />
            <p className="text-sm text-text-secondary">{t('account.noSecurityKeys')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {webauthnCredentials.map(cred => (
              <div 
                key={cred.id} 
                className="flex items-center justify-between p-3 bg-tertiary-50 border border-border rounded-lg"
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
                <Button type="button" size="sm" variant="ghost" onClick={() => handleDeleteWebAuthn(cred.id)}>
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
          <Button type="button" size="sm" onClick={() => setShowMTLSModal(true)}>
            <Plus size={14} className="mr-1" />
            {t('account.addCertificate')}
          </Button>
        }
      >
        <p className="text-sm text-text-secondary mb-3">
          {t('account.useMTLSCerts')}
        </p>
        
        {mtlsCertificates.length === 0 ? (
          <div className="p-4 bg-tertiary-50 border border-border rounded-lg text-center">
            <Certificate size={28} className="mx-auto mb-2 text-text-tertiary" />
            <p className="text-sm text-text-secondary">{t('account.noCertificatesEnrolled')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {mtlsCertificates.map(cert => (
              <div 
                key={cert.id} 
                className="flex items-center justify-between p-3 bg-tertiary-50 border border-border rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <Certificate size={20} className="text-accent-primary" />
                  <div>
                    <p className="text-sm font-medium text-text-primary">{cert.name || cert.cert_subject}</p>
                    <p className="text-xs text-text-tertiary">
                      {t('common.expires')} {formatDate(cert.valid_until)}
                      {cert.last_used_at && ` • ${t('common.used')} ${formatDate(cert.last_used_at)}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Badge variant={cert.enabled ? 'success' : 'warning'} size="sm">
                    {cert.enabled ? t('common.active') : t('common.disabled')}
                  </Badge>
                  <Button type="button" size="sm" variant="ghost" title={t('account.downloadPEM')} onClick={() => handleExportCert(cert.cert_id || cert.id, 'pem')}>
                    <Download size={16} className="text-accent-primary" />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => handleDeleteMTLS(cert.id)}>
                    <Trash size={16} className="text-status-danger" />
                  </Button>
                </div>
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
          <div className="p-4 bg-tertiary-50 border border-border rounded-lg text-center">
            <Key size={28} className="mx-auto mb-2 text-text-tertiary" />
            <p className="text-sm text-text-secondary">{t('account.noAPIKeys')}</p>
            <p className="text-xs text-text-tertiary mt-1">{t('account.createKeyToAccess')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {apiKeys.map(key => (
              <div 
                key={key.id} 
                className="flex items-center justify-between p-3 bg-tertiary-50 border border-border rounded-lg"
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
                <Button type="button" size="sm" variant="ghost" onClick={() => handleDeleteApiKey(key.id)}>
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
              <div className="p-3 bg-status-warning-op10 border border-status-warning-op30 rounded-lg">
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
              <Button type="button" variant="secondary" onClick={() => setShow2FAModal(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="button" onClick={handleConfirm2FA} disabled={confirmCode.length !== 6}>
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
            <Button type="button" variant="secondary" onClick={() => setShowWebAuthnModal(false)}>
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
        onOpenChange={handleCloseMTLSModal}
        title={t('account.addCertificate')}
      >
        <div className="p-4 space-y-4">
          {mtlsResult ? (
            <>
              <div className="p-3 rounded-lg bg-status-success-op10 text-sm text-status-success font-medium">
                {t('account.mtlsCertCreated')}
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-text-secondary font-medium">{t('common.certificate')}</label>
                  <textarea
                    readOnly
                    value={mtlsResult.certificate || ''}
                    className="w-full h-24 mt-1 p-2 text-xs font-mono bg-bg-tertiary border border-border rounded-lg resize-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary font-medium">{t('account.privateKey')}</label>
                  <textarea
                    readOnly
                    value={mtlsResult.private_key || ''}
                    className="w-full h-24 mt-1 p-2 text-xs font-mono bg-bg-tertiary border border-border rounded-lg resize-none"
                  />
                </div>
                <div className="flex items-start gap-2 p-3 rounded-lg bg-status-success-op10 text-xs text-status-success">
                  <ShieldCheck size={16} weight="fill" className="flex-shrink-0 mt-0.5" />
                  <span>{t('account.mtlsCertManaged')}</span>
                </div>
              </div>
              <div className="flex justify-between pt-4 border-t border-border">
                <Button type="button" variant="outline" size="sm" onClick={() => handleExportCert(mtlsResult.cert_id || mtlsResult.id, 'pem')}>
                  <Download size={16} className="mr-1" />
                  {t('account.downloadPEM')}
                </Button>
                <Button type="button" variant="secondary" onClick={handleCloseMTLSModal}>
                  {t('common.close')}
                </Button>
              </div>
            </>
          ) : (
            <>
              {/* Tab selector */}
              <div className="flex border-b border-border">
                <button
                  type="button"
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    mtlsTab === 'generate' 
                      ? 'border-accent-primary text-accent-primary' 
                      : 'border-transparent text-text-secondary hover:text-text-primary'
                  }`}
                  onClick={() => setMtlsTab('generate')}
                >
                  {t('account.mtlsGenerate')}
                </button>
                <button
                  type="button"
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    mtlsTab === 'import' 
                      ? 'border-accent-primary text-accent-primary' 
                      : 'border-transparent text-text-secondary hover:text-text-primary'
                  }`}
                  onClick={() => setMtlsTab('import')}
                >
                  {t('account.mtlsImport')}
                </button>
              </div>

              {mtlsTab === 'generate' ? (
                <>
                  <Input
                    label={t('account.mtlsCertName')}
                    value={mtlsForm.name}
                    onChange={(e) => setMtlsForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder={`${user?.username || 'user'} mTLS`}
                  />
                  <Select
                    label={t('account.mtlsIssuingCA')}
                    value={mtlsForm.ca_id}
                    onChange={(val) => setMtlsForm(prev => ({ ...prev, ca_id: val }))}
                    placeholder={t('account.mtlsDefaultCA')}
                    options={cas.filter(ca => ca.has_private_key !== false).map(ca => ({
                      value: ca.refid || String(ca.id),
                      label: ca.descr || ca.subject || ca.refid,
                    }))}
                  />
                  <Input
                    label={t('account.mtlsValidityDays')}
                    type="number"
                    value={mtlsForm.validity_days}
                    onChange={(e) => setMtlsForm(prev => ({ ...prev, validity_days: parseInt(e.target.value) || 365 }))}
                    min="1"
                    max="3650"
                  />
                  <div className="flex justify-end gap-2 pt-4 border-t border-border">
                    <Button type="button" variant="secondary" onClick={handleCloseMTLSModal}>
                      {t('common.cancel')}
                    </Button>
                    <Button type="button" onClick={handleCreateMTLS} loading={mtlsCreating} disabled={mtlsCreating}>
                      <Certificate size={16} />
                      {t('account.generateCertificate')}
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <Input
                    label={t('account.mtlsCertName')}
                    value={mtlsImportForm.name}
                    onChange={(e) => setMtlsImportForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder={t('account.mtlsImportNamePlaceholder')}
                  />
                  <div>
                    <label className="block text-sm font-medium text-text-primary mb-1">
                      {t('account.mtlsPemData')}
                    </label>
                    <textarea
                      value={mtlsImportForm.pem}
                      onChange={(e) => setMtlsImportForm(prev => ({ ...prev, pem: e.target.value }))}
                      placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                      className="w-full h-32 p-2 text-xs font-mono bg-bg-tertiary border border-border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-accent-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">{t('account.mtlsOrUploadFile')}</label>
                    <input
                      type="file"
                      accept=".pem,.crt,.cer"
                      onChange={handlePemFileUpload}
                      className="block w-full text-xs text-text-secondary file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-border file:text-sm file:font-medium file:bg-bg-secondary file:text-text-primary hover:file:bg-bg-tertiary"
                    />
                  </div>
                  <div className="flex justify-end gap-2 pt-4 border-t border-border">
                    <Button type="button" variant="secondary" onClick={handleCloseMTLSModal}>
                      {t('common.cancel')}
                    </Button>
                    <Button type="button" onClick={handleImportMTLS} loading={mtlsCreating} disabled={mtlsCreating || !mtlsImportForm.pem.trim()}>
                      <Certificate size={16} />
                      {t('account.importCertificate')}
                    </Button>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </Modal>
    </>
  )
}
