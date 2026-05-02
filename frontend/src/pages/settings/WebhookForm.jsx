import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Input } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'

const WEBHOOK_EVENTS = [
  'certificate.issued',
  'certificate.revoked',
  'certificate.renewed',
  'certificate.expiring',
  'ca.created',
  'ca.updated',
  'csr.submitted',
  'csr.approved',
  'csr.rejected',
]

export const WEBHOOK_EVENT_LABELS = {
  'certificate.issued': 'Issued',
  'certificate.revoked': 'Revoked',
  'certificate.renewed': 'Renewed',
  'certificate.expiring': 'Expiring',
  'ca.created': 'CA Created',
  'ca.updated': 'CA Updated',
  'csr.submitted': 'CSR Submitted',
  'csr.approved': 'CSR Approved',
  'csr.rejected': 'CSR Rejected',
}

export default function WebhookForm({ webhook, onSave, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    name: webhook?.name || '',
    url: webhook?.url || '',
    events: webhook?.events || [],
    ca_filter: webhook?.ca_filter || '',
    enabled: webhook?.enabled ?? true,
  })

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const toggleEvent = (event) => {
    setFormData(prev => ({
      ...prev,
      events: prev.events.includes(event)
        ? prev.events.filter(e => e !== event)
        : [...prev.events, event]
    }))
  }

  const toggleAllEvents = () => {
    setFormData(prev => ({
      ...prev,
      events: prev.events.length === WEBHOOK_EVENTS.length ? [] : [...WEBHOOK_EVENTS]
    }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('common.name')}
        value={formData.name}
        onChange={e => handleChange('name', e.target.value)}
        required
        placeholder={t('webhooks.namePlaceholder')}
      />
      <Input
        label="URL"
        value={formData.url}
        onChange={e => handleChange('url', e.target.value)}
        required
        placeholder="https://example.com/webhook"
      />
      <Input
        label={t('webhooks.caFilter')}
        value={formData.ca_filter}
        onChange={e => handleChange('ca_filter', e.target.value)}
        placeholder={t('webhooks.caFilterPlaceholder')}
      />

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-text-primary">{t('webhooks.events')}</label>
          <button type="button" onClick={toggleAllEvents} className="text-xs text-accent-primary hover:underline">
            {formData.events.length === WEBHOOK_EVENTS.length ? t('common.deselectAll') : t('common.selectAll')}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {WEBHOOK_EVENTS.map(event => (
            <label key={event} className="flex items-center gap-2 p-2 rounded-lg bg-tertiary-50 border border-border-op30 cursor-pointer hover:border-accent-primary-op50 transition-colors">
              <input
                type="checkbox"
                checked={formData.events.includes(event)}
                onChange={() => toggleEvent(event)}
                className="rounded border-border bg-bg-tertiary"
              />
              <span className="text-xs text-text-primary">{WEBHOOK_EVENT_LABELS[event] || event}</span>
            </label>
          ))}
        </div>
      </div>

      <ToggleSwitch
        checked={formData.enabled}
        onChange={(val) => handleChange('enabled', val)}
        label={t('webhooks.enableOnCreate')}
      />

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button type="submit">
          {webhook ? t('common.save') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}
