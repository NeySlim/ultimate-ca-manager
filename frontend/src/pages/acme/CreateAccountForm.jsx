import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'
import { Input, Select } from '../../components/atelier/Form'
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
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <Input id="acme-account-email" label={t('common.emailAddress')} type="email" full value={formData.email}
          onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))} required helperText={t('acme.contactEmailHelper')} data-autofocus="" />
        <Select id="acme-account-key" label={t('common.keyType')} full value={formData.key_type}
          onChange={(val) => setFormData(prev => ({ ...prev, key_type: val }))} options={groupedOptions(accountKeys(fips), t)} />
        <label className="checkbox-line field full">
          <input type="checkbox" checked={formData.agree_tos} onChange={(e) => setFormData(prev => ({ ...prev, agree_tos: e.target.checked }))} />
          {t('acme.agreeToTerms')}
        </label>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary"><Icon name="plus" />{t('acme.createAccount')}</button>
      </div>
    </form>
  )
}
