/**
 * Login Page
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button, Input, Logo } from '../components'
import { useAuth, useNotification } from '../contexts'
import { LoadingSpinner } from '../components/LoadingSpinner'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, isAuthenticated, loading: authLoading } = useAuth()
  const { showError, showSuccess } = useNotification()
  
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  // Force redirect if already authenticated (wait for auth check to complete)
  useEffect(() => {
    console.log('🔍 LoginPage check - isAuthenticated:', isAuthenticated, 'loading:', loading)
    if (!loading && isAuthenticated) {
      console.log('✅ User already authenticated, redirecting...')
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, loading, navigate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!username || !password) {
      showError('Please enter username and password')
      return
    }

    setLoading(true)
    try {
      await login(username, password)
      showSuccess('Login successful!')
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <Logo variant="horizontal" size="md" />
        </div>

        {/* Login Card */}
        <Card>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <h2 className="text-sm font-semibold text-text-primary mb-0.5">Sign In</h2>
              <p className="text-xs text-text-secondary">Enter your credentials to continue</p>
            </div>

            <Input
              label="Username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              disabled={loading}
              autoComplete="username"
              autoFocus
            />

            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              disabled={loading}
              autoComplete="current-password"
            />

            <Button 
              type="submit" 
              className="w-full"
              disabled={loading}
            >
              {loading ? <LoadingSpinner size="sm" /> : 'Sign In'}
            </Button>
          </form>
        </Card>

        {/* Footer */}
        <p className="text-center text-xs text-text-secondary mt-4">
          UCM v4.0 • Powered by Radix UI
        </p>
      </div>
    </div>
  )
}
