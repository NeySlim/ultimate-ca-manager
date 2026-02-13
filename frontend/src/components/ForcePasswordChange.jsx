/**
 * ForcePasswordChange Component - Modal to force password change
 * Shown after login if force_password_change flag is set
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Lock, Warning, SkipForward } from '@phosphor-icons/react'
import { Modal, Button, Input } from '../components'
import { useAuth, useNotification } from '../contexts'
import { accountService } from '../services'

export function ForcePasswordChange({ onComplete }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showSuccess, showError } = useNotification()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    new_password: '',
    confirm_password: ''
  })
  const [errors, setErrors] = useState({})

  const validate = () => {
    const newErrors = {}
    
    if (!formData.new_password) {
      newErrors.new_password = t('password.newRequired')
    } else if (formData.new_password.length < 8) {
      newErrors.new_password = t('password.minLength')
    }
    
    if (formData.new_password !== formData.confirm_password) {
      newErrors.confirm_password = t('common.passwordMismatch')
    }
    
    setErrors(newErrors)
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
      showError(error.message || t('password.changeFailed'))
      if (error.message?.includes('current')) {
        setErrors({ current_password: t('password.incorrect') })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={true}
      onClose={() => {}} // Cannot be dismissed
      title={t('password.changeRequired')}
    >
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <div className="flex items-start gap-3 p-3 rounded-lg bg-accent-warning/10 border border-accent-warning/30">
          <Warning size={20} className="text-accent-warning flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-accent-warning">{t('password.changeRequired')}</p>
            <p className="text-text-secondary mt-1">
              {t('password.securityReason')}
            </p>
          </div>
        </div>

        <Input
          label={t('common.newPassword')}
          type="password"
          value={formData.new_password}
          onChange={(e) => setFormData(prev => ({ ...prev, new_password: e.target.value }))}
          error={errors.new_password}
          showStrength
          required
        />
        
        <Input
          label={t('common.confirmNewPassword')}
          type="password"
          value={formData.confirm_password}
          onChange={(e) => setFormData(prev => ({ ...prev, confirm_password: e.target.value }))}
          error={errors.confirm_password}
          required
        />

        <div className="flex justify-between pt-2">
          <Button variant="ghost" onClick={() => onComplete?.()} type="button">
            <SkipForward size={16} />
            {t('password.skipForNow')}
          </Button>
          <Button type="submit" disabled={loading}>
            <Lock size={16} />
            {loading ? t('common.loading') : t('common.changePassword')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default ForcePasswordChange
