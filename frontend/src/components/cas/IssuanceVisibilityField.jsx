/**
 * Whether the manual issuance pickers list this CA (#430), with the switch.
 * A hidden CA stays one click away under the picker, and nothing else changes.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CompactField } from '../DetailCard'
import { Button } from '../Button'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'

export function IssuanceVisibilityField({ ca, canWrite = false, onChanged }) {
  const { t } = useTranslation()
  const hidden = !!ca.issuance_hidden

  return (
    <CompactField autoIcon="issuer" label={t('cas.issuancePickers')}>
      <span>{t(hidden ? 'cas.issuanceHiddenState' : 'cas.issuanceListedState')}</span>
      {canWrite && <VisibilitySwitch ca={ca} hidden={hidden} onChanged={onChanged} />}
    </CompactField>
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
    <Button type="button" size="xs" variant="secondary" className="ml-2" onClick={handleSwitch} disabled={saving}>
      {t(hidden ? 'cas.showInIssuance' : 'cas.hideFromIssuance')}
    </Button>
  )
}
