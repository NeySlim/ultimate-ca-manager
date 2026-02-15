/**
 * ResetPassword Page - Set new password using reset token
 */
import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Lock, CheckCircle, Warning, ArrowLeft } from '@phosphor-icons/react'
import { Card, Button, Input, Logo } from '../components'
import { apiClient } from '../services'

export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) {
      setError('Invalid reset link. Please request a new password reset.')
    }
  }, [token])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)
    try {
      await apiClient.post('/auth/reset-password', { token, password })
      setSuccess(true)
    } catch (err) {
      setError(err.message || 'Failed to reset password. The link may have expired.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Logo variant="stacked" size="lg" className="mx-auto" />
        </div>

        <Card className="p-6">
          {success ? (
            <div className="text-center space-y-4">
              <div className="flex justify-center">
                <div className="p-4 rounded-full bg-accent-success/15">
                  <CheckCircle size={48} weight="duotone" className="text-accent-success" />
                </div>
              </div>
              
              <div>
                <h2 className="text-xl font-semibold text-text-primary">Password Reset!</h2>
                <p className="text-sm text-text-secondary mt-2">
                  Your password has been changed successfully. You can now log in with your new password.
                </p>
              </div>

              <Button onClick={() => navigate('/login')} className="w-full">
                Go to Login
              </Button>
            </div>
          ) : !token ? (
            <div className="text-center space-y-4">
              <div className="flex justify-center">
                <div className="p-4 rounded-full bg-accent-danger/15">
                  <Warning size={48} weight="duotone" className="text-accent-danger" />
                </div>
              </div>
              
              <div>
                <h2 className="text-xl font-semibold text-text-primary">Invalid Link</h2>
                <p className="text-sm text-text-secondary mt-2">
                  This password reset link is invalid or has expired.
                </p>
              </div>

              <Link to="/forgot-password">
                <Button variant="secondary" className="w-full">
                  Request New Reset Link
                </Button>
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-6">
                <h2 className="text-xl font-semibold text-text-primary">Reset Password</h2>
                <p className="text-sm text-text-secondary mt-1">
                  Enter your new password below.
                </p>
              </div>

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                  label={t('common.newPassword')}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  icon={<Lock size={18} />}
                  placeholder={t('auth.minCharacters')}
                  autoComplete="new-password"
                  showStrength
                  autoFocus
                  required
                />

                <Input
                  label={t('common.confirmPassword')}
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  icon={<Lock size={18} />}
                  placeholder={t('auth.reenterPassword')}
                  autoComplete="new-password"
                  required
                />

                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? 'Resetting...' : 'Reset Password'}
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link 
                  to="/login" 
                  className="flex items-center justify-center gap-2 text-sm text-accent-primary hover:underline"
                >
                  <ArrowLeft size={16} />
                  Back to Login
                </Link>
              </div>
            </>
          )}
        </Card>

        <p className="text-center text-xs text-text-tertiary mt-6">
          Ultimate Certificate Manager v2
        </p>
      </div>
    </div>
  )
}
