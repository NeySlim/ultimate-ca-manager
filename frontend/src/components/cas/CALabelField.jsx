/**
 * The display name and the free-text description of a CA (#459), rows of the side panel's
 * Identité; a writer edits both in one dialog. The certificate itself never changes.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FactRow, RowAction } from '../atelier/Detail'
import { AtelierDialog } from '../atelier/AtelierDialog'
import { Btn } from '../atelier/Btn'
import { Input, Notice, Textarea } from '../atelier/Form'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'

export const NAME_MAX = 255
export const DESCRIPTION_MAX = 1000

export function CALabelField({ ca, canWrite = false, onChanged, idPrefix = '' }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const editId = `${idPrefix}ca-label-edit-${ca.id}`
  return (
    <>
      <FactRow product label={t('cas.label.displayName')} value={ca.name || ca.descr || '—'}
        action={canWrite ? <RowAction id={editId} onClick={() => setEditing(true)}>{t('cas.label.edit')}</RowAction> : null} />
      <FactRow product label={t('cas.label.description')} long={!!ca.description}
        {...(ca.description ? { value: <span className="cert-comment">{ca.description}</span> } : { absent: t('cas.label.noDescription') })} />
      {editing && (
        <CALabelDialog ca={ca} returnTo={editId} idPrefix={idPrefix} onClose={() => setEditing(false)}
          onSaved={(updated) => { setEditing(false); onChanged?.(updated) }} />
      )}
    </>
  )
}

export function CALabelDialog({ ca, onClose, onSaved, returnTo, idPrefix = '' }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()
  const [name, setName] = useState(ca.name || ca.descr || '')
  const [description, setDescription] = useState(ca.description || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async (event) => {
    event.preventDefault()
    if (saving) return
    if (!name.trim()) {
      setError(t('cas.label.nameRequired'))
      return
    }
    setSaving(true)
    setError('')
    try {
      const res = await casService.update(ca.id, { name: name.trim(), description })
      showSuccess(t('cas.label.saved'))
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      // The PATCH answer lacks the detail's parsed fields (serial, fingerprints): kept from the shown CA
      onSaved({ ...ca, ...(res?.data ?? { name: name.trim(), descr: name.trim(), description }) })
    } catch (err) {
      setError(err?.message || t('cas.label.saveFailed'))
      setSaving(false)
    }
  }

  return (
    <AtelierDialog size="narrow" title={t('cas.label.dialogTitle')} onClose={() => { if (!saving) onClose() }} returnTo={returnTo}>
      <form onSubmit={save} noValidate>
        <div className="form-fields">
          <Input id={`${idPrefix}ca-label-name-${ca.id}`} label={t('cas.label.displayName')} value={name} maxLength={NAME_MAX}
            data-autofocus disabled={saving} onChange={(e) => setName(e.target.value)}
            hint={t('cas.label.displayNameHint', { cn: ca.common_name || '—' })} />
          <Textarea id={`${idPrefix}ca-label-description-${ca.id}`} label={t('cas.label.description')} value={description} rows={5}
            maxLength={DESCRIPTION_MAX} disabled={saving} onChange={(e) => setDescription(e.target.value)}
            hint={`${t('cas.label.descriptionHint')} ${t('cas.label.descriptionCount', { length: description.length, max: DESCRIPTION_MAX })}`} />
          {error && <Notice tone="bad">{error}</Notice>}
        </div>
        <div className="modal-actions">
          <Btn onClick={onClose} disabled={saving}>{t('common.cancel')}</Btn>
          <Btn tone="primary" icon="check" type="submit" disabled={saving}>{t('common.save')}</Btn>
        </div>
      </form>
    </AtelierDialog>
  )
}
