/**
 * Multi-Method Login Page
 * Cascade: mTLS → WebAuthn → Password
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, Fingerprint, Key, LockKey } from '@phosphor-icons/react'
import { Card, Button, Input, Logo, LoadingSpinner } from '../components'
import { useAuth, useNotification } from '../contexts'
import { authMethodsService } from '../services/authMethods.service'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const { showError, showSuccess } = useNotification()
  
  const [detecting, setDetecting] = useState(true)
  const [methods, setMethods] = useState(null)
  const [authMethod, setAuthMethod] = useState(null) // 'mtls' | 'webauthn' | 'password'
  
  // Password form
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  // Detect available methods on mount
  useEffect(() => {
    detectAuthMethods()
  }, [])

  const detectAuthMethods = async () => {
    try {
      const availableMethods = await authMethodsService.detectMethods()
      setMethods(availableMethods)
      
      // Auto-select best method in cascade order
      if (availableMethods.mtls && availableMethods.mtls_status === 'enrolled') {
        // mTLS certificate present and enrolled → auto-login
        setAuthMethod('mtls')
        await handleMTLSLogin()
      } else if (availableMethods.webauthn && authMethodsService.isWebAuthnSupported()) {
        // WebAuthn available
        setAuthMethod('webauthn')
      } else {
        // Fallback to password
        setAuthMethod('password')
      }
    } catch (error) {
      console.error('Failed to detect auth methods:', error)
      // Fallback to password on error
      setAuthMethod('password')
      setMethods({ password: true })
    } finally {
      setDetecting(false)
    }
  }

  const handleMTLSLogin = async () => {
    setLoading(true)
    try {
      const userData = await authMethodsService.loginMTLS()
      
      // Update auth context
      await login(userData.user.username, null, userData)
      
      showSuccess(`Logged in via mTLS: ${userData.user.username}`)
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || 'mTLS authentication failed')
      // Fallback to next method
      if (methods?.webauthn && authMethodsService.isWebAuthnSupported()) {
        setAuthMethod('webauthn')
      } else {
        setAuthMethod('password')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleWebAuthnLogin = async () => {
    if (!username) {
      showError('Please enter your username')
      return
    }

    setLoading(true)
    try {
      const userData = await authMethodsService.authenticateWebAuthn(username)
      
      // Update auth context
      await login(username, null, userData)
      
      showSuccess(`Logged in via WebAuthn: ${username}`)
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || 'WebAuthn authentication failed')
      // Fallback to password
      setAuthMethod('password')
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordLogin = async (e) => {
    e.preventDefault()
    
    if (!username || !password) {
      showError('Please enter username and password')
      return
    }

    setLoading(true)
    try {
      const userData = await authMethodsService.loginPassword(username, password)
      
      // Update auth context
      await login(username, password, userData)
      
      showSuccess(`Login successful: ${username}`)
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  // Detecting methods
  if (detecting) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-bg-primary via-bg-secondary to-bg-tertiary">
        <Card className="w-full max-w-md p-8">
          <div className="flex flex-col items-center gap-4">
            <Logo variant="horizontal" size="lg" />
            <LoadingSpinner size="lg" />
            <p className="text-sm text-text-secondary">Detecting authentication methods...</p>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-bg-primary via-bg-secondary to-bg-tertiary">
      <Card className="w-full max-w-md p-8 space-y-6">
        {/* Logo */}
        <div className="flex justify-center mb-2">
          <Logo variant="horizontal" size="lg" />
        </div>

        {/* Title */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-text-primary mb-2">
            Welcome Back
          </h1>
          <p className="text-sm text-text-secondary">
            {authMethod === 'mtls' && 'Authenticating with client certificate...'}
            {authMethod === 'webauthn' && 'Sign in with your security key'}
            {authMethod === 'password' && 'Sign in to your account'}
          </p>
        </div>

        {/* Auth Method Indicator */}
        <div className="flex justify-center gap-2 p-3 bg-bg-secondary rounded-lg border border-border">
          {methods?.mtls && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded ${authMethod === 'mtls' ? 'bg-accent text-white' : 'text-text-secondary'}`}>
              <ShieldCheck weight="fill" size={16} />
              <span className="text-xs font-medium">mTLS</span>
            </div>
          )}
          {methods?.webauthn && authMethodsService.isWebAuthnSupported() && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded ${authMethod === 'webauthn' ? 'bg-accent text-white' : 'text-text-secondary'}`}>
              <Fingerprint weight="fill" size={16} />
              <span className="text-xs font-medium">WebAuthn</span>
            </div>
          )}
          {methods?.password && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded ${authMethod === 'password' ? 'bg-accent text-white' : 'text-text-secondary'}`}>
              <Key weight="fill" size={16} />
              <span className="text-xs font-medium">Password</span>
            </div>
          )}
        </div>

        {/* mTLS Auto-Login (shown during auto-login) */}
        {authMethod === 'mtls' && loading && (
          <div className="flex flex-col items-center gap-4 py-4">
            <LoadingSpinner size="lg" />
            <p className="text-sm text-text-secondary">
              Verifying client certificate...
            </p>
          </div>
        )}

        {/* WebAuthn Form */}
        {authMethod === 'webauthn' && !loading && (
          <div className="space-y-4">
            <Input
              label="Username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              autoComplete="username"
              autoFocus
            />

            <Button
              onClick={handleWebAuthnLogin}
              className="w-full"
              disabled={loading || !username}
            >
              <Fingerprint weight="fill" size={20} />
              {loading ? 'Authenticating...' : 'Authenticate with Security Key'}
            </Button>

            {/* Fallback to password */}
            <button
              onClick={() => setAuthMethod('password')}
              className="w-full text-sm text-text-secondary hover:text-accent transition-colors"
            >
              Use password instead
            </button>
          </div>
        )}

        {/* Password Form */}
        {authMethod === 'password' && (
          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <Input
              label="Username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              disabled={loading}
              autoComplete="username"
              autoFocus
            />

            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              disabled={loading}
              autoComplete="current-password"
            />

            <Button
              type="submit"
              className="w-full"
              disabled={loading || !username || !password}
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </Button>

            {/* Show other methods if available */}
            {(methods?.webauthn && authMethodsService.isWebAuthnSupported()) && (
              <button
                onClick={() => setAuthMethod('webauthn')}
                className="w-full text-sm text-text-secondary hover:text-accent transition-colors"
                type="button"
              >
                Use security key instead
              </button>
            )}
          </form>
        )}

        {/* Footer */}
        <div className="text-center text-xs text-text-secondary pt-4 border-t border-border">
          <p>Ultimate Certificate Manager v4</p>
          <p className="mt-1 opacity-70">
            Secured with {authMethod === 'mtls' ? 'mTLS' : authMethod === 'webauthn' ? 'WebAuthn' : 'password'} authentication
          </p>
        </div>
      </Card>
    </div>
  )
}
