/**
 * The CA option enforce_unique_subject (RFC 5280 §4.1.2.6), with its switch. Turning it on
 * names the subjects several entities already share (count, first examples): they stay shared.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SideField, SideAction } from './SideField'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'

export function UniqueSubjectField({ ca, canWrite = false, onChanged }) {
  const { t } = useTranslation()
  const enforced = !!ca.enforce_unique_subject

  return (
    <SideField label={t('cas.uniqueSubject')}>
      <span title={t('cas.uniqueSubjectHelp')}>
        {t(enforced ? 'cas.uniqueSubjectEnforced' : 'cas.uniqueSubjectNotEnforced')}
      </span>
      {canWrite && <UniqueSubjectSwitch ca={ca} enforced={enforced} onChanged={onChanged} />}
      <p className="small muted">{t('cas.uniqueSubjectHelp')}</p>
    </SideField>
  )
}

/** "CN=a (1, 2); CN=b (3, 4)": the first shared subjects the API returns, with their serials. */
export function sharedExamples(examples) {
  return (examples || []).map(e => `${e.subject} (${(e.serial_numbers || []).join(', ')})`).join('; ')
}

function UniqueSubjectSwitch({ ca, enforced, onChanged }) {
  const { t } = useTranslation()
  const { showSuccess, showWarning, showError } = useNotification()
  const [saving, setSaving] = useState(false)

  const handleSwitch = async () => {
    setSaving(true)
    try {
      const res = await casService.update(ca.id, { enforceUniqueSubject: !enforced })
      const updated = res?.data || res
      showSuccess(t('cas.uniqueSubjectChanged'))
      if (updated?.shared_subjects) {
        showWarning(t('cas.uniqueSubjectShared', {
          count: updated.shared_subjects, examples: sharedExamples(updated.shared_subject_examples),
        }))
      }
      if (updated?.id) onChanged?.(updated)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    } catch (err) {
      showError(err?.message || t('cas.uniqueSubjectChangeFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <SideAction onClick={handleSwitch} disabled={saving}>
      {t(enforced ? 'cas.stopEnforcingUniqueSubject' : 'cas.enforceUniqueSubject')}
    </SideAction>
  )
}
