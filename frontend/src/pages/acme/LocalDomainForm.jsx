import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FloppyDisk } from '@phosphor-icons/react'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { Input, Select, Button } from '../../components'

export default function LocalDomainForm({ domain, cas, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    domain: domain?.domain || '',
    issuing_ca_id: domain?.issuing_ca_id?.toString() || '',
    auto_approve: domain?.auto_approve ?? false,
  })

  const signingCas = (cas || []).filter(ca => ca.has_private_key)

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      ...formData,
      issuing_ca_id: formData.issuing_ca_id ? parseInt(formData.issuing_ca_id) : null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('acme.domainName')}
        value={formData.domain}
        onChange={(e) => setFormData(prev => ({ ...prev, domain: e.target.value.toLowerCase() }))}
        required
        placeholder="example.com"
        helperText={t('acme.localDomainHelper')}
        disabled={!!domain}
      />

      <Select
        label={t('acme.issuingCA')}
        value={formData.issuing_ca_id}
        onChange={(val) => setFormData(prev => ({ ...prev, issuing_ca_id: val }))}
        options={signingCas.map(ca => ({
          value: ca.id.toString(),
          label: ca.common_name || ca.descr || `CA #${ca.id}`
        }))}
        required
      />

      <ToggleSwitch
        checked={formData.auto_approve}
        onChange={(val) => setFormData(prev => ({ ...prev, auto_approve: val }))}
        label={t('acme.autoApproveRequests')}
        description={t('acme.autoApproveDesc')}
      />
      {formData.auto_approve && (
        <div className="p-3 rounded-md border border-yellow-500/40 bg-yellow-500/10 text-sm text-yellow-200">
          ⚠ {t('acme.autoApproveWarning')}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <FloppyDisk size={14} />
          {domain ? t('common.update') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}
