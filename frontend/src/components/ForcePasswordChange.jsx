/**
 * ForcePasswordChange Component - Modal to force password change
 * Shown after login if force_password_change flag is set
 */
import { useState } from 'react'
import { Lock, Warning } from '@phosphor-icons/react'
import { Modal, Button, Input } from '../components'
import { useAuth, useNotification } from '../contexts'
import { accountService } from '../services'

export function ForcePasswordChange({ onComplete }) {
  const { user } = useAuth()
  const { showSuccess, showError } = useNotification()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  })
  const [errors, setErrors] = useState({})

  const validate = () => {
    const newErrors = {}
    
    if (!formData.current_password) {
      newErrors.current_password = 'Current password is required'
    }
    
    if (!formData.new_password) {
      newErrors.new_password = 'New password is required'
    } else if (formData.new_password.length < 8) {
      newErrors.new_password = 'Password must be at least 8 characters'
    } else if (formData.new_password === formData.current_password) {
      newErrors.new_password = 'New password must be different from current'
    }
    
    if (formData.new_password !== formData.confirm_password) {
      newErrors.confirm_password = 'Passwords do not match'
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
        current_password: formData.current_password,
        new_password: formData.new_password
      })
      
      showSuccess('Password changed successfully')
      onComplete?.()
    } catch (error) {
      showError(error.message || 'Failed to change password')
      if (error.message?.includes('current')) {
        setErrors({ current_password: 'Incorrect password' })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={true}
      onClose={() => {}} // Cannot be dismissed
      title="Password Change Required"
    >
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <div className="flex items-start gap-3 p-3 rounded-lg bg-accent-warning/10 border border-accent-warning/30">
          <Warning size={20} className="text-accent-warning flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-accent-warning">Password change required</p>
            <p className="text-text-secondary mt-1">
              For security reasons, you must change your password before continuing.
            </p>
          </div>
        </div>

        <Input
          label="Current Password"
          type="password"
          value={formData.current_password}
          onChange={(e) => setFormData(prev => ({ ...prev, current_password: e.target.value }))}
          error={errors.current_password}
          autoFocus
          required
        />
        
        <Input
          label="New Password"
          type="password"
          value={formData.new_password}
          onChange={(e) => setFormData(prev => ({ ...prev, new_password: e.target.value }))}
          error={errors.new_password}
          showStrength
          required
        />
        
        <Input
          label="Confirm New Password"
          type="password"
          value={formData.confirm_password}
          onChange={(e) => setFormData(prev => ({ ...prev, confirm_password: e.target.value }))}
          error={errors.confirm_password}
          required
        />

        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={loading}>
            <Lock size={16} />
            {loading ? 'Changing...' : 'Change Password'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default ForcePasswordChange
