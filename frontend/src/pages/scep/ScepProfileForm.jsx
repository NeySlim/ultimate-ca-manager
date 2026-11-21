import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Cloud } from '@phosphor-icons/react'
import { Button, Input, Select, Modal } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { scepService } from '../../services'
import { useNotification } from '../../contexts'
import { scepPickerCas, unlistedScepPickerCas } from '../../lib/caSelection'
import { extractData } from '../../lib/utils'

const EMPTY_FORM = {
  name: '', url_slug: '', description: '', ca_id: '',
  template_id: '', challenge_password: '', auto_approve: false, enabled: true,
  intune_enabled: false, intune_app_id: '',
}

// The form of a SCEP profile: a named endpoint at /scep/<slug>/pkiclient.exe, bound to its own
// CA, template, challenge and approval policy (issue #228). `profile` null creates one.
export default function ScepProfileForm({ profile, cas, templates, onClose, onSaved, onManageIntuneApps }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const editing = profile
  const showModal = true
  const setShowModal = (open) => { if (!open) onClose() }
  const [formData, setFormData] = useState(() => (profile ? {
    name: profile.name,
    url_slug: profile.url_slug,
    description: profile.description || '',
    ca_id: String(cas.find(c => c.refid === profile.ca_refid)?.id ?? ''),
    template_id: profile.template_id ? String(profile.template_id) : '',
    challenge_password: '',
    auto_approve: profile.auto_approve,
    enabled: profile.enabled,
    intune_enabled: profile.intune_enabled || false,
    intune_app_id: profile.intune_app_id ? String(profile.intune_app_id) : '',
  } : EMPTY_FORM))
  const [saving, setSaving] = useState(false)
  const [slugTouched, setSlugTouched] = useState(Boolean(profile))
  const [intuneApps, setIntuneApps] = useState([])

  // The app registrations to pick from, fetched when the form opens
  useEffect(() => {
    let current = true
    scepService.getIntuneApps()
      .then(res => { if (current) setIntuneApps(extractData(res) || []) })
      .catch(() => { if (current) setIntuneApps([]) })
    return () => { current = false }
  }, [])

  const slugify = (name) =>
    (name || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64)

  const update = (field, val) => setFormData(prev => {
    const next = { ...prev, [field]: val }
    if (field === 'name' && !slugTouched && !editing) next.url_slug = slugify(val)
    if (field === 'url_slug') setSlugTouched(true)
    // Intune's flow is a synchronous validate-then-issue round trip -- there's
    // no human queue on Intune's side to poll, so auto-approve is mandatory
    // whenever Intune validation is on (enforced again server-side).
    if (field === 'intune_enabled' && val) next.auto_approve = true
    return next
  })

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = {
        name: formData.name,
        url_slug: formData.url_slug || undefined,
        description: formData.description,
        ca_id: formData.ca_id ? parseInt(formData.ca_id) : undefined,
        template_id: formData.template_id ? parseInt(formData.template_id) : null,
        auto_approve: formData.auto_approve,
        enabled: formData.enabled,
        intune_enabled: formData.intune_enabled,
        intune_app_id: formData.intune_enabled && formData.intune_app_id ? parseInt(formData.intune_app_id) : null,
      }
      if (formData.challenge_password) payload.challenge_password = formData.challenge_password
      if (editing) {
        await scepService.updateProfile(editing.id, payload)
        showSuccess(t('scep.profileUpdated'))
      } else {
        await scepService.createProfile(payload)
        showSuccess(t('scep.profileCreated'))
      }
      onSaved()
    } catch (error) {
      showError(error.message || t('common.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={showModal}
      onClose={() => setShowModal(false)}
      title={editing ? t('scep.editProfile') : t('scep.newProfile')}
    >
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('common.name')}
            value={formData.name}
            onChange={(e) => update('name', e.target.value)}
            required
          />
          <Input
            label={t('scep.profileSlug')}
            value={formData.url_slug}
            onChange={(e) => update('url_slug', e.target.value)}
            placeholder="device-certs"
            helperText={t('scep.profileSlugHelp')}
          />
        </div>
        <Input
          label={t('common.description')}
          value={formData.description}
          onChange={(e) => update('description', e.target.value)}
        />
        <Select
          label={t('common.certificateAuthority')}
          value={formData.ca_id}
          onChange={(val) => update('ca_id', val)}
          placeholder={t('certificates.selectCA')}
          options={scepPickerCas(cas, formData.ca_id).map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name }))}
          helperText={unlistedScepPickerCas(cas, formData.ca_id) > 0 ? t('cas.notListedForScep', { count: unlistedScepPickerCas(cas, formData.ca_id) }) : undefined}
        />
        <Select
          label={t('scep.profileTemplate')}
          value={formData.template_id}
          onChange={(val) => update('template_id', val)}
          placeholder={t('scep.noTemplate')}
          options={[
            { value: '', label: t('scep.noTemplate') },
            // A deactivated template is refused on binding: only the one the profile already binds stays listed
            ...templates.filter(tpl => tpl.is_active !== false || String(tpl.id) === String(editing?.template_id ?? ''))
              .map(tpl => ({ value: String(tpl.id), label: tpl.name })),
          ]}
        />
        <p className="text-xs text-text-tertiary -mt-2">{t('scep.profileTemplateHelp')}</p>
        {!formData.intune_enabled && (
          <Input
            label={t('scep.challenge')}
            type="password"
            noAutofill
            value={formData.challenge_password}
            onChange={(e) => update('challenge_password', e.target.value)}
            placeholder={editing && editing.challenge_set ? '••••••••' : ''}
            helperText={t('scep.profileChallengeHelp')}
          />
        )}
        <ToggleSwitch
          checked={formData.auto_approve}
          onChange={(val) => update('auto_approve', val)}
          label={t('scep.autoApprove')}
          disabled={formData.intune_enabled}
          size="sm"
        />
        {formData.intune_enabled && (
          <p className="text-xs text-text-tertiary -mt-2">{t('scep.intuneForcesAutoApprove')}</p>
        )}

        <div className="pt-2 border-t border-border space-y-3">
          <ToggleSwitch
            checked={formData.intune_enabled}
            onChange={(val) => update('intune_enabled', val)}
            label={t('scep.intuneEnabled')}
            size="sm"
          />
          {formData.intune_enabled && (
            <>
              <Select
                label={t('scep.intuneApp')}
                value={formData.intune_app_id}
                onChange={(val) => update('intune_app_id', val)}
                placeholder={t('scep.selectIntuneApp')}
                options={intuneApps.map(app => ({
                  value: String(app.id), label: `${app.name} (${app.tenant_id})`,
                }))}
              />
              {intuneApps.length === 0 && (
                <p className="text-xs text-text-tertiary -mt-2">{t('scep.noIntuneAppsYet')}</p>
              )}
              <div className="flex items-center gap-2">
                {onManageIntuneApps && (
                  <Button type="button" variant="ghost" size="sm"
                          onClick={() => { setShowModal(false); onManageIntuneApps() }}>
                    <Cloud size={14} />
                    {t('scep.manageIntuneApps')}
                  </Button>
                )}
              </div>
            </>
          )}
        </div>

        <ToggleSwitch
          checked={formData.enabled}
          onChange={(val) => update('enabled', val)}
          label={t('common.enabled')}
          size="sm"
        />
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={() => setShowModal(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" loading={saving}>
            {editing ? t('common.saveChanges') : t('common.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
