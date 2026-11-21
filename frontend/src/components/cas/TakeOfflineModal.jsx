/**
 * TakeOfflineModal — take a CA offline by encrypting its private key with a
 * user-supplied password.
 *
 * Two-step flow:
 *   1. confirm  — explain what taking offline does + warn about file_exported
 *   2. form     — choose mode + enter password (twice) + submit
 *
 * On success:
 *   - password_protected: closes, shows toast, parent refreshes
 *   - file_exported:      triggers .key download, closes, shows toast
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks/usePermission'
import { canExportPrivateKey } from '../../lib/exportPermissions'
import { downloadBlob } from '../../lib/utils'
import { AtelierDialog, Icon } from '../atelier'

export function TakeOfflineModal({ open, onClose, ca, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  // file_exported hands the key over: offered only where the server allows it
  const canExportKey = canExportPrivateKey('ca', { canWrite, hasPermission })

  const [step, setStep] = useState('confirm')        // 'confirm' | 'form'
  const [mode, setMode] = useState('password_protected')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const passwordsMatch = password.length > 0 && password === confirm
  const passwordTooShort = password.length > 0 && password.length < 12
  const canSubmit = !submitting && passwordsMatch && !passwordTooShort

  const reset = () => {
    setStep('confirm')
    setMode('password_protected')
    setPassword('')
    setConfirm('')
    setSubmitting(false)
  }

  const handleClose = () => {
    if (submitting) return
    reset()
    onClose?.()
  }

  const downloadKeyBlob = (blob) => {
    downloadBlob(blob, `${ca?.descr || ca?.common_name || `ca-${ca?.id}`}-offline.key`)
  }

  const handleSubmit = async (e) => {
    e?.preventDefault?.()
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const res = await casService.takeOffline(ca.id, { password, mode })
      if (mode === 'file_exported' && res instanceof Blob) {
        downloadKeyBlob(res)
      }
      showSuccess(t('messages.success.create.caOffline'))
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      onSuccess?.()
      reset()
      onClose?.()
    } catch (err) {
      showError(err?.message || t('cas.offlineFailed'))
      setSubmitting(false)
    }
  }

  const title = useMemo(
    () => `${t('cas.takeOffline')}: ${ca?.common_name || ca?.descr || `CA #${ca?.id}`}`,
    [t, ca]
  )

  if (!open) return null
  // The mockup's modal() and its form grammar: a notice, the mode as format options, the fields, then the actions
  return (
    <AtelierDialog title={title} size="narrow" onClose={handleClose} testId="take-offline-dialog">
      {step === 'confirm' && (
        <>
          <p className="notice warn"><Icon name="lock" /><span><strong>{t('cas.offlineExplain.title')}</strong> {t('cas.offlineExplain.body')}</span></p>
          <ul className="link-list">
            <li className="small">{t('cas.offlineExplain.bullet1')}</li>
            <li className="small">{t('cas.offlineExplain.bullet2')}</li>
            <li className="small">{t('cas.offlineExplain.bullet3')}</li>
          </ul>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={handleClose}>{t('common.cancel')}</button>
            <button type="button" className="btn primary" onClick={() => setStep('form')}>{t('common.continue')}</button>
          </div>
        </>
      )}

      {step === 'form' && (
        <form onSubmit={handleSubmit}>
          <div className="form-fields">
            <fieldset className="field full">
              <legend>{t('cas.offlineMode')}</legend>
              <div className="choice-grid">
                <label className="format-option">
                  <input type="radio" name="offlineMode" value="password_protected" checked={mode === 'password_protected'} onChange={() => setMode('password_protected')} />
                  <span>{t('cas.offlinePasswordProtected')}<small>{t('cas.offlineModeDesc.passwordProtected')}</small></span>
                </label>
                {canExportKey && (
                  <label className="format-option">
                    <input type="radio" name="offlineMode" value="file_exported" checked={mode === 'file_exported'} onChange={() => setMode('file_exported')} />
                    <span>{t('cas.offlineFileExported')}<small>{t('cas.offlineModeDesc.fileExported')}</small></span>
                  </label>
                )}
              </div>
            </fieldset>
            {mode === 'file_exported' && <p className="notice warn"><Icon name="warning" /><span>{t('cas.offlineFileExportedWarning')}</span></p>}
            <div className="field full">
              <label htmlFor="offline-password">{t('cas.offlinePassword')}</label>
              <input id="offline-password" type="password" value={password} required autoComplete="new-password" data-autofocus=""
                aria-describedby="hint-offline-password" aria-invalid={passwordTooShort || undefined} onChange={(e) => setPassword(e.target.value)} />
              <small id="hint-offline-password">{t('cas.offlinePasswordHint')}</small>
              {passwordTooShort && <p className="field-error"><Icon name="warning" /><span>{t('cas.passwordTooShort')}</span></p>}
            </div>
            <div className="field full">
              <label htmlFor="offline-confirm">{t('cas.offlinePasswordConfirm')}</label>
              <input id="offline-confirm" type="password" value={confirm} required autoComplete="new-password"
                aria-invalid={(confirm.length > 0 && !passwordsMatch) || undefined} onChange={(e) => setConfirm(e.target.value)} />
              {confirm.length > 0 && !passwordsMatch && <p className="field-error"><Icon name="warning" /><span>{t('cas.passwordMismatch')}</span></p>}
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn quiet" onClick={() => setStep('confirm')} disabled={submitting}>{t('common.back')}</button>
            <button type="button" className="btn" onClick={handleClose} disabled={submitting}>{t('common.cancel')}</button>
            <button type="submit" className={mode === 'file_exported' ? 'btn danger' : 'btn primary'} data-write="" disabled={!canSubmit}>
              {mode === 'file_exported' ? t('cas.takeOfflineAndDownload') : t('cas.takeOffline')}
            </button>
          </div>
        </form>
      )}
    </AtelierDialog>
  )
}
