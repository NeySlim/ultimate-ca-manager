import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'
import { Input, Select, ToggleSwitch } from '../../components/atelier/Form'
import { pickerCas, unlistedPickerCas } from '../../lib/caSelection'

export default function LocalDomainForm({ domain, cas, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    domain: domain?.domain || '',
    issuing_ca_id: domain?.issuing_ca_id?.toString() || '',
    auto_approve: domain?.auto_approve ?? false,
  })

  // Only CAs able to sign now, plus the saved one so an existing domain keeps showing its CA
  const signingCas = pickerCas(cas, formData.issuing_ca_id)
  const unlisted = unlistedPickerCas(cas, formData.issuing_ca_id)

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      ...formData,
      issuing_ca_id: formData.issuing_ca_id ? parseInt(formData.issuing_ca_id) : null,
    })
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
      <Input
        id="acme-domain-name"
        full
        data-autofocus=""
        label={t('acme.domainName')}
        value={formData.domain}
        onChange={(e) => setFormData(prev => ({ ...prev, domain: e.target.value.toLowerCase() }))}
        required
        placeholder="example.com"
        helperText={t('acme.localDomainHelper')}
        disabled={!!domain}
      />

      <Select
        id="acme-domain-ca"
        full
        label={t('acme.issuingCA')}
        value={formData.issuing_ca_id}
        onChange={(val) => setFormData(prev => ({ ...prev, issuing_ca_id: val }))}
        options={signingCas.map(ca => ({
          value: ca.id.toString(),
          label: ca.common_name || ca.descr || `CA #${ca.id}`
        }))}
        helperText={unlisted > 0 ? t('cas.notListedForSigning', { count: unlisted }) : undefined}
        required
      />

      <ToggleSwitch
        checked={formData.auto_approve}
        onChange={(val) => setFormData(prev => ({ ...prev, auto_approve: val }))}
        label={t('acme.autoApproveRequests')}
        description={t('acme.autoApproveDesc')}
      />
      {formData.auto_approve && (
        <p className="notice warn"><Icon name="warning" /><span>{t('acme.autoApproveWarning')}</span></p>
      )}

      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary"><Icon name="check" />{domain ? t('common.update') : t('common.create')}</button>
      </div>
    </form>
  )
}
