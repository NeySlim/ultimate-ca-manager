import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from '@phosphor-icons/react'
import { Input, Select, Button } from '../../components'
import { useNotification } from '../../contexts'
import { ACME_CLIENT_LABELS, GROUP_NIST, GROUP_RSA, groupedOptions, listAlgorithms } from '../../lib/keyAlgorithms'
import { useFipsMode } from '../../lib/policyAlgorithms'

// An account key signs JWS (RFC 7518): RSA or a NIST curve, never Brainpool
const accountKeys = (fips) => listAlgorithms({ labels: ACME_CLIENT_LABELS, generate: true, fips })
  .filter(a => a.group === GROUP_RSA || a.group === GROUP_NIST)

export default function CreateAccountForm({ onSubmit, onCancel }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const fips = useFipsMode()
  const [formData, setFormData] = useState({
    email: '',
    key_type: accountKeys(false)[0]?.label,
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
        options={groupedOptions(accountKeys(fips), t)}
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
