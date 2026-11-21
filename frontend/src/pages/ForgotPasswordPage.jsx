/**
 * Forgotten password: asks for a reset link by email, in the sign-in frame.
 * The answer is the same whether the address exists or not (no enumeration).
 */
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AuthFrame, AuthField } from '../components/auth/AuthFrame'
import { describedBy } from '../components/auth/describedBy'
import { Icon } from '../components/atelier/Icon'
import { authService } from '../services'

export default function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const titleRef = useRef(null)
  const emailRef = useRef(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!email || !email.includes('@')) {
      setError(t('auth.validEmailRequired'))
      emailRef.current?.focus()
      return
    }

    setLoading(true)
    try {
      await authService.forgotPassword(email)
    } catch {
      // Always show success to prevent email enumeration
    } finally {
      setLoading(false)
      setSent(true)
      setTimeout(() => titleRef.current?.focus(), 0)
    }
  }

  const back = <Link to="/login" className="text-link auth-switch">{t('auth.backToLogin')}</Link>

  if (sent) {
    return (
      <AuthFrame
        ref={titleRef}
        title={t('auth.checkYourEmail')}
        lead={<>{t('auth.checkEmailDescBefore')} <strong>{email}</strong>{t('auth.checkEmailDescAfter')}</>}
      >
        <p className="auth-wait">{t('auth.checkEmailHint')}</p>
        <button type="button" className="btn auth-submit" onClick={() => setSent(false)}>
          <Icon name="refresh" />{t('auth.tryAnotherEmail')}
        </button>
        {back}
      </AuthFrame>
    )
  }

  return (
    <AuthFrame ref={titleRef} title={t('auth.forgotPasswordTitle')} lead={t('auth.forgotPasswordDesc')}>
      <form className="auth-form" id="reset-form" onSubmit={handleSubmit} noValidate aria-busy={loading || undefined}>
        <AuthField id="reset-email" label={t('common.emailAddress')} error={error}>
          <input
            ref={emailRef}
            id="reset-email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={describedBy('reset-email', error)}
          />
        </AuthField>
        <button type="submit" className="btn primary auth-submit" disabled={loading}>
          <Icon name="send" />{loading ? t('auth.sending') : t('auth.sendResetLink')}
        </button>
      </form>
      {back}
    </AuthFrame>
  )
}
