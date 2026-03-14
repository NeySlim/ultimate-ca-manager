/**
 * ResetPassword Page - Set new password using reset token
 */
import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Lock, CheckCircle, Warning, ArrowLeft } from '@phosphor-icons/react'
import { Card, Button, Input, Logo } from '../components'
import { authService } from '../services'

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
      setError(t('auth.invalidResetLink'))
    }
  }, [token])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError(t('auth.passwordMinLength'))
      return
    }

    if (password !== confirmPassword) {
      setError(t('common.passwordMismatch'))
      return
    }

    setLoading(true)
    try {
      await authService.resetPassword(token, password)
      setSuccess(true)
    } catch (err) {
      setError(err.message || t('auth.resetFailed'))
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
                <div className="p-4 rounded-full bg-accent-success-op15">
                  <CheckCircle size={48} weight="duotone" className="text-accent-success" />
                </div>
              </div>
              
              <div>
                <h2 className="text-xl font-semibold text-text-primary">{t('auth.passwordReset')}</h2>
                <p className="text-sm text-text-secondary mt-2">
                  {t('auth.passwordResetSuccess')}
                </p>
              </div>

              <Button type="button" onClick={() => navigate('/login')} className="w-full">
                {t('auth.goToLogin')}
              </Button>
            </div>
          ) : !token ? (
            <div className="text-center space-y-4">
              <div className="flex justify-center">
                <div className="p-4 rounded-full bg-accent-danger-op15">
                  <Warning size={48} weight="duotone" className="text-accent-danger" />
                </div>
              </div>
              
              <div>
                <h2 className="text-xl font-semibold text-text-primary">{t('auth.invalidLink')}</h2>
                <p className="text-sm text-text-secondary mt-2">
                  {t('auth.invalidLinkDesc')}
                </p>
              </div>

              <Link to="/forgot-password">
                <Button variant="secondary" className="w-full">
                  {t('auth.requestNewResetLink')}
                </Button>
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-6">
                <h2 className="text-xl font-semibold text-text-primary">{t('auth.resetPasswordTitle')}</h2>
                <p className="text-sm text-text-secondary mt-1">
                  {t('auth.resetPasswordDesc')}
                </p>
              </div>

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-accent-danger-op10 border border-accent-danger-op30 text-sm text-accent-danger">
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
                  {loading ? t('auth.resetting') : t('auth.resetPasswordTitle')}
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link 
                  to="/login" 
                  className="flex items-center justify-center gap-2 text-sm text-accent-primary hover:underline"
                >
                  <ArrowLeft size={16} />
                  {t('auth.backToLogin')}
                </Link>
              </div>
            </>
          )}
        </Card>

        <p className="text-center text-xs text-text-tertiary mt-6">
          {t('common.appName', 'Ultimate Certificate Manager v2')}
        </p>
      </div>
    </div>
  )
}
