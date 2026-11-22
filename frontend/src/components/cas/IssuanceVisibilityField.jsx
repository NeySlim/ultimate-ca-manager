/**
 * Whether the manual issuance pickers list this CA (#430), with the switch.
 * A hidden CA stays one click away under the picker, and nothing else changes.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FactRow, RowAction } from '../atelier/Detail'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'

export function IssuanceVisibilityField({ ca, canWrite = false, onChanged }) {
  const { t } = useTranslation()
  const hidden = !!ca.issuance_hidden

  return (
    <FactRow product label={t('cas.issuancePickers')} value={t(hidden ? 'cas.issuanceHiddenState' : 'cas.issuanceListedState')}
      action={canWrite ? <VisibilitySwitch ca={ca} hidden={hidden} onChanged={onChanged} /> : null} />
  )
}

function VisibilitySwitch({ ca, hidden, onChanged }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [saving, setSaving] = useState(false)

  const handleSwitch = async () => {
    setSaving(true)
    try {
      const res = await casService.update(ca.id, { issuanceHidden: !hidden })
      const updated = res?.data || res
      showSuccess(t('cas.issuanceVisibilityChanged'))
      if (updated?.id) onChanged?.(updated)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    } catch (err) {
      showError(err?.message || t('cas.issuanceVisibilityChangeFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <RowAction onClick={handleSwitch} disabled={saving}>
      {t(hidden ? 'cas.showInIssuance' : 'cas.hideFromIssuance')}
    </RowAction>
  )
}
