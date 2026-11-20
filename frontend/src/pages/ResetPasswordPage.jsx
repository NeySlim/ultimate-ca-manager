/**
 * New password from an emailed reset link (?token=), in the sign-in frame.
 */
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CaretRight, Warning } from '@phosphor-icons/react'
import { AuthFrame, AuthField } from '../components/auth/AuthFrame'
import { PasswordMeter } from '../components/auth/PasswordMeter'
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
  const titleRef = useRef(null)

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
      setTimeout(() => titleRef.current?.focus(), 0)
    } catch (err) {
      setError(err.message || t('auth.resetFailed'))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <AuthFrame ref={titleRef} title={t('auth.passwordReset')} lead={t('auth.passwordResetSuccess')}>
        <button type="button" className="auth-btn is-primary auth-submit" onClick={() => navigate('/login')}>
          <CaretRight size={16} aria-hidden="true" />{t('auth.goToLogin')}
        </button>
      </AuthFrame>
    )
  }

  if (!token) {
    return (
      <AuthFrame ref={titleRef} title={t('auth.invalidLink')} lead={t('auth.invalidLinkDesc')}>
        <Link to="/forgot-password" className="auth-btn is-primary auth-submit">
          <CaretRight size={16} aria-hidden="true" />{t('auth.requestNewResetLink')}
        </Link>
        <Link to="/login" className="auth-link">{t('auth.backToLogin')}</Link>
      </AuthFrame>
    )
  }

  return (
    <AuthFrame ref={titleRef} title={t('auth.resetPasswordTitle')} lead={t('auth.resetPasswordDesc')}>
      <form className="auth-form" onSubmit={handleSubmit} noValidate aria-busy={loading || undefined}>
        <AuthField id="reset-new" label={t('common.newPassword')}>
          <input
            id="reset-new"
            name="new-password"
            type="password"
            autoComplete="new-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby="reset-new-hint"
          />
          <PasswordMeter password={password} />
          <small id="reset-new-hint" className="auth-wait">{t('auth.minCharacters')}</small>
        </AuthField>
        <AuthField id="reset-confirm" label={t('common.confirmPassword')}>
          <input
            id="reset-confirm"
            name="confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </AuthField>
        {error && (
          <div className="auth-error" role="alert"><Warning size={14} aria-hidden="true" /><span>{error}</span></div>
        )}
        <button type="submit" className="auth-btn is-primary auth-submit" disabled={loading}>
          <CaretRight size={16} aria-hidden="true" />{loading ? t('auth.resetting') : t('auth.resetPasswordTitle')}
        </button>
      </form>
      <Link to="/login" className="auth-link">{t('auth.backToLogin')}</Link>
    </AuthFrame>
  )
}
