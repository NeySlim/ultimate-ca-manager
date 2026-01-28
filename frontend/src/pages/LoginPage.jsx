/**
 * Multi-Method Login Page
 * Flow: Username → mTLS/WebAuthn → Password (fallback)
 * Remembers last username in localStorage
 */
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, Fingerprint, Key, User, ArrowRight, ArrowLeft, CaretRight } from '@phosphor-icons/react'
import { Card, Button, Input, Logo, LoadingSpinner } from '../components'
import { useAuth, useNotification } from '../contexts'
import { authMethodsService } from '../services/authMethods.service'

const STORAGE_KEY = 'ucm_last_username'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const { showError, showSuccess, showInfo } = useNotification()
  const passwordRef = useRef(null)
  
  // Login flow step: 'username' | 'auth'
  const [step, setStep] = useState('username')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [authMethod, setAuthMethod] = useState(null) // 'mtls' | 'webauthn' | 'password'
  const [userMethods, setUserMethods] = useState(null) // Methods available for this user
  const [statusMessage, setStatusMessage] = useState('')

  // Load last username on mount
  useEffect(() => {
    const lastUsername = localStorage.getItem(STORAGE_KEY)
    if (lastUsername) {
      setUsername(lastUsername)
    }
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
        setStatusMessage('Waiting for security key...')
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
      console.log('mTLS login failed, trying next method:', error.message)
      // Try WebAuthn next
      if (userMethods?.webauthn && userMethods.webauthn_credentials > 0 && authMethodsService.isWebAuthnSupported()) {
        setAuthMethod('webauthn')
        setStatusMessage('Waiting for security key...')
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
      setStatusMessage('Touch your security key...')
      const userData = await authMethodsService.authenticateWebAuthn(username)
      saveUsername(username)
      await login(username, null, userData)
      showSuccess(`Welcome back, ${username}!`)
      navigate('/dashboard')
    } catch (error) {
      console.log('WebAuthn login failed:', error.message)
      // User cancelled or error → show password form
      setAuthMethod('password')
      setStatusMessage('')
      setLoading(false)
      if (error.message?.includes('cancelled') || error.message?.includes('abort')) {
        showInfo('Security key cancelled. Use password instead.')
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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-bg-primary via-bg-secondary to-bg-tertiary p-4">
      <Card className="w-full max-w-md p-8 space-y-6">
        {/* Logo */}
        <div className="flex justify-center mb-2">
          <Logo variant="horizontal" size="lg" />
        </div>

        {/* Title */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-text-primary mb-2">
            {step === 'username' 
              ? (username ? 'Welcome Back' : 'Sign In')
              : 'Welcome Back'
            }
          </h1>
          <p className="text-sm text-text-secondary">
            {step === 'username' 
              ? (username ? 'Click to continue to your account' : 'Enter your username to continue')
              : statusMessage || (authMethod === 'password' ? 'Enter your password to continue' : 'Choose how to authenticate')
            }
          </p>
        </div>

        {/* Step 1: Username */}
        {step === 'username' && (
          <div className="space-y-4">
            {/* If username saved: show identity card */}
            {username ? (
              <>
                {/* Clickable user identity card */}
                <button
                  onClick={handleContinue}
                  disabled={loading}
                  className="w-full text-left relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-4 hover:border-accent/50 hover:shadow-lg transition-all group"
                >
                  <div className="absolute top-0 right-0 w-24 h-24 bg-accent/5 rounded-full -translate-y-1/2 translate-x-1/2 group-hover:bg-accent/10 transition-colors" />
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-accent to-accent/70 flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
                      <User size={24} className="text-white" weight="bold" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-text-secondary uppercase tracking-wider font-medium">Continue as</p>
                      <p className="text-lg font-semibold text-text-primary truncate">{username}</p>
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
                    localStorage.removeItem(STORAGE_KEY)
                  }}
                  className="w-full text-sm text-text-secondary hover:text-accent transition-colors py-2"
                  disabled={loading}
                >
                  Use a different account
                </button>
              </>
            ) : (
              /* No saved username: show input field */
              <form onSubmit={handleContinue} className="space-y-4">
                <Input
                  label="Username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
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
                      <span>Checking...</span>
                    </>
                  ) : (
                    <>
                      <span>Continue</span>
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
          <div className="space-y-5">
            {/* User identity card - modern design */}
            <div className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-bg-secondary to-bg-tertiary p-4">
              <div className="absolute top-0 right-0 w-24 h-24 bg-accent/5 rounded-full -translate-y-1/2 translate-x-1/2" />
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-accent to-accent/70 flex items-center justify-center shadow-lg">
                  <User size={24} className="text-white" weight="bold" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-medium">Signing in as</p>
                  <p className="text-lg font-semibold text-text-primary truncate">{username}</p>
                </div>
                <button
                  onClick={handleChangeUser}
                  className="px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-accent hover:bg-accent/10 rounded-lg transition-all"
                  disabled={loading}
                >
                  Change
                </button>
              </div>
            </div>

            {/* Loading state for auto-auth */}
            {loading && (authMethod === 'mtls' || authMethod === 'webauthn') && (
              <div className="flex flex-col items-center gap-4 py-6">
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
              <div className="space-y-3">
                <Button
                  onClick={handleWebAuthnRetry}
                  className="w-full"
                  variant="secondary"
                  disabled={loading}
                >
                  <Fingerprint size={20} weight="fill" />
                  <span>Try Security Key Again</span>
                </Button>
                
                <button
                  onClick={() => setAuthMethod('password')}
                  className="w-full text-sm text-text-secondary hover:text-accent transition-colors py-2"
                >
                  Use password instead
                </button>
              </div>
            )}

            {/* Password form */}
            {authMethod === 'password' && (
              <form onSubmit={handlePasswordLogin} className="space-y-4">
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
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
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
                      <span>Signing in...</span>
                    </>
                  ) : (
                    <>
                      <Key size={18} weight="fill" />
                      <span>Sign In</span>
                    </>
                  )}
                </Button>

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
                    <span>Use security key instead</span>
                  </button>
                )}
              </form>
            )}

            {/* Back button */}
            <button
              onClick={handleBack}
              className="w-full text-sm text-text-secondary hover:text-text-primary transition-colors py-2 flex items-center justify-center gap-1"
              disabled={loading}
            >
              <ArrowLeft size={14} />
              <span>Back</span>
            </button>
          </div>
        )}

        {/* Auth methods available indicator */}
        {step === 'auth' && userMethods && (
          <div className="flex justify-center gap-2 pt-2">
            {userMethods.mtls && (
              <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'mtls' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
                <ShieldCheck size={12} weight="fill" />
                <span>mTLS</span>
              </div>
            )}
            {userMethods.webauthn && userMethods.webauthn_credentials > 0 && (
              <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'webauthn' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
                <Fingerprint size={12} weight="fill" />
                <span>Key</span>
              </div>
            )}
            <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${authMethod === 'password' ? 'bg-accent text-white' : 'bg-bg-secondary text-text-secondary'}`}>
              <Key size={12} weight="fill" />
              <span>Password</span>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="text-center text-xs text-text-secondary pt-4 border-t border-border">
          <p>Ultimate Certificate Manager v4</p>
        </div>
      </Card>
    </div>
  )
}
