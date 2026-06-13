import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Vault, Warning } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { Textarea } from './Textarea'
import { useNotification } from '../contexts'
import { keyRecoveryService } from '../services'

export function KeyRecoveryRequestModal({ certId, certName, open, onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!reason.trim()) { showError(t('keyRecovery.reasonRequired')); return }
    setBusy(true)
    try {
      await keyRecoveryService.request(certId, reason.trim())
      showSuccess(t('keyRecovery.requestSubmitted'))
      setReason('')
      onClose()
    } catch (e) {
      showError(e.message || t('keyRecovery.actionFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose}
           title={certName ? t('keyRecovery.requestTitleNamed', { name: certName }) : t('keyRecovery.requestTitle')}>
      <div className="p-4 space-y-3">
        <p className="flex items-start gap-1.5 text-xs text-text-secondary">
          <Warning size={14} className="mt-0.5 shrink-0 text-status-warning" />
          {t('keyRecovery.requestInfo')}
        </p>
        <Textarea
          label={t('keyRecovery.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t('keyRecovery.reasonHint')}
          rows={3}
          autoFocus
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="button" variant="primary" disabled={busy || !reason.trim()} onClick={submit}>
            <Vault size={16} /> {t('keyRecovery.submitRequest')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default KeyRecoveryRequestModal
