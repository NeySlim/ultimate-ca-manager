/**
 * A CA left without a parent because UCM cannot verify the parent's signature here:
 * the parent proposed, linked on an explicit confirmation; a link confirmed by hand,
 * who and when, with the means to withdraw it.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { SideAction } from './SideField'
import { Modal } from '../Modal'
import { Button } from '../Button'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'
import { extractData, formatDate } from '../../lib/utils'

export function ParentConfirmationSection({ ca, canWrite = false, onChanged }) {
  const { t } = useTranslation()
  const [dialog, setDialog] = useState(null)
  const candidate = ca?.parent_candidate
  const confirmed = !!ca?.parent_confirmed_at

  if (!candidate && !confirmed) return null

  // Two notices of the side panel (`p.notice` of the mockup), each with its action as a text link
  return (
    <>
      {candidate && (
        <p className="notice warn" data-testid="parent-candidate">
          <Icon name="link" />
          <span>
            {t('cas.parentCandidateBanner', { name: candidate.name, algorithm: candidate.algorithm })}
            {canWrite && <SideAction onClick={() => setDialog('link')}>{t('cas.linkToParent')}</SideAction>}
          </span>
        </p>
      )}
      {confirmed && (
        <p className="notice" data-testid="parent-confirmed">
          <Icon name="link" />
          <span>
            {t('cas.parentConfirmedBanner', { user: ca.parent_confirmed_by || '-', date: formatDate(ca.parent_confirmed_at) })}
            {canWrite && <SideAction onClick={() => setDialog('withdraw')}>{t('cas.withdrawParentLink')}</SideAction>}
          </span>
        </p>
      )}
      {dialog && (
        <ParentDialog ca={ca} candidate={candidate} mode={dialog} onClose={() => setDialog(null)} onChanged={onChanged} />
      )}
    </>
  )
}

function ParentDialog({ ca, candidate, mode, onClose, onChanged }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const linking = mode === 'link'

  const submit = async (e) => {
    e?.preventDefault?.()
    setBusy(true)
    try {
      const res = linking ? await casService.confirmParent(ca.id, candidate.id) : await casService.withdrawParent(ca.id)
      showSuccess(t(linking ? 'cas.linkParentDone' : 'cas.withdrawParentDone'))
      const updated = extractData(res)
      if (updated?.id) onChanged?.(updated)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      onClose()
    } catch (err) {
      showError(err?.message || t(linking ? 'cas.linkParentFailed' : 'cas.withdrawParentFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onOpenChange={(v) => !v && !busy && onClose()}
           title={t(linking ? 'cas.linkParentTitle' : 'cas.withdrawParentTitle')} size="md">
      <form onSubmit={submit} className="p-4 space-y-3">
        <p className="text-xs text-text-secondary">
          {linking
            ? t('cas.linkParentWarning', { name: candidate?.name, algorithm: candidate?.algorithm })
            : t('cas.withdrawParentWarning')}
        </p>
        {linking && (
          <label className="flex items-start gap-2 text-xs text-text-primary cursor-pointer">
            <input type="checkbox" className="w-4 h-4 mt-0.5 accent-accent-primary" checked={checked}
                   onChange={(e) => setChecked(e.target.checked)} data-testid="parent-confirm-check" />
            <span>{t('cas.linkParentConfirm')}</span>
          </label>
        )}
        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
          <Button type="submit" variant={linking ? 'primary' : 'danger'} loading={busy} disabled={linking && !checked}>
            {t(linking ? 'cas.linkToParent' : 'cas.withdrawParentLink')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
