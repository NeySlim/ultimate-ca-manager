import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, PencilSimple, Trash, TestTube, Cloud } from '@phosphor-icons/react'
import { Button, Input, Card, Badge, Modal, EmptyState, HelpCard } from '../../components'
import { scepService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData, formatDate } from '../../lib/utils'
import { secretInputProps, secretRequiredForTarget } from '../../lib/secretTarget'

const EMPTY_FORM = { name: '', tenant_id: '', client_id: '', client_secret: '' }

// Intune app registrations: one Entra app, shared by the SCEP profiles that
// validate Intune challenges with it (issue #358)
export default function ScepIntuneAppsTab({ canWrite }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [formData, setFormData] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const load = useCallback(async () => {
    try {
      setApps(extractData(await scepService.getIntuneApps()) || [])
    } catch (error) {
      showError(error.message || t('common.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditing(null)
    setFormData(EMPTY_FORM)
    setShowModal(true)
  }

  const openEdit = (app) => {
    setEditing(app)
    setFormData({ name: app.name, tenant_id: app.tenant_id, client_id: app.client_id, client_secret: '' })
    setShowModal(true)
  }

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
      setShowModal(false)
      load()
    } catch (error) {
      showError(error.message || t('common.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (app) => {
    const confirmed = await showConfirm(t('scep.intuneAppDeleteConfirm', { name: app.name }), {
      title: t('common.confirmDelete'),
      confirmText: t('common.delete'),
      variant: 'danger',
    })
    if (!confirmed) return
    try {
      await scepService.deleteIntuneApp(app.id)
      showSuccess(t('scep.intuneAppDeleted'))
      load()
    } catch (error) {
      showError(error.message)
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
      if (editing) load()
    } catch (error) {
      showError(error.message || t('scep.intuneTestFailed'))
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-secondary">{t('scep.intuneAppsDesc')}</p>
        {canWrite && (
          <Button size="sm" onClick={openCreate}>
            <Plus size={14} />
            {t('scep.newIntuneApp')}
          </Button>
        )}
      </div>

      {!loading && apps.length === 0 ? (
        <EmptyState
          icon={Cloud}
          title={t('scep.noIntuneApps')}
          description={t('scep.noIntuneAppsDesc')}
        />
      ) : (
        apps.map(app => (
          <Card key={app.id} className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-semibold text-text-primary truncate">{app.name}</h3>
                  <Badge variant={app.profile_count > 0 ? 'info' : 'secondary'}>
                    {app.profile_count > 0
                      ? t('scep.intuneAppUsedBy', { count: app.profile_count })
                      : t('scep.intuneAppNotUsed')}
                  </Badge>
                </div>
                <p className="text-xs text-text-secondary font-mono truncate">{app.tenant_id}</p>
                <p className="text-xs text-text-tertiary font-mono truncate">{app.client_id}</p>
                <p className="text-xs text-text-tertiary mt-1">
                  {t('scep.intuneAppLastTest')}: {app.last_test_at
                    ? `${formatDate(app.last_test_at)} (${app.last_test_result})`
                    : t('scep.intuneAppNeverTested')}
                </p>
                {app.profile_names?.length > 0 && (
                  <p className="text-xs text-text-tertiary truncate">{app.profile_names.join(', ')}</p>
                )}
              </div>
              {canWrite && (
                <div className="flex items-center gap-1 shrink-0">
                  <Button variant="ghost" size="sm" onClick={() => openEdit(app)} title={t('common.edit')}>
                    <PencilSimple size={14} />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(app)} title={t('common.delete')}>
                    <Trash size={14} />
                  </Button>
                </div>
              )}
            </div>
          </Card>
        ))
      )}

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
    </div>
  )
}
