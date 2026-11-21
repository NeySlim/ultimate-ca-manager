/**
 * RestoreModal — restore an offline CA back to online state.
 *
 * Two modes (driven by ca.offline_mode):
 *   - password_protected: just ask for password, POST JSON
 *   - file_exported:      ask for password + .key file, POST multipart
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { AtelierDialog, Icon } from '../atelier'

export function RestoreModal({ open, onClose, ca, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()

  const mode = ca?.offline_mode || 'password_protected'
  const needsFile = mode === 'file_exported'

  const [password, setPassword] = useState('')
  const [keyFile, setKeyFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = !submitting && password.length > 0 && (!needsFile || keyFile)

  const reset = () => {
    setPassword('')
    setKeyFile(null)
    setSubmitting(false)
  }

  const handleClose = () => {
    if (submitting) return
    reset()
    onClose?.()
  }

  const handleSubmit = async (e) => {
    e?.preventDefault?.()
    if (!canSubmit) return
    setSubmitting(true)
    try {
      await casService.restore(ca.id, { password, keyFile: needsFile ? keyFile : undefined })
      showSuccess(t('messages.success.create.caRestored'))
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      onSuccess?.()
      reset()
      onClose?.()
    } catch (err) {
      showError(err?.message || t('cas.restoreFailed'))
      setSubmitting(false)
    }
  }

  const title = useMemo(
    () => `${t('cas.restore')}: ${ca?.common_name || ca?.descr || `CA #${ca?.id}`}`,
    [t, ca]
  )

  if (!open) return null
  return (
    <AtelierDialog title={title} size="narrow" onClose={handleClose} testId="restore-ca-dialog">
      <form onSubmit={handleSubmit}>
        <p className="notice"><Icon name="refresh" /><span><strong>{t('cas.restoreExplain.title')}</strong> {needsFile ? t('cas.restoreExplain.fileExported') : t('cas.restoreExplain.passwordProtected')}</span></p>
        <div className="form-fields">
          {needsFile && (
            <div className="field full">
              <label htmlFor="ucm-restore-key-file">{t('cas.offlineKeyFile')}</label>
              <input id="ucm-restore-key-file" type="file" accept=".key,.pem,application/x-pem-file" required
                onChange={(e) => setKeyFile(e.target.files?.[0] || null)} />
              <small>{keyFile ? keyFile.name : t('cas.offlineKeyFilePick')}</small>
              {keyFile && keyFile.size > 256 * 1024 && <p className="field-error"><Icon name="warning" /><span>{t('cas.offlineKeyFileTooLarge')}</span></p>}
            </div>
          )}
          <div className="field full">
            <label htmlFor="restore-password">{t('cas.offlinePassword')}</label>
            <input id="restore-password" type="password" value={password} required autoComplete="current-password" data-autofocus=""
              aria-describedby="hint-restore-password" onChange={(e) => setPassword(e.target.value)} />
            <small id="hint-restore-password">{t('cas.restorePasswordHint')}</small>
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={handleClose} disabled={submitting}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" data-write="" disabled={!canSubmit}>{t('cas.restore')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}
