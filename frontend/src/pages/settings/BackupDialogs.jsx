/**
 * The backup and restore dialogs in the mockup's modal(): a sentence, the fields in
 * `.form-fields`, then Annuler and the action under the rule. Each follows its job on the server
 * (progress, cancel, the archive at the end; the sign-in a committed restore asks for).
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, Notice } from '../../components/atelier'
import { Field } from '../../components/atelier/Form'
import { PasswordMeter } from '../../components/auth/PasswordMeter'

const close = (onClose, t) => <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.close')}</button>

/** A password of the mockup's field, the strength meter under it when asked. */
function PasswordField({ id, label, value, onChange, placeholder, hint, error, meter = false }) {
  const describedBy = [hint && `hint-${id}`, error && `err-${id}`].filter(Boolean).join(' ') || undefined
  return (
    <Field id={id} label={label} hint={hint} error={error} full>
      <input id={id} type="password" autoComplete="new-password" spellCheck={false} data-autofocus="" value={value}
        placeholder={placeholder} aria-describedby={describedBy} aria-invalid={error ? 'true' : undefined} onChange={onChange} />
      {meter && <PasswordMeter password={value} />}
    </Field>
  )
}

export function BackupDialog({ running, progress, job, ready, password, setPassword, problem, loading, onClose, onCreate, onCancelJob, onDownload }) {
  const { t } = useTranslation()
  return (
    <AtelierDialog title={t('settings.encryptedBackup')} size="narrow" onClose={onClose}>
      {running ? (
        <div data-testid="backup-job">
          <p role="status">{progress}</p>
          <p className="muted small">{t('settings.backupRunsInBackground')}</p>
          <div className="modal-actions">
            {close(onClose, t)}
            <Btn tone="danger" onClick={onCancelJob} disabled={!!job?.cancel_requested} data-testid="backup-job-cancel">{t('settings.backupCancel')}</Btn>
          </div>
        </div>
      ) : ready ? (
        <div data-testid="backup-ready">
          <p>{t('settings.backupReady', { filename: ready.filename })}</p>
          <div className="modal-actions">
            {close(onClose, t)}
            <Btn tone="primary" icon="download" write={false} onClick={() => onDownload(ready.filename)} data-testid="backup-ready-download">{t('common.download')}</Btn>
          </div>
        </div>
      ) : (
        <form noValidate onSubmit={(e) => { e.preventDefault(); if (!loading && !problem) onCreate() }}>
          <p>{t('settings.createBackupDesc')}</p>
          <div className="form-fields">
            <PasswordField id="backup-password" label={t('settings.encryptionPassword')} value={password} meter
              onChange={(e) => setPassword(e.target.value)} placeholder={t('settings.min12Characters')}
              hint={t('settings.encryptionPasswordHelper')} error={password ? problem : null} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
            <Btn type="submit" tone="primary" icon="archive" disabled={loading || !!problem}>
              {loading ? t('settings.creating') : t('settings.createAndDownload')}
            </Btn>
          </div>
        </form>
      )}
    </AtelierDialog>
  )
}

/**
 * The restore: its warning, the file and the password, then the job; a restore that committed
 * signs every session out, and the dialog then asks for the sign-in (same status line, kept).
 */
export function RestoreDialog({ job, uncancellable, progress, file, password, setPassword, loading, uploadLabel, onClose, onCancel, onRestore, onCancelJob, onSignIn }) {
  const { t } = useTranslation()
  const short = !password || password.length < 12
  return (
    <AtelierDialog title={t('settings.restoreFromBackup')} size="narrow" onClose={onClose}>
      {job.signInNeeded ? (
        <div data-testid="restore-sign-in">
          <p role="status">{t('settings.restoreSignInAgain')}</p>
          <div className="modal-actions">
            <Btn tone="primary" write={false} autoFocus onClick={onSignIn} data-testid="restore-sign-in-button">{t('settings.restoreSignIn')}</Btn>
          </div>
        </div>
      ) : job.running ? (
        <div data-testid="restore-job">
          <p role="status" data-testid="restore-job-progress">{progress}</p>
          <p className="muted small">{t('settings.restoreRunsInBackground')}</p>
          <div className="modal-actions">
            {close(onClose, t)}
            {/* From the commit on the server refuses the cancellation (409): none is offered */}
            {!uncancellable && (
              <Btn tone="danger" onClick={onCancelJob} disabled={!!job.job?.cancel_requested} data-testid="restore-job-cancel">{t('settings.restoreCancel')}</Btn>
            )}
          </div>
        </div>
      ) : (
        <form noValidate onSubmit={(e) => { e.preventDefault(); if (!loading && !short) onRestore() }}>
          <Notice tone="warn"><strong>{t('common.warning')}</strong>{' '}{t('settings.restoreWarning')}</Notice>
          {file && <p>{t('settings.file')}{t('work.sep')}<strong>{file.name}</strong></p>}
          <div className="form-fields">
            <PasswordField id="restore-password" label={t('settings.backupPassword')} value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder={t('settings.enterBackupPassword')} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
            <Btn type="submit" tone="danger" icon="upload" disabled={loading || short}>
              {loading ? uploadLabel : t('settings.restoreBackup')}
            </Btn>
          </div>
        </form>
      )}
    </AtelierDialog>
  )
}
