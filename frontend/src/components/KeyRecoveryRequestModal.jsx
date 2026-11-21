/**
 * Ask for a key recovery in the mockup's modal(): the warning notice, the required reason
 * (decision-field), then Annuler and the primary request.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from './atelier'
import { useNotification } from '../contexts'
import { keyRecoveryService } from '../services'

export function KeyRecoveryRequestModal({ certId, certName, open, onClose }) {
  if (!open) return null
  return <RequestBody certId={certId} certName={certName} onClose={onClose} />
}

function RequestBody({ certId, certName, onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e?.preventDefault?.()
    if (busy) return
    if (!reason.trim()) { showError(t('keyRecovery.reasonRequired')); return }
    setBusy(true)
    try {
      await keyRecoveryService.request(certId, reason.trim())
      showSuccess(t('keyRecovery.requestSubmitted'))
      onClose()
    } catch (err) {
      showError(err.message || t('keyRecovery.actionFailed'))
      setBusy(false)
    }
  }

  return (
    <AtelierDialog title={certName ? t('keyRecovery.requestTitleNamed', { name: certName }) : t('keyRecovery.requestTitle')} size="narrow" onClose={onClose}
      testId="key-recovery-request-dialog">
      <form onSubmit={submit} noValidate>
        <div className="notice warn"><Icon name="warning" /><span>{t('keyRecovery.requestInfo')}</span></div>
        <div className="field decision-field">
          <label htmlFor="key-recovery-reason">{t('keyRecovery.reason')}</label>
          <textarea id="key-recovery-reason" rows={3} value={reason} placeholder={t('keyRecovery.reasonHint')} data-autofocus=""
            onChange={(e) => setReason(e.target.value)} />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" disabled={busy || !reason.trim() || undefined}><Icon name="key" />{t('keyRecovery.submitRequest')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}

export default KeyRecoveryRequestModal
