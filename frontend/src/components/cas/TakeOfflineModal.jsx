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
import { ShieldWarning, Lock, DownloadSimple, Warning } from '@phosphor-icons/react'
import { Modal } from '../Modal'
import { Button } from '../Button'
import { Input } from '../Input'
import { casService } from '../../services'
import { useNotification } from '../../contexts'

export function TakeOfflineModal({ open, onClose, ca, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()

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
    const fname = `${(ca?.descr || ca?.common_name || `ca-${ca?.id}`).replace(/[^A-Za-z0-9._-]/g, '_')}-offline.key`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fname
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
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
    () => `${t('cas.takeOffline')} — ${ca?.common_name || ca?.descr || `CA #${ca?.id}`}`,
    [t, ca]
  )

  return (
    <Modal open={open} onOpenChange={(v) => !v && handleClose()} title={title} size="md">
      {step === 'confirm' && (
        <div className="p-4 space-y-4">
          <div className="flex items-start gap-3 p-3 rounded-md bg-status-warning-op10 border border-status-warning-op30">
            <ShieldWarning size={20} className="text-status-warning shrink-0 mt-0.5" />
            <div className="text-sm text-text-primary space-y-1">
              <p className="font-medium">{t('cas.offlineExplain.title')}</p>
              <p className="text-text-secondary text-xs">{t('cas.offlineExplain.body')}</p>
            </div>
          </div>

          <div className="space-y-2 text-xs text-text-secondary">
            <p>{t('cas.offlineExplain.bullet1')}</p>
            <p>{t('cas.offlineExplain.bullet2')}</p>
            <p>{t('cas.offlineExplain.bullet3')}</p>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t border-border">
            <Button type="button" variant="secondary" onClick={handleClose}>
              {t('common.cancel')}
            </Button>
            <Button type="button" variant="primary" onClick={() => setStep('form')}>
              {t('common.continue')}
            </Button>
          </div>
        </div>
      )}

      {step === 'form' && (
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="space-y-2">
            <label className="block text-xs font-medium text-text-secondary">
              {t('cas.offlineMode')} <span className="status-danger-text">*</span>
            </label>

            <button
              type="button"
              onClick={() => setMode('password_protected')}
              className={`w-full text-left p-3 rounded-md border transition-all flex items-start gap-3 ${
                mode === 'password_protected'
                  ? 'border-accent-primary bg-accent-primary-op10'
                  : 'border-border hover:border-text-tertiary'
              }`}
            >
              <Lock size={18} className="text-accent-primary shrink-0 mt-0.5" />
              <div className="text-sm">
                <div className="font-medium text-text-primary">{t('cas.offlinePasswordProtected')}</div>
                <div className="text-xs text-text-secondary mt-0.5">{t('cas.offlineModeDesc.passwordProtected')}</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setMode('file_exported')}
              className={`w-full text-left p-3 rounded-md border transition-all flex items-start gap-3 ${
                mode === 'file_exported'
                  ? 'border-accent-warning bg-status-warning-op10'
                  : 'border-border hover:border-text-tertiary'
              }`}
            >
              <DownloadSimple size={18} className="text-accent-warning shrink-0 mt-0.5" />
              <div className="text-sm">
                <div className="font-medium text-text-primary">{t('cas.offlineFileExported')}</div>
                <div className="text-xs text-text-secondary mt-0.5">{t('cas.offlineModeDesc.fileExported')}</div>
              </div>
            </button>
          </div>

          {mode === 'file_exported' && (
            <div className="flex items-start gap-2 p-2.5 rounded-md bg-status-warning-op10 border border-status-warning-op30 text-xs">
              <Warning size={14} className="text-status-warning shrink-0 mt-0.5" />
              <span className="text-text-secondary">{t('cas.offlineFileExportedWarning')}</span>
            </div>
          )}

          <Input
            label={t('cas.offlinePassword')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            showStrength
            autoFocus
            helperText={t('cas.offlinePasswordHint')}
            error={passwordTooShort ? t('cas.passwordTooShort') : undefined}
          />

          <Input
            label={t('cas.offlinePasswordConfirm')}
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            error={confirm.length > 0 && !passwordsMatch ? t('cas.passwordMismatch') : undefined}
          />

          <div className="flex justify-between gap-2 pt-3 border-t border-border">
            <Button type="button" variant="ghost" onClick={() => setStep('confirm')} disabled={submitting}>
              {t('common.back')}
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={handleClose} disabled={submitting}>
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                variant={mode === 'file_exported' ? 'warning-soft' : 'primary'}
                loading={submitting}
                disabled={!canSubmit}
              >
                {mode === 'file_exported' ? t('cas.takeOfflineAndDownload') : t('cas.takeOffline')}
              </Button>
            </div>
          </div>
        </form>
      )}
    </Modal>
  )
}
