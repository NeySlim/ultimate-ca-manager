/**
 * Decisions and recovery on key recovery requests, from the queue or the
 * inspector: approve or reject with an optional note (one or several requests,
 * several ending on a line-by-line outcome), and the recovery itself, a
 * password-protected PKCS#12 download, one request at a time.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Prohibit, DownloadSimple, Warning } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { WorkButton, BulkOutcome, runEach } from '../../components/work'
import { keyRecoveryService } from '../../services'
import { useNotification } from '../../contexts'
import { downloadBlob } from '../../lib/utils'

export const recoveryChanged = () => window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'key_recovery' } }))
const nameOf = (req) => req.cert_cn || req.cert_refid || `#${req.cert_id}`

export function useRecoveryActions({ onDone } = {}) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [ask, setAsk] = useState(null) // { kind: 'approve'|'reject'|'recover', requests }
  const [note, setNote] = useState('')
  const [password, setPassword] = useState('')
  const [legacy, setLegacy] = useState(false)  // PKCS#12 3DES/SHA-1 profile (#331)
  const [invalid, setInvalid] = useState(false)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState(null)
  const pwd = useRef(null)

  const open = (kind, requests) => {
    setAsk({ kind, requests }); setNote(''); setPassword(''); setLegacy(false); setInvalid(false); setOutcome(null)
  }
  const close = () => { setAsk(null); setOutcome(null); setPassword(''); setNote('') }

  const finish = async () => {
    recoveryChanged()
    await onDone?.()
  }

  const decide = async () => {
    const { kind, requests } = ask
    setBusy(true)
    try {
      if (requests.length === 1) {
        try {
          await keyRecoveryService[kind](requests[0].id, note.trim() || undefined)
          showSuccess(t(`keyRecovery.${kind === 'approve' ? 'approved' : 'rejected'}`))
        } catch (e) {
          showError(e?.message || t('keyRecovery.actionFailed'))
        }
        close()
      } else {
        setOutcome(await runEach(requests, (req) => keyRecoveryService[kind](req.id, note.trim() || undefined)))
      }
    } finally {
      setBusy(false)
      await finish()
    }
  }

  const recover = async () => {
    const req = ask.requests[0]
    if (password.length < 8) { setInvalid(true); pwd.current?.focus(); return }
    setBusy(true)
    try {
      const blob = await keyRecoveryService.recover(req.id, password, legacy)
      downloadBlob(blob, `${req.cert_cn || req.cert_refid || 'recovered'}.p12`)
      showSuccess(t('keyRecovery.recovered'))
      close()
    } catch (e) {
      showError(e?.message || t('keyRecovery.actionFailed'))
    } finally {
      setBusy(false)
      await finish()
    }
  }

  const kind = ask?.kind
  const many = ask?.requests.length > 1
  const title = !ask ? '' : outcome ? t('work.bulk.title')
    : kind === 'recover' ? t('keyRecovery.recoverTitle')
      : t(`keyRecovery.work.dialog.${kind}${many ? 'Many' : 'One'}`)

  const dialog = (
    <Modal open={!!ask} onOpenChange={(v) => { if (!v) close() }} title={title} size="md">
      {ask && outcome ? (
        <BulkOutcome outcome={outcome} nameOf={(req) => `#${req.id} · ${nameOf(req)}`} onClose={close} />
      ) : ask && kind === 'recover' ? (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); recover() }}>
          <p className="wk-notice is-warn"><Warning aria-hidden="true" /><span>{t('keyRecovery.recoverWarning')}</span></p>
          <p><strong>{nameOf(ask.requests[0])}</strong></p>
          <div className="wk-field">
            <label htmlFor="recover-password">{t('keyRecovery.p12Password')}</label>
            <input id="recover-password" ref={pwd} type="password" autoComplete="new-password" value={password} autoFocus
              onChange={(e) => { setPassword(e.target.value); if (invalid) setInvalid(false) }}
              aria-invalid={invalid || undefined} aria-describedby="recover-hint" />
            <small id="recover-hint">{t('keyRecovery.p12PasswordHint')}</small>
            {invalid && <p className="wk-field-error" role="alert"><Warning aria-hidden="true" /><span>{t('keyRecovery.passwordTooShort')}</span></p>}
          </div>
          <label className="wk-check-line">
            <input type="checkbox" checked={legacy} onChange={(e) => setLegacy(e.target.checked)} />
            <span>{t('export.legacyPkcs12')}<br /><span className="wk-muted">{t('export.legacyPkcs12Desc')}</span></span>
          </label>
          <div className="wk-dialog-actions">
            <WorkButton onClick={close}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary icon={DownloadSimple} disabled={busy}>{t('keyRecovery.download')}</WorkButton>
          </div>
        </form>
      ) : ask && (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); decide() }}>
          <ul className="wk-dialog-list">
            {ask.requests.map((req) => (
              <li key={req.id}><strong>#{req.id}</strong> · {nameOf(req)} <span className="wk-muted">({req.requested_by})</span></li>
            ))}
          </ul>
          <div className="wk-field">
            <label htmlFor="recovery-note">
              {t('keyRecovery.work.dialog.note')} <span className="wk-optional">{t('approvals.work.dialog.optional')}</span>
            </label>
            <textarea id="recovery-note" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} autoFocus
              aria-describedby="recovery-note-hint" />
            <small id="recovery-note-hint">{t('keyRecovery.work.dialog.noteHint')}</small>
          </div>
          <div className="wk-dialog-actions">
            <WorkButton onClick={close}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary={kind === 'approve'} danger={kind === 'reject'} icon={kind === 'approve' ? Check : Prohibit}
              disabled={busy} data-testid="recovery-confirm">
              {t(kind === 'approve' ? 'keyRecovery.approve' : 'keyRecovery.reject')}{many ? ` (${ask.requests.length})` : ''}
            </WorkButton>
          </div>
        </form>
      )}
    </Modal>
  )

  return { open, dialog }
}
