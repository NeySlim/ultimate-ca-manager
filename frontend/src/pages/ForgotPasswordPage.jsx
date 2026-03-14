/**
 * ForgotPassword Page - Request password reset via email
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Envelope, ArrowLeft, CheckCircle } from '@phosphor-icons/react'
import { Card, Button, Input, Logo } from '../components'
import { authService } from '../services'

export default function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    
    if (!email || !email.includes('@')) {
      setError(t('auth.validEmailRequired'))
      return
    }

    setLoading(true)
    try {
      await authService.forgotPassword(email)
      setSent(true)
    } catch (err) {
      // Always show success to prevent email enumeration
      setSent(true)
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
          {sent ? (
            <div className="text-center space-y-4">
              <div className="flex justify-center">
                <div className="p-4 rounded-full bg-accent-success-op15">
                  <CheckCircle size={48} weight="duotone" className="text-accent-success" />
                </div>
              </div>
              
              <div>
                <h2 className="text-xl font-semibold text-text-primary">{t('auth.checkYourEmail')}</h2>
                <p className="text-sm text-text-secondary mt-2">
                  {t('auth.checkEmailDescBefore')} <strong>{email}</strong>{t('auth.checkEmailDescAfter')}
                </p>
              </div>

              <div className="pt-4 space-y-3">
                <p className="text-xs text-text-tertiary">
                  {t('auth.checkEmailHint')}
                </p>
                <Button type="button" variant="secondary" onClick={() => setSent(false)} className="w-full">
                  {t('auth.tryAnotherEmail')}
                </Button>
              </div>

              <Link 
                to="/login" 
                className="flex items-center justify-center gap-2 text-sm text-accent-primary hover:underline pt-2"
              >
                <ArrowLeft size={16} />
                {t('auth.backToLogin')}
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-6">
                <h2 className="text-xl font-semibold text-text-primary">{t('auth.forgotPasswordTitle')}</h2>
                <p className="text-sm text-text-secondary mt-1">
                  {t('auth.forgotPasswordDesc')}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                  label={t('common.emailAddress')}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  icon={<Envelope size={18} />}
                  placeholder={t('auth.emailPlaceholder')}
                  error={error}
                  autoFocus
                  required
                />

                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? t('auth.sending') : t('auth.sendResetLink')}
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
