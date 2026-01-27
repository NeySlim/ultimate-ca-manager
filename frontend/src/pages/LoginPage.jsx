/**
 * Login Page
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck } from '@phosphor-icons/react'
import { Card, Button, Input } from '../components'
import { useAuth, useNotification } from '../contexts'
import { LoadingSpinner } from '../components/LoadingSpinner'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const { showError, showSuccess } = useNotification()
  
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

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
        <div className="flex flex-col items-center mb-6">
          <div 
            className="w-16 h-16 bg-gradient-to-br from-accent-primary to-blue-600 rounded-lg flex items-center justify-center mb-3 shadow-lg shadow-accent-primary/20"
            style={{ background: 'var(--gradient-accent)' }}
          >
            <ShieldCheck size={32} weight="bold" className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-text-primary">UCM</h1>
          <p className="text-xs text-text-secondary mt-0.5">Ultimate CA Manager</p>
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
