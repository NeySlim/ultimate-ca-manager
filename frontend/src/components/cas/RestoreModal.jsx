/**
 * RestoreModal — restore an offline CA back to online state.
 *
 * Two modes (driven by ca.offline_mode):
 *   - password_protected: just ask for password, POST JSON
 *   - file_exported:      ask for password + .key file, POST multipart
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, UploadSimple, Warning } from '@phosphor-icons/react'
import { Modal } from '../Modal'
import { Button } from '../Button'
import { Input } from '../Input'
import { casService } from '../../services'
import { useNotification } from '../../contexts'

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
    () => `${t('cas.restore')} — ${ca?.common_name || ca?.descr || `CA #${ca?.id}`}`,
    [t, ca]
  )

  return (
    <Modal open={open} onOpenChange={(v) => !v && handleClose()} title={title} size="md">
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <div className="flex items-start gap-3 p-3 rounded-md bg-accent-success-op10 border border-accent-success-op30">
          <ShieldCheck size={20} className="text-accent-success shrink-0 mt-0.5" />
          <div className="text-sm text-text-primary">
            <p className="font-medium">{t('cas.restoreExplain.title')}</p>
            <p className="text-text-secondary text-xs mt-0.5">
              {needsFile ? t('cas.restoreExplain.fileExported') : t('cas.restoreExplain.passwordProtected')}
            </p>
          </div>
        </div>

        {needsFile && (
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-text-secondary">
              {t('cas.offlineKeyFile')} <span className="status-danger-text">*</span>
            </label>
            <label
              htmlFor="ucm-restore-key-file"
              className="flex items-center gap-2 px-3 py-2 bg-bg-tertiary border border-border rounded-md cursor-pointer hover:border-text-tertiary transition-colors"
            >
              <UploadSimple size={16} className="text-text-tertiary" />
              <span className="text-sm text-text-primary truncate">
                {keyFile ? keyFile.name : t('cas.offlineKeyFilePick')}
              </span>
            </label>
            <input
              id="ucm-restore-key-file"
              type="file"
              accept=".key,.pem,application/x-pem-file"
              className="hidden"
              onChange={(e) => setKeyFile(e.target.files?.[0] || null)}
            />
            {keyFile && keyFile.size > 256 * 1024 && (
              <p className="text-xs status-danger-text flex items-center gap-1">
                <Warning size={12} /> {t('cas.offlineKeyFileTooLarge')}
              </p>
            )}
          </div>
        )}

        <Input
          label={t('cas.offlinePassword')}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoFocus
          helperText={t('cas.restorePasswordHint')}
        />

        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="primary" loading={submitting} disabled={!canSubmit}>
            {t('cas.restore')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
