/**
 * ForgotPassword Page - Request password reset via email
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Envelope, ArrowLeft, CheckCircle } from '@phosphor-icons/react'
import { Card, Button, Input, Logo } from '../components'
import { apiClient } from '../services'

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
      setError('Please enter a valid email address')
      return
    }

    setLoading(true)
    try {
      await apiClient.post('/auth/forgot-password', { email })
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
                <div className="p-4 rounded-full bg-accent-success/15">
                  <CheckCircle size={48} weight="duotone" className="text-accent-success" />
                </div>
              </div>
              
              <div>
                <h2 className="text-xl font-semibold text-text-primary">Check Your Email</h2>
                <p className="text-sm text-text-secondary mt-2">
                  If an account exists with <strong>{email}</strong>, you'll receive a password reset link shortly.
                </p>
              </div>

              <div className="pt-4 space-y-3">
                <p className="text-xs text-text-tertiary">
                  Didn't receive an email? Check your spam folder or try again.
                </p>
                <Button variant="secondary" onClick={() => setSent(false)} className="w-full">
                  Try Another Email
                </Button>
              </div>

              <Link 
                to="/login" 
                className="flex items-center justify-center gap-2 text-sm text-accent-primary hover:underline pt-2"
              >
                <ArrowLeft size={16} />
                Back to Login
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-6">
                <h2 className="text-xl font-semibold text-text-primary">Forgot Password?</h2>
                <p className="text-sm text-text-secondary mt-1">
                  Enter your email and we'll send you a reset link.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                  label={t('auth.emailAddress')}
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
                  {loading ? 'Sending...' : 'Send Reset Link'}
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
