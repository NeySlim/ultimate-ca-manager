/**
 * Login Page - Clean and simple
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button, Input, Logo } from '../components'
import { useAuth, useNotification } from '../contexts'

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
      // Use React Router navigation (preserves React state and cookies)
      navigate('/dashboard')
    } catch (error) {
      showError(error.message || 'Login failed')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-bg-primary via-bg-secondary to-bg-tertiary">
      <Card className="w-full max-w-md p-8 space-y-6">
        {/* Logo */}
        <div className="flex justify-center mb-6">
          <Logo variant="horizontal" size="lg" />
        </div>

        {/* Title */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-text-primary mb-2">
            Welcome Back
          </h1>
          <p className="text-sm text-text-secondary">
            Sign in to your account
          </p>
        </div>

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
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
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </Button>
        </form>

        {/* Footer */}
        <div className="text-center text-xs text-text-secondary pt-4 border-t border-border">
          <p>Ultimate Certificate Manager v4</p>
        </div>
      </Card>
    </div>
  )
}
