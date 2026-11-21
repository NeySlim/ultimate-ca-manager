/**
 * Forced password change after sign-in (first sign-in, or an administrator's reset): the server
 * refuses everything else until it is done, so the sign-in card offers the change or a sign-out,
 * nothing past it. Drawn in the mockup's authPage() card, the step that follows the sign-in.
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth, useNotification } from '../contexts'
import { accountService, usersService } from '../services'
import { AuthFrame, AuthField } from './auth/AuthFrame'
import { describedBy } from './auth/describedBy'
import { PasswordMeter } from './auth/PasswordMeter'
import { Icon } from './atelier/Icon'

export function ForcePasswordChange({ onComplete }) {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const { showSuccess, showError } = useNotification()
  const [loading, setLoading] = useState(false)
  const [policy, setPolicy] = useState(null)
  const [formData, setFormData] = useState({
    new_password: '',
    confirm_password: ''
  })
  const [errors, setErrors] = useState({})
  const newRef = useRef(null)
  const confirmRef = useRef(null)

  // Load password policy from backend
  useEffect(() => {
    usersService.getPasswordPolicy().then((res) => {
      setPolicy(res.data)
    }).catch(() => {
      // Fallback to defaults if policy endpoint unavailable
      setPolicy({ min_length: 8 })
    })
  }, [])

  // Field errors beside their field, the first one focused, as the sign-in form does
  const validate = () => {
    const newErrors = {}
    if (!formData.new_password) {
      newErrors.new_password = t('password.newRequired')
    } else if (formData.new_password.length < (policy?.min_length || 8)) {
      newErrors.new_password = t('password.minLength')
    }
    if (formData.new_password !== formData.confirm_password) {
      newErrors.confirm_password = t('common.passwordMismatch')
    }
    setErrors(newErrors)
    if (newErrors.new_password) newRef.current?.focus()
    else if (newErrors.confirm_password) confirmRef.current?.focus()
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validate()) return
    setLoading(true)
    try {
      await accountService.changePassword({
        new_password: formData.new_password,
        force_change: true
      })
      showSuccess(t('password.changeSuccess'))
      onComplete?.()
    } catch (error) {
      if (error.data?.details?.i18n_key) {
        showError(t(error.data.details.i18n_key, error.data.details.i18n_values || {}))
      } else {
        showError(error.message || t('password.changeFailed'))
      }
    } finally {
      setLoading(false)
    }
  }

  const set = (key) => (e) => {
    setFormData(prev => ({ ...prev, [key]: e.target.value }))
    if (errors[key]) setErrors(prev => ({ ...prev, [key]: undefined }))
  }

  return (
    <AuthFrame title={t('password.changeRequired')} lead={t('password.securityReason')}>
      <form className="auth-form" id="password-form" onSubmit={handleSubmit} noValidate aria-busy={loading || undefined}>
        <AuthField id="force-new" label={t('common.newPassword')} error={errors.new_password}>
          <input
            ref={newRef}
            id="force-new"
            name="new-password"
            type="password"
            autoComplete="new-password"
            value={formData.new_password}
            onChange={set('new_password')}
            aria-invalid={errors.new_password ? 'true' : undefined}
            aria-describedby={describedBy('force-new', errors.new_password)}
          />
          <PasswordMeter password={formData.new_password} />
        </AuthField>
        <AuthField id="force-confirm" label={t('common.confirmNewPassword')} error={errors.confirm_password}>
          <input
            ref={confirmRef}
            id="force-confirm"
            name="confirm-password"
            type="password"
            autoComplete="new-password"
            value={formData.confirm_password}
            onChange={set('confirm_password')}
            aria-invalid={errors.confirm_password ? 'true' : undefined}
            aria-describedby={describedBy('force-confirm', errors.confirm_password)}
          />
        </AuthField>
        <button type="submit" className="btn primary auth-submit" disabled={loading}>
          <Icon name="lock" />{loading ? t('common.loading') : t('common.changePassword')}
        </button>
      </form>
      <button type="button" className="text-link auth-switch" onClick={logout}>{t('common.logout')}</button>
    </AuthFrame>
  )
}

export default ForcePasswordChange
