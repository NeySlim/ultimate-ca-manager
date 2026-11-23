import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'
import { Input, SecretInput, Select, Modal, ToggleSwitch } from '../../components/atelier/Form'
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
    <Modal open={showModal} onClose={() => setShowModal(false)} title={editing ? t('scep.editProfile') : t('scep.newProfile')} testId="scep-profile-dialog">
      <form className="scep-profile-form" onSubmit={handleSubmit}>
        <div className="form-fields">
          <Input id="scep-profile-name" label={t('common.name')} value={formData.name} onChange={(e) => update('name', e.target.value)} required data-autofocus="" />
          <Input id="scep-profile-slug" label={t('scep.profileSlug')} value={formData.url_slug} onChange={(e) => update('url_slug', e.target.value)}
            placeholder="device-certs" helperText={t('scep.profileSlugHelp')} />
          <Input id="scep-profile-description" label={t('common.description')} full value={formData.description} onChange={(e) => update('description', e.target.value)} />
          <Select id="scep-profile-ca" label={t('common.certificateAuthority')} value={formData.ca_id} onChange={(val) => update('ca_id', val)}
            placeholder={t('certificates.selectCA')}
            options={scepPickerCas(cas, formData.ca_id).map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name }))}
            helperText={unlistedScepPickerCas(cas, formData.ca_id) > 0 ? t('cas.notListedForScep', { count: unlistedScepPickerCas(cas, formData.ca_id) }) : undefined} />
          <Select id="scep-profile-template" label={t('scep.profileTemplate')} value={formData.template_id} onChange={(val) => update('template_id', val)}
            placeholder={t('scep.noTemplate')} helperText={t('scep.profileTemplateHelp')}
            options={[
              { value: '', label: t('scep.noTemplate') },
              // A deactivated template is refused on binding: only the one the profile already binds stays listed
              ...templates.filter(tpl => tpl.is_active !== false || String(tpl.id) === String(editing?.template_id ?? ''))
                .map(tpl => ({ value: String(tpl.id), label: tpl.name })),
            ]} />
          {!formData.intune_enabled && (
            <SecretInput id="scep-profile-challenge" label={t('scep.challenge')} full value={formData.challenge_password}
              onChange={(e) => update('challenge_password', e.target.value)} placeholder={editing && editing.challenge_set ? '••••••••' : ''}
              helperText={t('scep.profileChallengeHelp')} />
          )}
          <ToggleSwitch id="scep-profile-auto" checked={formData.auto_approve} onChange={(val) => update('auto_approve', val)} label={t('scep.autoApprove')}
            disabled={formData.intune_enabled} description={formData.intune_enabled ? t('scep.intuneForcesAutoApprove') : undefined} />
          {/* Intune is one more switch of the profile: no rule sets it apart from the switch above */}
          <fieldset className="field full">
            <ToggleSwitch id="scep-profile-intune" checked={formData.intune_enabled} onChange={(val) => update('intune_enabled', val)} label={t('scep.intuneEnabled')} />
            {formData.intune_enabled && (
              <>
                <Select id="scep-profile-intune-app" label={t('scep.intuneApp')} full value={formData.intune_app_id} onChange={(val) => update('intune_app_id', val)}
                  placeholder={t('scep.selectIntuneApp')} helperText={intuneApps.length === 0 ? t('scep.noIntuneAppsYet') : undefined}
                  options={intuneApps.map(app => ({ value: String(app.id), label: `${app.name} (${app.tenant_id})` }))} />
                {onManageIntuneApps && (
                  <div className="actions">
                    <button type="button" className="btn quiet" onClick={() => { setShowModal(false); onManageIntuneApps() }}>
                      <Icon name="globe" />{t('scep.manageIntuneApps')}
                    </button>
                  </div>
                )}
              </>
            )}
          </fieldset>
          <ToggleSwitch id="scep-profile-enabled" checked={formData.enabled} onChange={(val) => update('enabled', val)} label={t('common.enabled')} />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" data-action="close-modal" onClick={() => setShowModal(false)}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" disabled={saving || undefined}><Icon name={editing ? 'check' : 'plus'} />{saving ? t('common.saving') : (editing ? t('common.saveChanges') : t('common.create'))}</button>
        </div>
      </form>
    </Modal>
  )
}
