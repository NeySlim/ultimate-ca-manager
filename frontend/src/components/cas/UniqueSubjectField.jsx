/**
 * The CA option enforce_unique_subject (RFC 5280 §4.1.2.6), with its switch. Turning it on
 * says how many subjects several entities already share: they stay, their next issuance is refused.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CompactField } from '../DetailCard'
import { Button } from '../Button'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'

export function UniqueSubjectField({ ca, canWrite = false, onChanged }) {
  const { t } = useTranslation()
  const enforced = !!ca.enforce_unique_subject

  return (
    <CompactField autoIcon="subject" label={t('cas.uniqueSubject')}>
      <span title={t('cas.uniqueSubjectHelp')}>
        {t(enforced ? 'cas.uniqueSubjectEnforced' : 'cas.uniqueSubjectNotEnforced')}
      </span>
      {canWrite && <UniqueSubjectSwitch ca={ca} enforced={enforced} onChanged={onChanged} />}
      <p className="text-xs text-text-tertiary mt-1">{t('cas.uniqueSubjectHelp')}</p>
    </CompactField>
  )
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
      if (updated?.shared_subjects) showWarning(t('cas.uniqueSubjectShared', { count: updated.shared_subjects }))
      if (updated?.id) onChanged?.(updated)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    } catch (err) {
      showError(err?.message || t('cas.uniqueSubjectChangeFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Button type="button" size="xs" variant="secondary" className="ml-2" onClick={handleSwitch} disabled={saving}>
      {t(enforced ? 'cas.stopEnforcingUniqueSubject' : 'cas.enforceUniqueSubject')}
    </Button>
  )
}
