import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, PencilSimple, Trash, Copy, ArrowsClockwise, LinkSimple } from '@phosphor-icons/react'
import { Button, Input, Select, Card, Badge, Modal, EmptyState } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { scepService } from '../../services'
import { useNotification } from '../../contexts'

const EMPTY_FORM = {
  name: '', url_slug: '', description: '', ca_id: '',
  template_id: '', challenge_password: '', auto_approve: false, enabled: true,
}

// SCEP profiles: named endpoints at /scep/<slug>/pkiclient.exe, each bound to
// its own CA, template, challenge and approval policy (issue #228)
export default function ScepProfilesTab({ profiles, cas, templates, canWrite, onChanged }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [formData, setFormData] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [slugTouched, setSlugTouched] = useState(false)

  const baseUrl = useMemo(() => window.location.origin, [])

  const slugify = (name) =>
    (name || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64)

  const openCreate = () => {
    setEditing(null)
    setFormData(EMPTY_FORM)
    setSlugTouched(false)
    setShowModal(true)
  }

  const openEdit = (profile) => {
    setEditing(profile)
    setFormData({
      name: profile.name,
      url_slug: profile.url_slug,
      description: profile.description || '',
      ca_id: String(cas.find(c => c.refid === profile.ca_refid)?.id ?? ''),
      template_id: profile.template_id ? String(profile.template_id) : '',
      challenge_password: '',
      auto_approve: profile.auto_approve,
      enabled: profile.enabled,
    })
    setSlugTouched(true)
    setShowModal(true)
  }

  const update = (field, val) => setFormData(prev => {
    const next = { ...prev, [field]: val }
    if (field === 'name' && !slugTouched && !editing) next.url_slug = slugify(val)
    if (field === 'url_slug') setSlugTouched(true)
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
      }
      if (formData.challenge_password) payload.challenge_password = formData.challenge_password
      if (editing) {
        await scepService.updateProfile(editing.id, payload)
        showSuccess(t('scep.profileUpdated'))
      } else {
        await scepService.createProfile(payload)
        showSuccess(t('scep.profileCreated'))
      }
      setShowModal(false)
      onChanged()
    } catch (error) {
      showError(error.message || t('common.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (profile) => {
    if (!window.confirm(t('scep.profileDeleteConfirm', { name: profile.name }))) return
    try {
      await scepService.deleteProfile(profile.id)
      showSuccess(t('scep.profileDeleted'))
      onChanged()
    } catch (error) {
      showError(error.message)
    }
  }

  const handleRegenerate = async (profile) => {
    try {
      const res = await scepService.regenerateProfileChallenge(profile.id)
      const challenge = res.data?.challenge || res.challenge
      if (challenge) {
        await navigator.clipboard.writeText(challenge).catch(() => {})
        showSuccess(t('scep.profileChallengeRegenerated'))
      }
      onChanged()
    } catch (error) {
      showError(error.message)
    }
  }

  const copyUrl = async (profile) => {
    try {
      await navigator.clipboard.writeText(`${baseUrl}/scep/${profile.url_slug}/pkiclient.exe`)
      showSuccess(t('common.copied'))
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-secondary">{t('scep.profilesDesc')}</p>
        {canWrite && (
          <Button size="sm" onClick={openCreate}>
            <Plus size={14} />
            {t('scep.newProfile')}
          </Button>
        )}
      </div>

      {profiles.length === 0 ? (
        <EmptyState
          icon={LinkSimple}
          title={t('scep.noProfiles')}
          description={t('scep.noProfilesDesc')}
        />
      ) : (
        profiles.map(profile => (
          <Card key={profile.id} className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-semibold text-text-primary truncate">{profile.name}</h3>
                  {!profile.enabled && <Badge variant="warning">{t('common.disabled')}</Badge>}
                  {profile.auto_approve && <Badge variant="success">{t('scep.autoApprove')}</Badge>}
                  {profile.challenge_set && <Badge>{t('scep.challengeSetBadge')}</Badge>}
                </div>
                <div className="flex items-center gap-1 mb-1">
                  <code className="text-xs font-mono text-text-secondary truncate">
                    /scep/{profile.url_slug}/pkiclient.exe
                  </code>
                  <Button type="button" size="sm" variant="ghost" onClick={() => copyUrl(profile)} aria-label={t('common.copy')}>
                    <Copy size={12} />
                  </Button>
                </div>
                <p className="text-xs text-text-tertiary truncate">
                  {t('common.certificateAuthority')}: {profile.ca_name || profile.ca_refid}
                  {profile.template_name && <> · {t('scep.profileTemplate')}: {profile.template_name}</>}
                </p>
              </div>
              {canWrite && (
                <div className="flex items-center gap-1 flex-shrink-0">
                  <Button type="button" size="sm" variant="ghost" onClick={() => handleRegenerate(profile)} aria-label={t('scep.regenerate')}>
                    <ArrowsClockwise size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => openEdit(profile)} aria-label={t('common.edit')}>
                    <PencilSimple size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="text-text-tertiary hover:text-accent-danger" onClick={() => handleDelete(profile)} aria-label={t('common.delete')}>
                    <Trash size={14} />
                  </Button>
                </div>
              )}
            </div>
          </Card>
        ))
      )}

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
            options={cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name }))}
          />
          <Select
            label={t('scep.profileTemplate')}
            value={formData.template_id}
            onChange={(val) => update('template_id', val)}
            placeholder={t('scep.noTemplate')}
            options={[
              { value: '', label: t('scep.noTemplate') },
              ...templates.map(tpl => ({ value: String(tpl.id), label: tpl.name })),
            ]}
          />
          <p className="text-xs text-text-tertiary -mt-2">{t('scep.profileTemplateHelp')}</p>
          <Input
            label={t('scep.challenge')}
            type="password"
            noAutofill
            value={formData.challenge_password}
            onChange={(e) => update('challenge_password', e.target.value)}
            placeholder={editing && editing.challenge_set ? '••••••••' : ''}
            helperText={t('scep.profileChallengeHelp')}
          />
          <ToggleSwitch
            checked={formData.auto_approve}
            onChange={(val) => update('auto_approve', val)}
            label={t('scep.autoApprove')}
            size="sm"
          />
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
    </div>
  )
}
