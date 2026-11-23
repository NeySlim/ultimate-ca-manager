/**
 * New password from an emailed reset link (?token=), in the sign-in frame.
 */
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AuthFrame, AuthField } from '../components/auth/AuthFrame'
import { describedBy } from '../components/auth/describedBy'
import { Icon } from '../components/atelier/Icon'
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
  // A field's error sits under it, as in the design; the server's refusal stays in the card
  const [fieldErrors, setFieldErrors] = useState({})
  const titleRef = useRef(null)
  const newRef = useRef(null)
  const confirmRef = useRef(null)

  const fieldError = (name, message, ref) => {
    setFieldErrors({ [name]: message })
    ref.current?.focus()
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setFieldErrors({})

    if (password.length < 8) {
      fieldError('password', t('auth.passwordMinLength'), newRef)
      return
    }

    if (password !== confirmPassword) {
      fieldError('confirm', t('common.passwordMismatch'), confirmRef)
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
        <button type="button" className="btn primary auth-submit" onClick={() => navigate('/login')}>
          <Icon name="right" />{t('auth.goToLogin')}
        </button>
      </AuthFrame>
    )
  }

  if (!token) {
    return (
      <AuthFrame ref={titleRef} title={t('auth.invalidLink')}>
        {/* A failure says itself as one: the warning notice and its icon, not a neutral lead */}
        <p className="notice warn" id="reset-invalid" role="status"><Icon name="warning" /><span>{t('auth.invalidLinkDesc')}</span></p>
        <Link to="/forgot-password" className="btn primary auth-submit">
          <Icon name="send" />{t('auth.requestNewResetLink')}
        </Link>
        <Link to="/login" className="text-link auth-switch">{t('auth.backToLogin')}</Link>
      </AuthFrame>
    )
  }

  return (
    <AuthFrame ref={titleRef} title={t('auth.resetPasswordTitle')} lead={t('auth.resetPasswordDesc')}>
      <form className="auth-form" id="reset-form" onSubmit={handleSubmit} noValidate aria-busy={loading || undefined}>
        <AuthField id="reset-new" label={t('common.newPassword')} error={fieldErrors.password}>
          <input
            ref={newRef}
            id="reset-new"
            name="new-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); if (fieldErrors.password) setFieldErrors({}) }}
            aria-invalid={fieldErrors.password ? 'true' : undefined}
            aria-describedby={describedBy('reset-new', fieldErrors.password, 'reset-new-hint')}
          />
          <PasswordMeter password={password} />
          <small id="reset-new-hint">{t('auth.minCharacters')}</small>
        </AuthField>
        <AuthField id="reset-confirm" label={t('common.confirmPassword')} error={fieldErrors.confirm}>
          <input
            ref={confirmRef}
            id="reset-confirm"
            name="confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => { setConfirmPassword(e.target.value); if (fieldErrors.confirm) setFieldErrors({}) }}
            aria-invalid={fieldErrors.confirm ? 'true' : undefined}
            aria-describedby={describedBy('reset-confirm', fieldErrors.confirm)}
          />
        </AuthField>
        <div className="form-error" id="reset-error" role="alert">{error ? <><Icon name="warning" /><span>{error}</span></> : null}</div>
        <button type="submit" className="btn primary auth-submit" disabled={loading}>
          <Icon name="check" />{loading ? t('auth.resetting') : t('auth.resetPasswordTitle')}
        </button>
      </form>
      <Link to="/login" className="text-link auth-switch">{t('auth.backToLogin')}</Link>
    </AuthFrame>
  )
}
