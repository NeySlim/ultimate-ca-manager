import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from '@phosphor-icons/react'
import { Input, Select, Button } from '../../components'
import { useNotification } from '../../contexts'

export default function CreateAccountForm({ onSubmit, onCancel }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    email: '',
    key_type: 'RSA-2048',
    agree_tos: false,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!formData.agree_tos) {
      showWarning(t('acme.agreeToTermsRequired'))
      return
    }
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('common.emailAddress')}
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText={t('acme.contactEmailHelper')}
      />
      
      <Select
        label={t('common.keyType')}
        value={formData.key_type}
        onChange={(val) => setFormData(prev => ({ ...prev, key_type: val }))}
        options={[
          { value: 'RSA-2048', label: 'RSA 2048-bit' },
          { value: 'RSA-4096', label: 'RSA 4096-bit' },
          { value: 'EC-P256', label: 'ECDSA P-256' },
          { value: 'EC-P384', label: 'ECDSA P-384' },
        ]}
      />
      
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={formData.agree_tos}
          onChange={(e) => setFormData(prev => ({ ...prev, agree_tos: e.target.checked }))}
          className="rounded border-border bg-bg-tertiary mt-1"
        />
        <span className="text-sm text-text-primary">
          {t('acme.agreeToTerms')}
        </span>
      </label>
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <Plus size={14} />
          {t('acme.createAccount')}
        </Button>
      </div>
    </form>
  )
}
