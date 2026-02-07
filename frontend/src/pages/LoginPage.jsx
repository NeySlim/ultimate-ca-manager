/**
 * Multi-Method Login Page
 * Flow: Username → mTLS/WebAuthn → Password (fallback)
 * Remembers last username in localStorage
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, Link } from 'react-router-dom'
import { ShieldCheck, Fingerprint, Key, User, ArrowRight, ArrowLeft, GithubLogo, Palette, Globe } from '@phosphor-icons/react'
import { Card, Button, Input, Logo, LoadingSpinner } from '../components'
import { languages } from '../i18n'
import { useAuth, useNotification } from '../contexts'
import { useTheme } from '../contexts/ThemeContext'
import { authMethodsService } from '../services/authMethods.service'
import { cn } from '../lib/utils'

const STORAGE_KEY = 'ucm_last_username'

export default function LoginPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { login } = useAuth()
  const { showError, showSuccess, showInfo } = useNotification()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const passwordRef = useRef(null)
  
  // Login flow step: 'username' | 'auth'
  const [step, setStep] = useState('username')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [authMethod, setAuthMethod] = useState(null) // 'mtls' | 'webauthn' | 'password'
  const [userMethods, setUserMethods] = useState(null) // Methods available for this user
  const [statusMessage, setStatusMessage] = useState('')
  const [hasSavedUsername, setHasSavedUsername] = useState(false) // Track if we loaded from storage
  const [emailConfigured, setEmailConfigured] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [langMenuOpen, setLangMenuOpen] = useState(false)

  // Get current language
  const currentLang = languages.find(l => l.code === (i18n.language?.split('-')[0] || 'en')) || languages[0]

  // Load last username on mount + check email config
  useEffect(() => {
    const lastUsername = localStorage.getItem(STORAGE_KEY)
    if (lastUsername) {
      setUsername(lastUsername)
      setHasSavedUsername(true)
    }
    
    // Check if email is configured for "Forgot Password" link
    fetch('/api/v2/auth/email-configured')
      .then(res => res.json())
      .then(data => setEmailConfigured(data.configured || false))
      .catch(() => setEmailConfigured(false))
  }, [])

  // Focus password field when switching to password auth
  useEffect(() => {
    if (authMethod === 'password' && step === 'auth' && passwordRef.current) {
      passwordRef.current.focus()
    }
  }, [authMethod, step])

  // Save username to localStorage
  const saveUsername = (name) => {
    if (name) {
      localStorage.setItem(STORAGE_KEY, name)
    }
  }

  // Step 1: Continue with username → detect methods and try auto-login
  const handleContinue = async (e) => {
    e?.preventDefault()
    
    if (!username.trim()) {
      showError('Please enter your username')
      return
    }

    setLoading(true)
    setStatusMessage('Checking authentication methods...')
    
    try {
      // Save username for next time
      saveUsername(username)
      
      // Check available methods for this user
      const methods = await authMethodsService.detectMethods(username)
      setUserMethods(methods)
      
      // Move to auth step
      setStep('auth')
      
      // Try cascade: mTLS → WebAuthn → Password
      
      // 1. Try mTLS if available
      if (methods.mtls && methods.mtls_status === 'enrolled') {
        setAuthMethod('mtls')
        setStatusMessage('Verifying client certificate...')
        await tryMTLSLogin()
        return
      }
      
      // 2. Try WebAuthn if user has registered keys
      if (methods.webauthn && methods.webauthn_credentials > 0 && authMethodsService.isWebAuthnSupported()) {
        setAuthMethod('webauthn')
        setStatusMessage(t('auth.waitingForSecurityKey'))
        await tryWebAuthnLogin()
        return
      }
      
      // 3. Fallback to password
      setAuthMethod('password')
      setStatusMessage('')
      
    } catch (error) {
      console.error('Auth detection failed:', error)
      // On error, go directly to password
      setStep('auth')
      setAuthMethod('password')
      setUserMethods({ password: true })
      setStatusMessage('')
    } finally {
      setLoading(false)
    }
  }

  // Try mTLS auto-login
  const tryMTLSLogin = async () => {
    try {
      const userData = await authMethodsService.loginMTLS()
      saveUsername(userData.user.username)
      await login(userData.user.username, null, userData)
      showSuccess(`Welcome back, ${userData.user.username}!`)
      navigate('/dashboard')
    } catch (error) {
      // Try WebAuthn next
      if (userMethods?.webauthn && userMethods.webauthn_credentials > 0 && authMethodsService.isWebAuthnSupported()) {
        setAuthMethod('webauthn')
        setStatusMessage(t('auth.waitingForSecurityKey'))
        await tryWebAuthnLogin()
      } else {
        // Fallback to password
        setAuthMethod('password')
        setStatusMessage('')
        setLoading(false)
      }
    }
  }

  // Try WebAuthn login
  const tryWebAuthnLogin = async () => {
    try {
      setStatusMessage(t('auth.touchSecurityKey'))
      const userData = await authMethodsService.authenticateWebAuthn(username)
      saveUsername(username)
      await login(username, null, userData)
      showSuccess(t('auth.welcomeBackUser', { username }))
      navigate('/dashboard')
    } catch (error) {
      // User cancelled or error → show password form
      setAuthMethod('password')
      setStatusMessage('')
      setLoading(false)
      if (error.message?.includes('cancelled') || error.message?.includes('abort')) {
        showInfo(t('auth.securityKeyCancelled'))
      }
    }
  }

  // Manual WebAuthn retry
  const handleWebAuthnRetry = async () => {
    setLoading(true)
    await tryWebAuthnLogin()
  }

  // Password login
  const handlePasswordLogin = async (e) => {
    e.preventDefault()
    
    if (!password) {
      showError('Please enter your password')
      return
    }

    setLoading(true)
    setStatusMessage('Signing in...')
    
    try {
      const userData = await authMethodsService.loginPassword(username, password)
      saveUsername(username)
      await login(username, password, userData)
      showSuccess(`Welcome back, ${username}!`)
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || 'Invalid credentials')
      setPassword('')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  // Go back to username step
  const handleBack = () => {
    setStep('username')
    setAuthMethod(null)
    setPassword('')
    setStatusMessage('')
  }

  // Change user (clear username)
  const handleChangeUser = () => {
    setUsername('')
    localStorage.removeItem(STORAGE_KEY)
    handleBack()
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
              ? (username ? t('auth.clickToContinue') : t('auth.signInToContinue'))
              : statusMessage || (authMethod === 'password' ? t('auth.enterPasswordToContinue') : t('auth.chooseAuthMethod'))
            }
          </p>
        </div>

        {/* Step 1: Username */}
        {step === 'username' && (
          <div className="space-y-3 sm:space-y-4">
            {/* If username saved from localStorage: show identity card */}
            {hasSavedUsername && username ? (
              <>
                {/* Clickable user identity card */}
                <button
                  onClick={handleContinue}
                  disabled={loading}
                  className="w-full text-left relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-3 sm:p-4 hover:border-accent/50 hover:shadow-lg transition-all group"
                >
                  <div className="absolute top-0 right-0 w-20 h-20 sm:w-24 sm:h-24 bg-accent/5 rounded-full -translate-y-1/2 translate-x-1/2 group-hover:bg-accent/10 transition-colors" />
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-br from-accent to-accent/70 flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
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
                    <div className="absolute inset-0 bg-bg-primary/50 flex items-center justify-center rounded-xl">
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
                  label={t('auth.username')}
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
              <div className="absolute top-0 right-0 w-20 h-20 sm:w-24 sm:h-24 bg-accent/5 rounded-full -translate-y-1/2 translate-x-1/2" />
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-br from-accent to-accent/70 flex items-center justify-center shadow-lg">
                  <User size={20} className="text-white sm:hidden" weight="bold" />
                  <User size={24} className="text-white hidden sm:block" weight="bold" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-medium">{t('auth.signingInAs')}</p>
                  <p className="text-base sm:text-lg font-semibold text-text-primary truncate">{username}</p>
                </div>
                <button
                  onClick={handleChangeUser}
                  className="px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-accent hover:bg-accent/10 rounded-lg transition-all"
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
                  onClick={handleWebAuthnRetry}
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
                  label={t('auth.password')}
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
                      className="text-sm text-accent hover:text-accent/80 hover:underline transition-colors"
                    >
                      {t('auth.forgotPassword')}
                    </Link>
                  </div>
                )}

                {/* Show WebAuthn option if available */}
                {userMethods?.webauthn && userMethods.webauthn_credentials > 0 && authMethodsService.isWebAuthnSupported() && (
                  <button
                    onClick={() => {
                      setAuthMethod('webauthn')
                      handleWebAuthnRetry()
                    }}
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
                <span>{t('auth.key')}</span>
              </div>
            )}
            <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'password' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
              <Key size={12} weight="fill" />
              <span>{t('auth.password')}</span>
            </div>
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
                          currentLang.code === lang.code && "text-accent-primary bg-accent-primary/10"
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
                title={t('settings.appearance')}
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
                          themeFamily === theme.id && "text-accent-primary bg-accent-primary/10"
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
                    <div className="px-2 py-0.5 text-xs text-text-tertiary uppercase tracking-wider">{t('settings.appearance')}</div>
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
                          mode === opt.id && "text-accent-primary bg-accent-primary/10"
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
            Ultimate Certificate Manager v2
          </p>
        </div>
      </Card>
    </div>
  )
}
