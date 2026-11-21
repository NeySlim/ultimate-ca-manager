import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TestTube } from '@phosphor-icons/react'
import { Button, Input, Modal, HelpCard } from '../../components'
import { scepService } from '../../services'
import { useNotification } from '../../contexts'
import { secretInputProps, secretRequiredForTarget } from '../../lib/secretTarget'

const EMPTY_FORM = { name: '', tenant_id: '', client_id: '', client_secret: '' }

// The form of an Intune app registration: one Entra app, shared by the SCEP profiles that
// validate Intune challenges with it (issue #358). `app` null creates one.
export default function IntuneAppForm({ app, onClose, onSaved }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const editing = app
  const showModal = true
  const setShowModal = (open) => { if (!open) onClose() }
  const [formData, setFormData] = useState(() => (app
    ? { name: app.name, tenant_id: app.tenant_id, client_id: app.client_id, client_secret: '' } : EMPTY_FORM))
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const update = (field, value) => setFormData(prev => ({ ...prev, [field]: value }))

  const secretTarget = {
    saved: editing, current: formData, fields: ['tenant_id', 'client_id'],
    secret: formData.client_secret, secretSaved: Boolean(editing?.client_secret_set),
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (secretRequiredForTarget(secretTarget)) {
      showError(t('common.secretRequiredForTarget'))
      return
    }
    setSaving(true)
    try {
      const payload = { name: formData.name, tenant_id: formData.tenant_id, client_id: formData.client_id }
      // A blank secret on edit keeps the stored one
      if (formData.client_secret) payload.client_secret = formData.client_secret
      if (editing) {
        await scepService.updateIntuneApp(editing.id, payload)
        showSuccess(t('scep.intuneAppUpdated'))
      } else {
        await scepService.createIntuneApp(payload)
        showSuccess(t('scep.intuneAppCreated'))
      }
      onSaved()
    } catch (error) {
      showError(error.message || t('common.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const response = await scepService.testIntuneApp({
        app_id: editing?.id,
        tenant_id: formData.tenant_id,
        client_id: formData.client_id,
        client_secret: formData.client_secret,
      })
      showSuccess(response.data?.message || t('scep.intuneTestSuccess'))
      if (editing) onSaved({ keepOpen: true })
    } catch (error) {
      showError(error.message || t('scep.intuneTestFailed'))
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal open={showModal} onClose={() => setShowModal(false)}
           title={editing ? t('scep.editIntuneApp', { name: editing.name }) : t('scep.newIntuneApp')}
           size="md">
      <form onSubmit={handleSubmit} className="p-4 space-y-3">
        <HelpCard variant="info" title={t('scep.intuneHelpTitle')}>
          {t('scep.intuneHelpDesc')}
        </HelpCard>
        <Input
          label={t('common.name')}
          value={formData.name}
          onChange={(e) => update('name', e.target.value)}
          required
        />
        <Input
          label={t('scep.intuneTenantId')}
          value={formData.tenant_id}
          onChange={(e) => update('tenant_id', e.target.value)}
          placeholder="contoso.onmicrosoft.com"
          required
        />
        <Input
          label={t('scep.intuneClientId')}
          value={formData.client_id}
          onChange={(e) => update('client_id', e.target.value)}
          required
        />
        <Input
          label={t('scep.intuneClientSecret')}
          type="password"
          noAutofill
          value={formData.client_secret}
          onChange={(e) => update('client_secret', e.target.value)}
          placeholder={editing?.client_secret_set ? '••••••••' : ''}
          required={!editing?.client_secret_set}
          {...secretInputProps(t, secretTarget)}
        />
        <div className="flex items-center justify-between gap-2 pt-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleTest}
            disabled={!formData.tenant_id || !formData.client_id || testing}
          >
            <TestTube size={14} />
            {testing ? t('common.testing') : t('scep.intuneTestConnection')}
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={saving}>
              {editing ? t('common.save') : t('common.create')}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
