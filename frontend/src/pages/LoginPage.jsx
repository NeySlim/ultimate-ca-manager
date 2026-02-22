/**
 * Multi-Method Login Page
 * 
 * Architecture:
 * - AuthContext.checkSession() runs on mount (including /login)
 * - If mTLS middleware auto-logged in → AuthContext sets isAuthenticated → App redirects to /
 * - If not auto-logged → LoginPage renders with state machine:
 *   idle → detecting → username → auth (webauthn_prompt | password_form) → 2fa → done
 * 
 * Auto-login priority: mTLS (0 interaction) → WebAuthn (1 touch) → Password (manual)
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { ShieldCheck, Fingerprint, Key, User, ArrowRight, ArrowLeft, GithubLogo, Palette, Globe, SignIn, Lock } from '@phosphor-icons/react'
import { Card, Button, Input, Logo, LoadingSpinner } from '../components'
import { languages } from '../i18n'
import { useAuth, useNotification } from '../contexts'
import { useTheme } from '../contexts/ThemeContext'
import { authMethodsService } from '../services/auth-methods.service'
import { cn } from '../lib/utils'

const STORAGE_KEY = 'ucm_last_username'
const STORAGE_AUTH_METHOD_KEY = 'ucm_last_auth_method'

const getSSOIcon = (provider) => {
  const name = provider.name?.toLowerCase() || ''
  const type = provider.provider_type
  if (name.includes('google')) return '🔵'
  if (name.includes('microsoft') || name.includes('azure') || name.includes('entra')) return '🟦'
  if (name.includes('github')) return '⚫'
  if (name.includes('gitlab')) return '🟠'
  if (name.includes('okta')) return '🔷'
  if (name.includes('keycloak')) return '🔐'
  if (name.includes('auth0')) return '🔴'
  if (type === 'ldap') return '📁'
  if (type === 'saml') return '🔒'
  if (type === 'oauth2') return '🔑'
  return '🔐'
}

export default function LoginPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { login, sessionChecked } = useAuth()
  const { showError, showSuccess, showInfo } = useNotification()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const passwordRef = useRef(null)

  // State machine: 'init' | 'username' | 'auth' | '2fa' | 'ldap'
  const [step, setStep] = useState('init')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [authMethod, setAuthMethod] = useState(null)
  const [userMethods, setUserMethods] = useState(null)
  const [statusMessage, setStatusMessage] = useState('')
  const [hasSavedUsername, setHasSavedUsername] = useState(false)
  const [emailConfigured, setEmailConfigured] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [langMenuOpen, setLangMenuOpen] = useState(false)
  const [globalMethods, setGlobalMethods] = useState(null)
  
  // SSO state
  const [ssoProviders, setSsoProviders] = useState([])
  const [selectedLdapProvider, setSelectedLdapProvider] = useState(null)

  const currentLang = languages.find(l => l.code === (i18n.language?.split('-')[0] || 'en')) || languages[0]

  // Save helpers
  const saveUsername = (name) => {
    if (name) {
      try { localStorage.setItem(STORAGE_KEY, name) } catch {}
    }
  }
  const saveAuthMethod = (method, providerId = null) => {
    try { localStorage.setItem(STORAGE_AUTH_METHOD_KEY, JSON.stringify({ method, providerId })) } catch {}
  }

  // ═══════════════════════════════════════════════════
  // INIT: After AuthContext finishes session check,
  // if we're still here (not auto-logged in), detect methods
  // ═══════════════════════════════════════════════════
  useEffect(() => {
    if (!sessionChecked) return
    
    // Load saved username
    let lastUsername = ''
    try { lastUsername = localStorage.getItem(STORAGE_KEY) || '' } catch {}
    if (lastUsername) {
      setUsername(lastUsername)
      setHasSavedUsername(true)
    }

    // Check email config
    fetch('/api/v2/auth/email-configured')
      .then(res => res.ok ? res.json() : null)
      .then(data => setEmailConfigured(data?.configured || false))
      .catch(() => {})

    // Load SSO providers + detect global auth methods in parallel
    Promise.all([
      fetch('/api/v2/sso/available').then(r => r.ok ? r.json() : null).catch(() => null),
      authMethodsService.detectMethods(null)
    ]).then(([ssoData, methods]) => {
      // SSO providers
      const providers = ssoData?.data && Array.isArray(ssoData.data) ? ssoData.data : []
      setSsoProviders(providers)
      
      // Global methods (no username - detects cert presence)
      setGlobalMethods(methods)

      // Restore saved LDAP provider
      if (lastUsername && providers.length > 0) {
        try {
          const saved = JSON.parse(localStorage.getItem(STORAGE_AUTH_METHOD_KEY) || '{}')
          if (saved.method === 'ldap' && saved.providerId) {
            const provider = providers.find(p => p.id === saved.providerId)
            if (provider) {
              setSelectedLdapProvider(provider)
              setStep('ldap')
              return
            }
          }
        } catch {}
      }

      // If mTLS cert present but not enrolled, show info
      if (methods?.mtls && methods.mtls_status === 'present_not_enrolled') {
        showInfo(t('auth.certNotEnrolled'))
      }

      setStep('username')
    }).catch(() => {
      setStep('username')
    })
  }, [sessionChecked]) // eslint-disable-line react-hooks/exhaustive-deps

  // SSO callback handling
  useEffect(() => {
    const ssoComplete = window.location.pathname.includes('sso-complete')
    if (ssoComplete) {
      setLoading(true)
      setStatusMessage(t('auth.signingIn'))
      fetch('/api/v2/auth/verify', { credentials: 'include' })
        .then(res => res.ok ? res.json() : Promise.reject('Session not established'))
        .then(async (data) => {
          const verifyData = data.data || data
          await login(verifyData?.user?.username || 'sso_user', null, verifyData)
          showSuccess(t('auth.welcomeBackUser', { username: verifyData?.user?.username || 'User' }))
          navigate('/dashboard')
        })
        .catch(() => {
          showError(t('auth.ssoError'))
          setLoading(false)
          setStatusMessage('')
          setStep('username')
        })
      return
    }

    const error = searchParams.get('error')
    if (error) {
      const errorMessages = {
        'provider_disabled': t('auth.ssoProviderDisabled'),
        'invalid_state': t('auth.ssoInvalidState'),
        'token_exchange_failed': t('auth.ssoTokenFailed'),
        'userinfo_failed': t('auth.ssoUserinfoFailed'),
        'no_username': t('auth.ssoNoUsername'),
        'user_creation_failed': t('auth.ssoUserCreationFailed'),
        'auto_create_disabled': t('auth.ssoAutoCreateDisabled'),
        'callback_error': t('auth.ssoCallbackError'),
      }
      showError(errorMessages[error] || t('auth.ssoError'))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Focus password field
  useEffect(() => {
    if (authMethod === 'password' && step === 'auth' && passwordRef.current) {
      passwordRef.current.focus()
    }
  }, [authMethod, step])

  // ═══════════════════════════════════════════════════
  // AUTH METHOD HANDLERS (standalone, no cascading)
  // ═══════════════════════════════════════════════════

  const attemptWebAuthn = useCallback(async () => {
    setAuthMethod('webauthn')
    setStatusMessage(t('auth.touchSecurityKey'))
    setLoading(true)
    try {
      const userData = await authMethodsService.authenticateWebAuthn(username)
      saveUsername(username)
      saveAuthMethod('webauthn')
      await login(username, null, userData)
      showSuccess(t('auth.welcomeBackUser', { username }))
      navigate('/dashboard')
    } catch (error) {
      // Cancelled or failed → fall to password
      setAuthMethod('password')
      setStatusMessage('')
      setLoading(false)
      if (error.message?.includes('cancelled') || error.message?.includes('abort')) {
        showInfo(t('auth.securityKeyCancelled'))
      }
    }
  }, [username, login, navigate, showSuccess, showInfo, t]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleContinue = async (e) => {
    e?.preventDefault()
    if (!username.trim()) {
      showError(t('auth.usernameRequired'))
      return
    }

    setLoading(true)
    setStatusMessage(t('auth.checkingMethods'))

    try {
      saveUsername(username)
      const methods = await authMethodsService.detectMethods(username)
      setUserMethods(methods)
      setStep('auth')

      // Auto-attempt WebAuthn if user has registered keys
      if (methods.webauthn && methods.webauthn_credentials > 0 && authMethodsService.isWebAuthnSupported()) {
        await attemptWebAuthn()
        return
      }

      // Fallback to password
      setAuthMethod('password')
      setStatusMessage('')
    } catch {
      setStep('auth')
      setAuthMethod('password')
      setUserMethods({ password: true })
      setStatusMessage('')
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordLogin = async (e) => {
    e.preventDefault()
    if (!password) {
      showError(t('auth.passwordRequired'))
      return
    }

    setLoading(true)
    setStatusMessage(t('auth.signingIn'))

    try {
      const userData = await authMethodsService.loginPassword(username, password)
      if (userData.requires_2fa) {
        setStep('2fa')
        setTotpCode('')
        setLoading(false)
        setStatusMessage('')
        return
      }
      saveUsername(username)
      saveAuthMethod('password')
      await login(username, password, userData)
      showSuccess(t('auth.welcomeBackUser', { username }))
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || t('auth.invalidCredentials'))
      setPassword('')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  const handle2FAVerify = async (e) => {
    e.preventDefault()
    if (!totpCode || totpCode.length < 6) {
      showError(t('auth.totpCodeRequired'))
      return
    }

    setLoading(true)
    try {
      const userData = await authMethodsService.login2FA(totpCode)
      saveUsername(username)
      saveAuthMethod('password')
      await login(username, password, userData)
      showSuccess(t('auth.welcomeBackUser', { username }))
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || t('auth.invalidTotpCode'))
      setTotpCode('')
    } finally {
      setLoading(false)
    }
  }

  const handleSSOLogin = (provider) => {
    if (provider.provider_type === 'ldap') {
      setSelectedLdapProvider(provider)
      setStep('ldap')
    } else {
      window.location.href = `/api/v2/sso/login/${provider.provider_type}`
    }
  }

  const handleLDAPLogin = async (e) => {
    e.preventDefault()
    if (!username || !password) {
      showError(t('auth.enterCredentials'))
      return
    }

    setLoading(true)
    setStatusMessage(t('auth.authenticating'))

    try {
      const response = await fetch('/api/v2/sso/ldap/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, provider_id: selectedLdapProvider?.id })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.message || t('auth.invalidCredentials'))

      saveUsername(username)
      saveAuthMethod('ldap', selectedLdapProvider?.id)
      await login(username, null, data.data)
      showSuccess(t('auth.welcomeBackUser', { username }))
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || t('auth.ldapFailed'))
      setPassword('')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  const handleBack = () => {
    setStep('username')
    setAuthMethod(null)
    setPassword('')
    setStatusMessage('')
    setSelectedLdapProvider(null)
    try { localStorage.removeItem(STORAGE_AUTH_METHOD_KEY) } catch {}
  }

  const handleChangeUser = () => {
    setUsername('')
    setHasSavedUsername(false)
    try {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem(STORAGE_AUTH_METHOD_KEY)
    } catch {}
    handleBack()
  }

  // ═══════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════

  // Show nothing while AuthContext is checking session (App.jsx shows PageLoader)
  if (!sessionChecked || step === 'init') {
    return null
  }

  return (
    <div className="min-h-dvh flex items-start sm:items-center justify-center bg-gradient-to-br from-bg-primary via-bg-secondary to-bg-tertiary p-2 sm:p-4 pt-2 sm:pt-4 overflow-hidden">
      <Card className="w-full max-w-md p-4 sm:p-8 space-y-3 sm:space-y-5">
        {/* Logo */}
        <div className="flex justify-center mb-1 sm:mb-2">
          <Logo variant="horizontal" size="lg" className="scale-90 sm:scale-100" />
        </div>

        {/* Title */}
        <div className="text-center">
          <h1 className="text-xl sm:text-2xl font-bold text-text-primary mb-1 sm:mb-2">
            {step === 'username' 
              ? (username ? t('auth.welcomeBack') : t('auth.login'))
              : t('auth.welcomeBack')
            }
          </h1>
          <p className="text-sm text-text-secondary">
            {step === 'username' 
              ? (globalMethods?.mtls && globalMethods.mtls_status === 'present_not_enrolled'
                ? t('auth.certNotEnrolled')
                : username ? t('auth.clickToContinue') : t('auth.signInToContinue'))
              : statusMessage || (authMethod === 'password' ? t('auth.enterPasswordToContinue') : t('auth.chooseAuthMethod'))
            }
          </p>
        </div>

        {/* Step 1: Username */}
        {step === 'username' && (
          <div className="space-y-3 sm:space-y-4">
            {/* SSO Providers — shown first */}
            {ssoProviders.length > 0 && (
              <div className="space-y-3">
                <div className="grid gap-2">
                  {ssoProviders.map((provider) => (
                    <button
                      key={provider.id}
                      onClick={() => handleSSOLogin(provider)}
                      disabled={loading}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-border bg-bg-secondary hover:bg-bg-tertiary hover:border-accent-op50 transition-all text-text-primary font-medium"
                    >
                      <span className="text-lg">{provider.icon || getSSOIcon(provider)}</span>
                      <span>{provider.display_name || provider.name}</span>
                    </button>
                  ))}
                </div>
                
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-xs text-text-tertiary uppercase tracking-wider">{t('auth.orSignInLocally')}</span>
                  <div className="flex-1 h-px bg-border" />
                </div>
              </div>
            )}

            {/* If username saved from localStorage: show identity card */}
            {hasSavedUsername && username ? (
              <>
                {/* Clickable user identity card */}
                <button
                  onClick={handleContinue}
                  disabled={loading}
                  className="w-full text-left relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-3 sm:p-4 hover:border-accent-op50 hover:shadow-lg transition-all group"
                >
                  <div className="absolute top-0 right-0 w-20 h-20 sm:w-24 sm:h-24 bg-accent-op5 rounded-full -translate-y-1/2 translate-x-1/2 group-hover:bg-accent-op10 transition-colors" />
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-br from-accent to-accent-op70 flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
                      <User size={20} className="text-white sm:hidden" weight="bold" />
                      <User size={24} className="text-white hidden sm:block" weight="bold" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-text-secondary uppercase tracking-wider font-medium">{t('auth.continueAs')}</p>
                      <p className="text-base sm:text-lg font-semibold text-text-primary truncate">{username}</p>
                    </div>
                    <div className="text-accent group-hover:translate-x-1 transition-transform">
                      <ArrowRight size={24} weight="bold" />
                    </div>
                  </div>
                  {loading && (
                    <div className="absolute inset-0 bg-primary-op50 flex items-center justify-center rounded-xl">
                      <LoadingSpinner size="md" />
                    </div>
                  )}
                </button>

                {/* Option to use different account */}
                <button
                  onClick={() => {
                    setUsername('')
                    setHasSavedUsername(false)
                    localStorage.removeItem(STORAGE_KEY)
                    localStorage.removeItem(STORAGE_AUTH_METHOD_KEY)
                  }}
                  className="w-full text-sm text-text-secondary hover:text-accent transition-colors py-2"
                  disabled={loading}
                >
                  {t('auth.useDifferentAccount')}
                </button>
              </>
            ) : (
              /* No saved username: show input field */
              <form onSubmit={handleContinue} className="space-y-4">
                <Input
                  label={t('common.username')}
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={t('auth.enterUsername')}
                  disabled={loading}
                  autoComplete="username"
                  autoFocus
                  icon={<User size={18} />}
                />

                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading || !username.trim()}
                >
                  {loading ? (
                    <>
                      <LoadingSpinner size="sm" />
                      <span>{t('auth.checking')}</span>
                    </>
                  ) : (
                    <>
                      <span>{t('auth.continue')}</span>
                      <ArrowRight size={18} weight="bold" />
                    </>
                  )}
                </Button>
              </form>
            )}
          </div>
        )}

        {/* Step 2: Authentication */}
        {step === 'auth' && (
          <div className="space-y-3 sm:space-y-5">
            {/* User identity card - modern design */}
            <div className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-3 sm:p-4">
              <div className="absolute top-0 right-0 w-20 h-20 sm:w-24 sm:h-24 bg-accent-op5 rounded-full -translate-y-1/2 translate-x-1/2" />
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-br from-accent to-accent-op70 flex items-center justify-center shadow-lg">
                  <User size={20} className="text-white sm:hidden" weight="bold" />
                  <User size={24} className="text-white hidden sm:block" weight="bold" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-medium">{t('auth.signingInAs')}</p>
                  <p className="text-base sm:text-lg font-semibold text-text-primary truncate">{username}</p>
                </div>
                <button
                  onClick={handleChangeUser}
                  className="px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-accent hover:bg-accent-op10 rounded-lg transition-all"
                  disabled={loading}
                >
                  {t('common.change')}
                </button>
              </div>
            </div>

            {/* Loading state for auto-auth */}
            {loading && (authMethod === 'mtls' || authMethod === 'webauthn') && (
              <div className="flex flex-col items-center gap-2 py-2 sm:gap-4 sm:py-6">
                <div className="relative">
                  <LoadingSpinner size="lg" />
                  {authMethod === 'mtls' && <ShieldCheck size={24} className="absolute inset-0 m-auto text-accent" />}
                  {authMethod === 'webauthn' && <Fingerprint size={24} className="absolute inset-0 m-auto text-accent" />}
                </div>
                <p className="text-sm text-text-secondary animate-pulse">
                  {statusMessage}
                </p>
              </div>
            )}

            {/* WebAuthn option (when not loading) */}
            {authMethod === 'webauthn' && !loading && (
              <div className="space-y-2 sm:space-y-3">
                <Button
                  onClick={() => attemptWebAuthn()}
                  className="w-full"
                  variant="secondary"
                  disabled={loading}
                >
                  <Fingerprint size={20} weight="fill" />
                  <span>{t('auth.trySecurityKeyAgain')}</span>
                </Button>
                
                <button
                  onClick={() => setAuthMethod('password')}
                  className="w-full text-sm text-text-secondary hover:text-accent transition-colors py-1.5 sm:py-2"
                >
                  {t('auth.usePasswordInstead')}
                </button>
              </div>
            )}

            {/* Password form */}
            {authMethod === 'password' && (
              <form onSubmit={handlePasswordLogin} className="space-y-3 sm:space-y-4">
                {/* Hidden username field for accessibility */}
                <input
                  type="text"
                  name="username"
                  autoComplete="username"
                  value={username}
                  readOnly
                  className="sr-only"
                  tabIndex={-1}
                />
                
                <Input
                  ref={passwordRef}
                  label={t('common.password')}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.enterPassword')}
                  disabled={loading}
                  autoComplete="current-password"
                  autoFocus
                  icon={<Key size={18} />}
                />

                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading || !password}
                >
                  {loading ? (
                    <>
                      <LoadingSpinner size="sm" />
                      <span>{t('auth.signingIn')}</span>
                    </>
                  ) : (
                    <>
                      <Key size={18} weight="fill" />
                      <span>{t('auth.login')}</span>
                    </>
                  )}
                </Button>

                {/* Forgot Password Link - only if email configured */}
                {emailConfigured && (
                  <div className="text-center">
                    <Link
                      to="/forgot-password"
                      className="text-sm text-accent hover:text-accent-op80 hover:underline transition-colors"
                    >
                      {t('auth.forgotPassword')}
                    </Link>
                  </div>
                )}

                {/* Show WebAuthn option if available */}
                {userMethods?.webauthn && userMethods.webauthn_credentials > 0 && authMethodsService.isWebAuthnSupported() && (
                  <button
                    onClick={() => attemptWebAuthn()}
                    className="w-full text-sm text-text-secondary hover:text-accent transition-colors py-2 flex items-center justify-center gap-2"
                    type="button"
                    disabled={loading}
                  >
                    <Fingerprint size={16} />
                    <span>{t('auth.useSecurityKey')}</span>
                  </button>
                )}
              </form>
            )}

            {/* Back button */}
            <button
              onClick={handleBack}
              className="w-full text-sm text-text-secondary hover:text-text-primary transition-colors py-1.5 sm:py-2 flex items-center justify-center gap-1"
              disabled={loading}
            >
              <ArrowLeft size={14} />
              <span>{t('common.back')}</span>
            </button>
          </div>
        )}

        {/* Auth methods available indicator */}
        {step === 'auth' && userMethods && (
          <div className="flex justify-center gap-1.5 sm:gap-2 pt-1 sm:pt-2">
            {userMethods.mtls && (
              <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'mtls' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
                <ShieldCheck size={12} weight="fill" />
                <span>mTLS</span>
              </div>
            )}
            {userMethods.webauthn && userMethods.webauthn_credentials > 0 && (
              <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'webauthn' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
                <Fingerprint size={12} weight="fill" />
                <span>{t('common.key')}</span>
              </div>
            )}
            <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'password' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
              <Key size={12} weight="fill" />
              <span>{t('common.password')}</span>
            </div>
          </div>
        )}

        {/* Step 2b: 2FA TOTP Verification */}
        {step === '2fa' && (
          <div className="space-y-3 sm:space-y-5">
            <div className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-3 sm:p-4">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center shadow-lg">
                  <Lock size={20} weight="fill" className="text-white" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-primary text-sm sm:text-base">{t('auth.twoFactorTitle')}</h3>
                  <p className="text-xs text-text-secondary">{t('auth.twoFactorDescription')}</p>
                </div>
              </div>
            </div>

            <form onSubmit={handle2FAVerify} className="space-y-3 sm:space-y-4">
              <Input
                label={t('auth.totpCode')}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000"
                disabled={loading}
                autoComplete="one-time-code"
                autoFocus
                icon={<ShieldCheck size={18} />}
              />

              <Button
                type="submit"
                className="w-full"
                disabled={loading || totpCode.length < 6}
              >
                {loading ? (
                  <>
                    <LoadingSpinner size="sm" />
                    <span>{t('auth.verifying')}</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck size={18} weight="fill" />
                    <span>{t('auth.verify')}</span>
                  </>
                )}
              </Button>
            </form>

            <button
              onClick={() => { setStep('auth'); setTotpCode(''); setAuthMethod('password') }}
              className="flex items-center justify-center gap-2 text-sm text-text-secondary hover:text-text-primary cursor-pointer transition-colors py-2 w-full"
            >
              <ArrowLeft size={16} />
              <span>{t('common.back')}</span>
            </button>
          </div>
        )}

        {/* Step 3: LDAP Login */}
        {step === 'ldap' && selectedLdapProvider && (
          <div className="space-y-3 sm:space-y-5">
            {/* Provider header */}
            <div className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-3 sm:p-4">
              <div className="absolute top-0 right-0 w-20 h-20 sm:w-24 sm:h-24 bg-accent-op5 rounded-full -translate-y-1/2 translate-x-1/2" />
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-br from-accent to-accent-op70 flex items-center justify-center shadow-lg text-xl">
                  {selectedLdapProvider.icon || getSSOIcon(selectedLdapProvider)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-medium">{t('auth.signingInWith')}</p>
                  <p className="text-base sm:text-lg font-semibold text-text-primary truncate">
                    {selectedLdapProvider.display_name || selectedLdapProvider.name}
                  </p>
                </div>
              </div>
            </div>

            {/* LDAP Login form */}
            <form onSubmit={handleLDAPLogin} className="space-y-3 sm:space-y-4">
              <Input
                label={t('common.username')}
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={t('auth.ldapUsername')}
                disabled={loading}
                autoComplete="username"
                autoFocus
                icon={<User size={18} />}
              />
              
              <Input
                label={t('common.password')}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('auth.enterPassword')}
                disabled={loading}
                autoComplete="current-password"
                icon={<Key size={18} />}
              />

              <Button
                type="submit"
                className="w-full"
                disabled={loading || !username || !password}
              >
                {loading ? (
                  <>
                    <LoadingSpinner size="sm" />
                    <span>{statusMessage || t('auth.signingIn')}</span>
                  </>
                ) : (
                  <>
                    <SignIn size={18} weight="bold" />
                    <span>{t('auth.login')}</span>
                  </>
                )}
              </Button>
            </form>

            {/* Back button */}
            <button
              onClick={handleBack}
              className="w-full text-sm text-text-secondary hover:text-text-primary transition-colors py-1.5 sm:py-2 flex items-center justify-center gap-1"
              disabled={loading}
            >
              <ArrowLeft size={14} />
              <span>{t('common.back')}</span>
            </button>
          </div>
        )}

        {/* Footer with actions */}
        <div className="pt-3 sm:pt-4 border-t border-border space-y-2 sm:space-y-3">
          {/* Action buttons row */}
          <div className="flex items-center justify-center gap-2 relative">
            {/* Language Selector - Flag only */}
            <div className="relative">
              <button
                onClick={() => { setLangMenuOpen(!langMenuOpen); setThemeMenuOpen(false) }}
                className="flex items-center justify-center w-9 h-9 rounded-md bg-bg-tertiary hover:bg-bg-secondary border border-border text-text-secondary hover:text-text-primary transition-colors"
                title={t('settings.language')}
              >
                <span className="text-lg">{currentLang.flag}</span>
              </button>
              
              {/* Language dropdown */}
              {langMenuOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setLangMenuOpen(false)} />
                  <div className="absolute bottom-full mb-2 left-0 z-50 bg-bg-secondary border border-border rounded-lg shadow-xl p-1.5 min-w-[140px]">
                    {languages.map((lang) => (
                      <button
                        key={lang.code}
                        onClick={() => { 
                          i18n.changeLanguage(lang.code)
                          try { localStorage.setItem('i18nextLng', lang.code) } catch {}
                          setLangMenuOpen(false)
                        }}
                        className={cn(
                          "w-full px-2 py-1.5 text-left text-sm rounded flex items-center gap-2",
                          "hover:bg-bg-tertiary transition-colors",
                          currentLang.code === lang.code && "text-accent-primary bg-accent-primary-op10"
                        )}
                      >
                        <span>{lang.flag}</span>
                        {lang.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
            
            {/* Theme Selector */}
            <div className="relative">
              <button
                onClick={() => { setThemeMenuOpen(!themeMenuOpen); setLangMenuOpen(false) }}
                className="flex items-center justify-center w-9 h-9 rounded-md bg-bg-tertiary hover:bg-bg-secondary border border-border text-text-secondary hover:text-text-primary transition-colors"
                title={t('settings.tabs.appearance')}
              >
                <Palette size={18} />
              </button>
              
              {/* Theme dropdown */}
              {themeMenuOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setThemeMenuOpen(false)} />
                  <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 z-50 bg-bg-secondary border border-border rounded-lg shadow-xl p-1.5 min-w-[160px]">
                    {/* Color Themes */}
                    <div className="px-2 py-0.5 text-xs text-text-tertiary uppercase tracking-wider">{t('settings.color')}</div>
                    {themes.map((theme) => (
                      <button
                        key={theme.id}
                        onClick={() => { setThemeFamily(theme.id); setThemeMenuOpen(false) }}
                        className={cn(
                          "w-full px-2 py-1.5 text-left text-sm rounded flex items-center gap-2",
                          "hover:bg-bg-tertiary transition-colors",
                          themeFamily === theme.id && "text-accent-primary bg-accent-primary-op10"
                        )}
                      >
                        <div 
                          className="w-3 h-3 rounded-full border border-border"
                          style={{ background: theme.accent }}
                        />
                        {theme.name}
                      </button>
                    ))}
                    
                    {/* Separator */}
                    <div className="h-px bg-border my-1.5" />
                    
                    {/* Mode */}
                    <div className="px-2 py-0.5 text-xs text-text-tertiary uppercase tracking-wider">{t('settings.tabs.appearance')}</div>
                    {[
                      { id: 'system', labelKey: 'settings.followSystem' },
                      { id: 'dark', labelKey: 'settings.dark' },
                      { id: 'light', labelKey: 'settings.light' }
                    ].map(opt => (
                      <button
                        key={opt.id}
                        onClick={() => { setMode(opt.id); setThemeMenuOpen(false) }}
                        className={cn(
                          "w-full px-2 py-1.5 text-left text-sm rounded",
                          "hover:bg-bg-tertiary transition-colors",
                          mode === opt.id && "text-accent-primary bg-accent-primary-op10"
                        )}
                      >
                        {t(opt.labelKey)}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
            
            {/* GitHub Link */}
            <a
              href="https://github.com/NeySlim/ultimate-ca-manager"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center w-9 h-9 rounded-md bg-bg-tertiary hover:bg-bg-secondary border border-border text-text-secondary hover:text-text-primary transition-colors"
              title="GitHub"
            >
              <GithubLogo size={18} />
            </a>
          </div>
          
          {/* Version */}
          <p className="text-center text-xs text-text-tertiary">
            Ultimate Certificate Manager v{__APP_VERSION__ || '2'}
          </p>
        </div>
      </Card>
    </div>
  )
}
