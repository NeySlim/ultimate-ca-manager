/**
 * Account page, on the mockup's sectioned form (settingsView()): the table of contents, then the
 * profile, the security of the sign-in and the API keys, each in its frame, one page; the profile's
 * fields save with the save bar. Its dialogs are the mockup's modal().
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { accountService, casService, userCertificatesService } from '../services'
import { hiddenFromIssuance, listedForIssuance, pickerCas, unlistedPickerCas } from '../lib/caSelection'
import { HiddenCasToggle } from '../components/cas/HiddenCasToggle'
import { useAuth, useNotification, useInspector } from '../contexts'
import { holdSignOut } from '../services/apiClient'
import { loginUrl } from '../navigation/safeNext'
import { useClipboard, usePermission } from '../hooks'
import { formatDate, downloadBlob } from '../lib/utils'
import { canExportPrivateKey } from '../lib/exportPermissions'
import { downloadExport } from '../lib/exportDownload'
import { reportSilentFailure } from '../lib/silentFailure'
import { localOnlyRevocationWarning } from '../lib/revocationOutcome'
import { apiKeyScopePermissions } from '../lib/apiKeyScopes'
import { describePermissions } from '../lib/rbacPermissions'
import { useUnloadGuard } from '../hooks/useSaveParts'
import { usePhoneWidth } from '../hooks/useMediaQuery'
import { keepDraft, readDraft } from '../lib/draftMemory'
import { Zone, PageHead, Btn, IconBtn, Pill, Facts, RecordList, RecordRow, SkeletonPanel, AtelierDialog } from '../components/atelier'
import { SettingsLayout, SettingsToc, SettingsJump, SettingsFrame, SettingsGroup, SettingsSaveBar } from '../components/atelier/SettingsView'
import { Field, FormModal, Input, NumberInput, Notice, SecretInput, Select, Textarea, ToggleSwitch } from '../components/atelier/Form'
import { useSectionParam } from '../components/atelier/useSectionParam'
import { MtlsCertificateDialog } from '../components/mtls/MtlsCertificateDialog'
import { validityDays } from '../components/mtls/validity'
import { ExportDialog } from './certificates/dialogs/ExportDialog'
import { ROLE_KEYS } from './users/userFacts'
import { languages } from '../i18n'
import ApiKeyList from './account/ApiKeyList'
import { chooseLanguage } from '../lib/chooseLanguage'

// Profile edit left pending, kept for the tab (lib/draftMemory)
const PROFILE_DRAFT = 'account:profile'
const SECTION_IDS = ['profile', 'security', 'api-keys']
const NO_KEY_FORM = { name: '', expires_days: '', scope: 'full' }

export default function AccountPage() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { showSuccess, showError, showWarning, showConfirm, showPrompt } = useNotification()
  const { copy } = useClipboard()
  const { hasPermission } = usePermission()
  const { closeOnNav, toggleCloseOnNav } = useInspector()

  const [loading, setLoading] = useState(true)
  // A wide screen holds the save state in the page head; a phone keeps the bar under the form
  const phone = usePhoneWidth()
  // The section a link names (/account?tab=security) is the one the page lands on
  const [activeTab, setActiveTab] = useSectionParam(SECTION_IDS, 'profile', { stacked: true, ready: !loading })
  const [saving, setSaving] = useState(false)
  const [accountData, setAccountData] = useState({})
  const [formData, setFormData] = useState({ full_name: '', email: '' })
  const keptProfile = useRef(readDraft(PROFILE_DRAFT))
  const saveState = useRef(null)
  const [announce, setAnnounce] = useState('')

  const [apiKeys, setApiKeys] = useState([])
  const [apiKeysLoading, setApiKeysLoading] = useState(true)
  const [webauthnCredentials, setWebauthnCredentials] = useState([])
  const [mtlsCertificates, setMtlsCertificates] = useState([])
  const [cas, setCas] = useState([])

  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  // The freshly created key, shown once in its dialog (#90)
  const [newApiKey, setNewApiKey] = useState(null)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [showWebAuthnModal, setShowWebAuthnModal] = useState(false)
  const [showMTLSModal, setShowMTLSModal] = useState(false)
  const [mtlsCreating, setMtlsCreating] = useState(false)
  const [mtlsResult, setMtlsResult] = useState(null)
  const [mtlsP12Password, setMtlsP12Password] = useState('')
  const [mtlsP12Legacy, setMtlsP12Legacy] = useState(false)  // PKCS#12 3DES/SHA-1 profile (#331)
  const [mtlsP12Downloading, setMtlsP12Downloading] = useState(false)
  const [mtlsForm, setMtlsForm] = useState({ name: '', validity_days: '365', ca_id: '' })
  const [showHiddenCas, setShowHiddenCas] = useState(false)
  const [mtlsTab, setMtlsTab] = useState('generate')
  const [mtlsImportForm, setMtlsImportForm] = useState({ name: '', pem: '' })
  const [exportCert, setExportCert] = useState(null) // { id, name, hasPrivateKey, keyAlgorithm }
  const [availableCerts, setAvailableCerts] = useState([])
  const [availableCertsLoading, setAvailableCertsLoading] = useState(false)
  const [selectedAssignCert, setSelectedAssignCert] = useState(null)

  const [qrData, setQrData] = useState(null)
  const [confirmCode, setConfirmCode] = useState('')
  // Codes of a change saved without its session: no 401 signs out before they are acknowledged
  const holdingSignOut = useRef(false)
  const releaseSignOut = () => {
    if (!holdingSignOut.current) return false
    holdingSignOut.current = false
    holdSignOut(false)
    return true
  }
  useEffect(() => () => { releaseSignOut() }, [])

  const [webauthnName, setWebauthnName] = useState('')
  const hasEnabledKey = webauthnCredentials.some(c => c.enabled)
  const activeFactors = accountData.two_factor_methods || []
  const [webauthnRegistering, setWebauthnRegistering] = useState(false)

  const [apiKeyForm, setApiKeyForm] = useState(NO_KEY_FORM)

  // Mirror the backend's mTLS issuance gates so the UI never offers an action
  // that can only 403: POST /api/v2/mtls/certificates requires
  // write:user_certificates (a CA signs the result), and directing any CA
  // other than the configured mTLS one additionally requires write:cas.
  // Import and assign stay available to every authenticated user.
  const canGenerateMtls = hasPermission('write:user_certificates')
  const canChooseMtlsCa = hasPermission('write:cas')

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
    } catch (error) { reportSilentFailure('loadCAs', error) }
  }

  const loadAccount = async () => {
    try {
      const response = await accountService.getProfile()
      const data = response.data || response
      setAccountData(data)
      // An edit left pending on this tab comes back, still in edit mode, once
      const kept = keptProfile.current
      keptProfile.current = null
      setFormData(kept || { full_name: data.full_name || '', email: data.email || '' })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
    }
  }

  const loadApiKeys = async () => {
    try {
      const response = await accountService.getApiKeys()
      setApiKeys(response.data || response || [])
    } catch { /* non-critical: API keys tab may not be available */ } finally {
      setApiKeysLoading(false)
    }
  }

  const loadWebAuthnCredentials = async () => {
    try {
      const response = await accountService.getWebAuthnCredentials()
      setWebauthnCredentials(response.data || [])
    } catch { /* non-critical: WebAuthn may not be configured */ }
  }

  const loadMTLSCertificates = async () => {
    try {
      const response = await accountService.getMTLSCertificates()
      setMtlsCertificates(response.data || [])
    } catch { /* non-critical: mTLS may not be enabled */ }
  }

  // Profile handlers
  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      await accountService.updateProfile(formData)
      showSuccess(t('messages.success.update.user'))
      await loadAccount()
      setAnnounce(t('account.profileSaved'))
      requestAnimationFrame(() => saveState.current?.focus())
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.user'))
    } finally {
      setSaving(false)
    }
  }

  // Password handlers
  const handleChangePassword = async ({ current_password, new_password, confirm_password }) => {
    // The form asks twice; nothing used to compare the answers, and the route
    // never sees confirm_password — so a typo silently set the wrong password.
    if (new_password !== confirm_password) {
      showError(t('common.passwordMismatch'))
      return
    }
    try {
      await accountService.changePassword({ current_password, new_password })
      showSuccess(t('messages.success.other.passwordChanged'))
      setShowPasswordModal(false)
    } catch (error) {
      if (error.data?.details?.i18n_key) {
        showError(t(error.data.details.i18n_key, error.data.details.i18n_values || {}))
      } else {
        showError(error.message || t('messages.errors.updateFailed.generic'))
      }
    }
  }

  // A second factor changed: say so of the other sessions unless the server closed none
  const factorChanged = (key, response) => showSuccess(response?.meta?.other_sessions_closed === 0
    ? t(key) : `${t(key)} ${t('account.otherSessionsClosed')}`)

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
        const disabled = await accountService.disable2FA(code)
        factorChanged('messages.success.other.twoFactorDisabled', disabled)
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

  // Security key as the second factor of password logins (needs a registered key)
  const handleToggleKey2FA = async () => {
    try {
      if (accountData.webauthn_2fa) {
        const password = await showPrompt(t('account.enterPasswordToDisableKey2fa'), {
          title: t('account.keyAsSecondFactor'),
          type: 'password',
          confirmText: t('account.turnOffKey2fa')
        })
        if (!password) return
        factorChanged('account.key2faDisabled', await accountService.setWebAuthnSecondFactor(false, password))
      } else {
        factorChanged('account.key2faEnabled', await accountService.setWebAuthnSecondFactor(true))
      }
      await loadAccount()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  const handleConfirm2FA = async () => {
    try {
      const confirmed = await accountService.confirm2FA(confirmCode)
      factorChanged('messages.success.other.twoFactorEnabled', confirmed)
      // The recovery codes are returned once: the dialog shows them until acknowledged
      const codes = (confirmed?.data || confirmed)?.backup_codes
      if (codes?.length) {
        setQrData(prev => ({ ...prev, backup_codes: codes, confirmed: true }))
      } else {
        setShow2FAModal(false)
        setQrData(null)
      }
      setConfirmCode('')
      await loadAccount()
    } catch (error) {
      // Saved but the session not kept: the stored codes come with the error, shown once
      const codes = error?.data?.data?.backup_codes
      if (codes?.length) {
        holdSignOut()
        holdingSignOut.current = true
        setQrData(prev => ({ ...prev, backup_codes: codes, confirmed: true }))
      }
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
      const registered = await accountService.registerWebAuthnKey(webauthnName)
      factorChanged('account.keyRegistered', registered)
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
      const deleted = await accountService.deleteWebAuthnCredential(credentialId)
      factorChanged('account.keyDeleted', deleted)
      await loadWebAuthnCredentials()
    } catch (error) {
      showError(error.message || t('account.deleteKeyFailed'))
    }
  }

  // API Key handlers
  const handleCreateApiKey = async (e) => {
    e?.preventDefault()
    if (!apiKeyForm.name.trim()) {
      showError(t('account.apiKeyNameRequired'))
      return
    }
    try {
      // Empty expiration field => no expiration (backend treats null as
      // "never expires"). Otherwise send the number of days.
      const expiresDays = apiKeyForm.expires_days
        ? parseInt(apiKeyForm.expires_days, 10)
        : null
      const payload = {
        name: apiKeyForm.name.trim(),
        permissions: apiKeyScopePermissions(apiKeyForm.scope, hasPermission),
        expires_days: expiresDays,
      }
      const response = await accountService.createApiKey(payload)
      // apiClient returns the full envelope: { data: {...}, message }
      const created = response.data || response
      setShowApiKeyModal(false)
      setApiKeyForm({ name: '', expires_days: '', scope: 'full' })
      // Show the key in a dedicated modal — it's only available once.
      setNewApiKey(created)
      await loadApiKeys()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.generic'))
    }
  }

  const handleRevokeApiKey = async (keyId) => {
    const confirmed = await showConfirm(t('account.revokeAPIKeyConfirm'), {
      title: t('account.revokeAPIKey'),
      confirmText: t('common.revoke'),
      variant: 'danger'
    })
    if (!confirmed) return

    try {
      await accountService.deleteApiKey(keyId)
      showSuccess(t('messages.success.delete.apiKey'))
      await loadApiKeys()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.generic'))
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
      showSuccess(t('messages.success.delete.apiKeyPermanent'))
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
      // Its certificate is revoked first: the ACME CA that issued it may not have been told
      const localOnly = localOnlyRevocationWarning(await accountService.deleteMTLSCertificate(certId), t)
      if (localOnly) showWarning(localOnly)
      else showSuccess(t('account.certificateDeleted'))
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
        validity_days: validityDays(mtlsForm.validity_days),
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
    setMtlsP12Password('')
    setMtlsP12Legacy(false)
    setMtlsP12Downloading(false)
    setMtlsForm({ name: '', validity_days: '365', ca_id: '' })
    setShowHiddenCas(false)
    setMtlsImportForm({ name: '', pem: '' })
    setMtlsTab('generate')
    setSelectedAssignCert(null)
    setAvailableCerts([])
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

  const loadAvailableCerts = async () => {
    setAvailableCertsLoading(true)
    try {
      const response = await accountService.getAvailableMTLSCertificates()
      setAvailableCerts(response.data || [])
    } catch (error) {
      showError(error.message || t('account.mtlsLoadAvailableFailed'))
    } finally {
      setAvailableCertsLoading(false)
    }
  }

  const handleAssignMTLS = async () => {
    if (!selectedAssignCert) return
    setMtlsCreating(true)
    try {
      await accountService.assignMTLSCertificate(selectedAssignCert.id, selectedAssignCert.name)
      showSuccess(t('account.mtlsCertAssigned'))
      await loadMTLSCertificates()
      handleCloseMTLSModal()
    } catch (error) {
      showError(error.message || t('account.mtlsCertAssignFailed'))
    } finally {
      setMtlsCreating(false)
    }
  }

  const handleDownloadMTLSPkcs12 = async (certId, certName, password, legacy = false) => {
    if (!password || password.length < 8) {
      showError(t('tools.pkcs12PasswordRequired'))
      return
    }
    setMtlsP12Downloading(true)
    try {
      const blob = await accountService.downloadMTLSCertificate(certId, {
        format: 'pkcs12',
        password,
        legacy,
      })
      downloadBlob(blob, `${certName || 'mtls-cert'}.p12`)
      showSuccess(t('userCertificates.exportSuccess'))
    } catch (error) {
      showError(error.message || t('userCertificates.exportError'))
    } finally {
      setMtlsP12Downloading(false)
    }
  }

  const handleExportCert = async (format, options) => {
    if (!exportCert) return
    try {
      const request = (format === 'pkcs12' || format === 'p12')
        ? accountService.downloadMTLSCertificate(exportCert.id, {
            format: 'pkcs12',
            password: options.password,
            includeChain: options.includeChain,
            includeRoot: options.includeRoot,
            legacy: options.legacy,
          })
        : userCertificatesService.export(exportCert.id, format, options)
      await downloadExport(request, { format, name: exportCert.name || 'certificate' })
      showSuccess(t('userCertificates.exportSuccess'))
      setExportCert(null)
    } catch (error) {
      showError(error.message || t('userCertificates.exportError'))
    }
  }

  // The profile's fields against the saved values: a change is « modifié, non enregistré » until saved or undone
  const profileLabels = { full_name: t('account.fullName'), email: t('common.email') }
  const changedFields = Object.keys(profileLabels).filter((k) => formData[k] !== (accountData[k] || ''))
  const profileChanged = !loading && changedFields.length > 0
  useUnloadGuard(profileChanged)
  useEffect(() => {
    if (!loading) keepDraft(PROFILE_DRAFT, profileChanged ? formData : null)
  }, [loading, profileChanged, formData])
  const resetProfile = () => {
    setFormData({ full_name: accountData.full_name || '', email: accountData.email || '' })
    setAnnounce(t('account.profileReset'))
    requestAnimationFrame(() => saveState.current?.focus())
  }
  const saveOnEnter = (e) => {
    if (e.key !== 'Enter' || e.target.tagName !== 'INPUT' || !e.target.closest('#set-sec-profile')) return
    e.preventDefault()
    if (profileChanged && !saving) handleSaveProfile()
  }
  const changeLanguage = (code) => chooseLanguage(i18n, code)
  const closeKeyModal = () => { setShowApiKeyModal(false); setApiKeyForm(NO_KEY_FORM) }
  const close2FA = () => {
    setShow2FAModal(false); setQrData(null); setConfirmCode('')
    // The session is gone: sign in again, back to this page
    if (releaseSignOut()) {
      const { pathname, search, hash } = window.location
      window.location.href = loginUrl(pathname, search, hash)
    }
  }
  const closeWebAuthn = () => { setShowWebAuthnModal(false); setWebauthnName('') }
  const openMtlsWay = (way) => { setMtlsTab(way); if (way === 'assign') loadAvailableCerts() }
  const onOff = (on) => <Pill tone={on ? 'good' : 'muted'} label={on ? t('common.enabled') : t('common.disabled')} />

  const sections = [
    { id: 'profile', label: t('account.profile'), description: t('account.personalDetails'), icon: 'users' },
    { id: 'security', label: t('common.security'), description: t('account.manageAccountSecurity'), icon: 'lock' },
    { id: 'api-keys', label: t('account.apiKeys'), description: t('account.apiKeysIntent'), icon: 'key' },
  ]
  const head = (bar) => <PageHead title={t('common.account')} total={accountData.username || user?.username} intent={t('account.intent')} bar={bar} />

  if (loading) {
    return (
      <Zone testId="account-page">
        {head()}
        <div className="scroll-view" id="view-scroll"><SkeletonPanel label={t('account.loadingAccount')} /></div>
      </Zone>
    )
  }

  const profile = (
    <>
      <SettingsGroup legend={t('common.accountInformation')}>
        <Field id="set-username" label={t('common.username')} full>
          <input id="set-username" value={accountData.username || user?.username || ''} readOnly />
        </Field>
        <Input id="set-full_name" label={t('account.fullName')} value={formData.full_name} placeholder={t('account.enterYourName')}
          onChange={(e) => setFormData((p) => ({ ...p, full_name: e.target.value }))} />
        <Input id="set-email" type="email" label={t('common.email')} value={formData.email}
          onChange={(e) => setFormData((p) => ({ ...p, email: e.target.value }))} />
        <Field id="set-role" label={t('common.role')} full>
          <input id="set-role" value={ROLE_KEYS[accountData.role] ? t(ROLE_KEYS[accountData.role]) : (accountData.role || t('common.user'))} readOnly />
        </Field>
      </SettingsGroup>
      {/* Preferences of this browser and the account's language; the inspector reads the first when the page changes */}
      <SettingsGroup legend={t('account.preferences')}>
        <Select id="set-language" label={t('settings.interfaceLanguage')} value={i18n.language?.split('-')[0] || 'en'} onChange={changeLanguage}
          options={languages.map((l) => ({ value: l.code, label: l.name }))} />
        <ToggleSwitch id="set-close_on_nav" checked={closeOnNav} onChange={(on) => { if (on !== closeOnNav) toggleCloseOnNav() }}
          label={t('account.closeInspectorOnNav')} description={t('account.closeInspectorOnNavHint')} />
      </SettingsGroup>
      <SettingsGroup legend={t('account.accountActivity')} grid={false}>
        <Facts items={[
          accountData.created_at ? [t('account.accountCreated'), formatDate(accountData.created_at)] : { label: t('account.accountCreated'), absent: '—' },
          accountData.last_login ? [t('common.lastLogin'), formatDate(accountData.last_login, true)] : { label: t('common.lastLogin'), absent: '—' },
          [t('account.totalLogins'), accountData.login_count || 0],
          { label: t('common.status'), state: accountData.active ? ['good', t('common.active')] : ['bad', t('common.inactive')] },
        ]} />
      </SettingsGroup>
    </>
  )

  const security = (
    <>
      <SettingsGroup legend={t('common.password')} grid={false}>
        <RecordList>
          <RecordRow title={t('account.changeYourPassword')}
            meta={`${t('account.lastChanged')}${t('work.sep')}${accountData.password_changed_at ? formatDate(accountData.password_changed_at) : t('common.never')}`}
            action={<Btn write id="account-password" onClick={() => setShowPasswordModal(true)}>{t('common.changePassword')}</Btn>} />
        </RecordList>
      </SettingsGroup>
      <SettingsGroup legend={t('common.twoFactorAuth')} grid={false}>
        <RecordList>
          <RecordRow key="totp" title={t('account.authenticatorApp')} badge={onOff(accountData.two_factor_enabled)}
            action={<Btn write tone={accountData.two_factor_enabled ? 'danger' : undefined} onClick={handleToggle2FA}>
              {accountData.two_factor_enabled ? t('common.disable2FA') : t('common.enable2FA')}
            </Btn>} />
          <RecordRow key="key" title={t('account.keyAsSecondFactor')} badge={onOff(accountData.webauthn_2fa)}
            meta={hasEnabledKey ? t('account.keyAsSecondFactorHint') : t('account.keyAsSecondFactorNoKey')}
            action={<Btn write tone={accountData.webauthn_2fa ? 'danger' : undefined} disabled={(!accountData.webauthn_2fa && !hasEnabledKey) || undefined}
              onClick={handleToggleKey2FA}>
              {accountData.webauthn_2fa ? t('account.turnOffKey2fa') : t('account.turnOnKey2fa')}
            </Btn>} />
        </RecordList>
        <p className="group-hint">
          {t('account.activeSecondFactors')}{t('work.sep')}{activeFactors.length
            ? activeFactors.map((m) => (m === 'totp' ? t('account.authenticatorApp') : t('account.securityKey'))).join(', ')
            : t('account.noSecondFactor')}
          {accountData.two_factor_enforced && ` (${t('account.twoFactorEnforced')})`}
        </p>
      </SettingsGroup>
      <SettingsGroup legend={t('account.securityKeys')} hint={t('account.webauthnDescription')} grid={false}>
        <RecordList empty={t('account.noSecurityKeys')}>
          {webauthnCredentials.map((cred) => (
            <RecordRow key={cred.id} title={cred.name || t('account.securityKey')}
              meta={[`${t('account.added')} ${formatDate(cred.created_at)}`, cred.last_used_at && `${t('common.used')} ${formatDate(cred.last_used_at)}`].filter(Boolean).join(' · ')}
              action={<IconBtn icon="close" write label={`${t('common.delete')} ${cred.name || t('account.securityKey')}`} onClick={() => handleDeleteWebAuthn(cred.id)} />} />
          ))}
        </RecordList>
        <div className="settings-actions">
          <Btn write icon="plus" id="account-add-key" onClick={() => setShowWebAuthnModal(true)}>{t('account.addKey')}</Btn>
        </div>
      </SettingsGroup>
      <SettingsGroup legend={<>{t('account.clientCertificates')}{' '}<Pill tone="warn" icon="sparkles" label={t('common.experimental')} /></>}
        hint={t('account.useMTLSCerts')} grid={false}>
        <RecordList empty={t('account.noCertificatesEnrolled')}>
          {mtlsCertificates.map((cert) => {
            const name = cert.name || cert.cert_subject
            // A certificate past its end no longer signs anyone in: it says so whatever its switch
            const expired = cert.valid_until && new Date(cert.valid_until) < new Date()
            return (
              <RecordRow key={cert.id} title={name}
                badge={expired ? <Pill tone="bad" label={t('common.expired')} />
                  : <Pill tone={cert.enabled ? 'good' : 'warn'} label={cert.enabled ? t('common.active') : t('common.disabled')} />}
                meta={[`${t(expired ? 'common.expired' : 'common.expires')} ${formatDate(cert.valid_until)}`, cert.last_used_at && `${t('common.used')} ${formatDate(cert.last_used_at)}`].filter(Boolean).join(' · ')}
                action={<span className="row-actions">
                  <IconBtn icon="download" label={`${t('common.export')} ${name}`}
                    onClick={() => setExportCert({ id: cert.id, name, hasPrivateKey: true, keyAlgorithm: cert.key_algorithm })} />
                  <IconBtn icon="close" write label={`${t('common.delete')} ${name}`} onClick={() => handleDeleteMTLS(cert.id)} />
                </span>} />
            )
          })}
        </RecordList>
        <div className="settings-actions">
          <Btn write icon="plus" id="account-add-mtls" onClick={() => setShowMTLSModal(true)}>{t('account.addCertificate')}</Btn>
        </div>
      </SettingsGroup>
    </>
  )

  const keys = (
    <SettingsGroup legend={t('account.yourAPIKeys')} grid={false}>
      <p className="group-hint">{t('account.apiKeyHint')}</p>
      <ApiKeyList keys={apiKeys} loading={apiKeysLoading} onRevoke={handleRevokeApiKey} onDelete={handleDeleteApiKey}
        onCopy={(prefix) => { copy(prefix); showSuccess(t('common.copied')) }} />
    </SettingsGroup>
  )

  const bodies = { profile, security, 'api-keys': keys }
  const asides = {
    'api-keys': <Btn tone="primary" icon="plus" id="account-new-key" onClick={() => setShowApiKeyModal(true)}>{t('account.createKey')}</Btn>,
  }
  const scopePermissions = apiKeyScopePermissions(apiKeyForm.scope, hasPermission)
  const expiresBad = apiKeyForm.expires_days !== '' && !/^\d+$/.test(String(apiKeyForm.expires_days).trim())
  const unlistedCas = unlistedPickerCas(cas, mtlsForm.ca_id)

  const dialogs = (
    <>
      <FormModal open={showPasswordModal} onOpenChange={setShowPasswordModal} title={t('common.changePassword')} size="sm"
        onSubmit={handleChangePassword} submitLabel={t('common.changePassword')} submitIcon="lock">
        <Input id="pw-current" full label={t('common.currentPassword')} type="password" name="current_password" autoComplete="current-password" required data-autofocus />
        <Input id="pw-new" full label={t('common.newPassword')} type="password" name="new_password" autoComplete="new-password" showStrength required />
        <Input id="pw-confirm" full label={t('common.confirmNewPassword')} type="password" name="confirm_password" autoComplete="new-password" required />
      </FormModal>

      {showApiKeyModal && (
        <AtelierDialog title={t('account.createAPIKey')} size="narrow" onClose={closeKeyModal}>
          <form onSubmit={(e) => { e.preventDefault(); if (!expiresBad) handleCreateApiKey(e) }} noValidate>
            <div className="form-fields">
              <Input id="key-name" full label={t('account.apiKeyName')} value={apiKeyForm.name} placeholder={t('account.keyNameExample')} required data-autofocus
                onChange={(e) => setApiKeyForm((f) => ({ ...f, name: e.target.value }))} />
              <Select id="key-scope" full label={t('account.permissionScope')} value={apiKeyForm.scope} hint={describePermissions(t, scopePermissions)}
                onChange={(val) => setApiKeyForm((f) => ({ ...f, scope: val }))}
                options={[
                  { value: 'full', label: t('account.scopeFull') },
                  { value: 'read', label: t('account.scopeReadOnly') },
                  { value: 'readwrite', label: t('account.scopeReadWrite') },
                  { value: 'certificates', label: t('account.scopeCertificates') },
                ]} />
              <NumberInput id="key-expires" label={t('account.expiresInDays')} value={apiKeyForm.expires_days} placeholder={t('account.expiresInDaysPlaceholder')}
                hint={t('account.expiresInDaysHelp')} error={expiresBad ? t('account.expiresInDaysInvalid') : undefined}
                onChange={(e) => setApiKeyForm((f) => ({ ...f, expires_days: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeKeyModal}>{t('common.cancel')}</button>
              <Btn type="submit" tone="primary" icon="key">{t('account.createKey')}</Btn>
            </div>
          </form>
        </AtelierDialog>
      )}

      {/* The new key, shown once so it can be copied */}
      {newApiKey && (
        <AtelierDialog title={t('account.apiKeyCreatedTitle')} size="narrow" onClose={() => setNewApiKey(null)} returnTo="account-new-key">
          <Notice tone="warn">{t('account.apiKeyCreatedWarning')}</Notice>
          <div className="form-fields">
            <Textarea id="key-value" mono readOnly rows={3} label={t('account.apiKeyValue')} value={newApiKey.key || ''}
              hint={newApiKey.expires_at ? `${t('common.expires')} ${formatDate(newApiKey.expires_at)}` : t('account.apiKeyNoExpiry')} />
          </div>
          <div className="modal-actions">
            <Btn icon="copy" onClick={() => { if (newApiKey.key) { copy(newApiKey.key); showSuccess(t('common.copied')) } }}>{t('common.copy')}</Btn>
            <Btn tone="primary" write={false} icon="check" onClick={() => setNewApiKey(null)}>{t('account.apiKeySavedDone')}</Btn>
          </div>
        </AtelierDialog>
      )}

      {show2FAModal && qrData && (
        <AtelierDialog title={t('account.enableTwoFactor')} size="narrow" onClose={close2FA}>
          <form onSubmit={(e) => { e.preventDefault(); if (!qrData.confirmed && confirmCode.length === 6) handleConfirm2FA() }} noValidate>
            {!qrData.confirmed && (
              <div className="form-fields">
                <div className="field full">
                  <p>{t('account.scanQRCode')}</p>
                  <img src={qrData.qr_code} alt={t('account.qrCodeAlt')} width={192} height={192} />
                </div>
                <Input id="totp-code" label={t('account.enterDigitCode')} placeholder={t('account.codePlaceholder')} inputMode="numeric" maxLength={6}
                  value={confirmCode} data-autofocus onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
              </div>
            )}
            {qrData.backup_codes && (
              <>
                <Notice tone="warn">{t('account.backupCodesHint')}</Notice>
                <div className="form-fields">
                  <Textarea id="totp-backup" mono readOnly rows={Math.ceil(qrData.backup_codes.length / 2) + 1} label={t('account.backupCodes')}
                    value={qrData.backup_codes.join('\n')} />
                </div>
              </>
            )}
            <div className="modal-actions">
              {qrData.confirmed ? (
                <Btn tone="primary" write={false} icon="check" onClick={close2FA}>{t('account.backupCodesSaved')}</Btn>
              ) : (
                <>
                  <button type="button" className="btn" data-action="close-modal" onClick={close2FA}>{t('common.cancel')}</button>
                  <Btn type="submit" tone="primary" icon="lock" disabled={confirmCode.length !== 6 || undefined}>{t('account.verifyAndEnable')}</Btn>
                </>
              )}
            </div>
          </form>
        </AtelierDialog>
      )}

      {showWebAuthnModal && (
        <AtelierDialog title={t('account.registerSecurityKey')} size="narrow" onClose={closeWebAuthn}>
          <form onSubmit={(e) => { e.preventDefault(); if (!webauthnRegistering && webauthnName.trim()) handleRegisterWebAuthn() }} noValidate>
            <p>{t('account.addHardwareKey')}</p>
            <div className="form-fields">
              <Input id="webauthn-name" full label={t('account.keyName')} value={webauthnName} placeholder={t('account.keyNamePlaceholder')} data-autofocus
                onChange={(e) => setWebauthnName(e.target.value)} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeWebAuthn}>{t('common.cancel')}</button>
              <Btn type="submit" tone="primary" icon="key" disabled={webauthnRegistering || !webauthnName.trim() || undefined}>
                {webauthnRegistering ? t('account.waitingForKey') : t('account.registerKey')}
              </Btn>
            </div>
          </form>
        </AtelierDialog>
      )}

      {showMTLSModal && (
        <MtlsCertificateDialog title={t('account.addCertificate')} onClose={handleCloseMTLSModal} busy={mtlsCreating}
          canGenerate={canGenerateMtls} tab={mtlsTab} onTab={openMtlsWay}
          generateForm={mtlsForm} setGenerateForm={setMtlsForm} namePlaceholder={`${user?.username || 'user'} mTLS`} onGenerate={handleCreateMTLS}
          caPicker={canChooseMtlsCa && (
            // Directing a CA other than the configured mTLS one requires write:cas server-side
            <Select id="mtls-ca" full label={t('account.mtlsIssuingCA')} value={mtlsForm.ca_id} placeholder={t('account.mtlsDefaultCA')}
              onChange={(val) => setMtlsForm((prev) => ({ ...prev, ca_id: val }))}
              options={listedForIssuance(pickerCas(cas, mtlsForm.ca_id), showHiddenCas, mtlsForm.ca_id).map((ca) => ({
                value: ca.refid || String(ca.id), label: ca.descr || ca.subject || ca.refid,
              }))}
              hint={(unlistedCas > 0 || hiddenFromIssuance(pickerCas(cas, mtlsForm.ca_id), mtlsForm.ca_id) > 0) && <>
                {unlistedCas > 0 && t('cas.notListedForSigning', { count: unlistedCas })}{' '}
                <HiddenCasToggle count={hiddenFromIssuance(pickerCas(cas, mtlsForm.ca_id), mtlsForm.ca_id)} shown={showHiddenCas} onToggle={() => setShowHiddenCas((v) => !v)} />
              </>} />
          )}
          importForm={mtlsImportForm} setImportForm={setMtlsImportForm} onImport={handleImportMTLS}
          assign={{ loading: availableCertsLoading, certs: availableCerts, selected: selectedAssignCert, onSelect: setSelectedAssignCert }}
          onAssign={handleAssignMTLS}
          result={mtlsResult && (
            <>
              <p className="test-result good" role="status"><span>{t('account.mtlsCertCreated')}</span></p>
              <Notice>{t('account.mtlsDownloadWarning')}</Notice>
              <div className="form-fields">
                <Textarea id="mtls-result-cert" mono readOnly rows={4} label={t('common.certificate')} value={mtlsResult.certificate || ''} />
                <Textarea id="mtls-result-key" mono readOnly rows={4} label={t('account.privateKey')} value={mtlsResult.private_key || ''}
                  hint={t('account.mtlsCertManaged')} />
                <SecretInput id="mtls-p12-password" full label={t('export.password')} value={mtlsP12Password} hint={t('export.formatP12Desc')}
                  onChange={(e) => setMtlsP12Password(e.target.value)} />
                <ToggleSwitch id="mtls-p12-legacy" checked={mtlsP12Legacy} onChange={setMtlsP12Legacy}
                  label={t('export.legacyPkcs12')} description={t('export.legacyPkcs12Desc')} />
              </div>
              <div className="modal-actions">
                <Btn icon="download" onClick={() => {
                  const pem = (mtlsResult.certificate || '') + '\n' + (mtlsResult.private_key || '')
                  downloadBlob(new Blob([pem], { type: 'application/x-pem-file' }), `${mtlsResult.name || 'mtls-cert'}.pem`)
                }}>{t('account.downloadPEM')}</Btn>
                <Btn icon="download" disabled={mtlsP12Downloading || mtlsP12Password.length < 8 || undefined}
                  onClick={() => handleDownloadMTLSPkcs12(mtlsResult.id, mtlsResult.name, mtlsP12Password, mtlsP12Legacy)}>
                  {t('export.formatOptions.pkcs12')}
                </Btn>
                <Btn tone="primary" write={false} onClick={handleCloseMTLSModal}>{t('common.close')}</Btn>
              </div>
            </>
          )} />
      )}

      <ExportDialog
        open={!!exportCert}
        onClose={() => setExportCert(null)}
        entityType="certificate"
        entityName={exportCert?.name || ''}
        hasPrivateKey={exportCert?.hasPrivateKey || false}
        canExportKey={canExportPrivateKey('user_certificate', { hasPermission })}
        keyAlgorithm={exportCert?.keyAlgorithm}
        defaultFormat="pem"
        onExport={handleExportCert}
      />
    </>
  )

  // One bar at a time, so its ids stay unique
  const saveBar = (
    <SettingsSaveBar head={!phone} stateRef={saveState} dirty={profileChanged} pending={changedFields.map((k) => profileLabels[k])}
      saving={saving} onReset={resetProfile} onSave={handleSaveProfile} announce={announce} />
  )

  return (
    <Zone testId="account-page" after={dialogs}>
      {head(phone ? null : saveBar)}
      <SettingsLayout
        toc={<SettingsToc label={t('account.tocLabel')} sections={sections} flags={profileChanged ? { profile: 'modified' } : {}} current={activeTab}
          hrefFor={(id) => (id === 'profile' ? '/account' : `/account?tab=${id}`)} onJump={setActiveTab} />}
        onKeyDown={saveOnEnter}
      >
        <SettingsJump sections={sections} current={activeTab} onJump={setActiveTab} />
        {sections.map((s) => (
          <SettingsFrame key={s.id} id={s.id} label={s.label} desc={s.description} aside={asides[s.id]}>{bodies[s.id]}</SettingsFrame>
        ))}
        {phone && saveBar}
      </SettingsLayout>
    </Zone>
  )
}
