/**
 * Decisions and recovery on key recovery requests, from the queue or the
 * inspector: approve or reject with an optional note (one or several requests,
 * several ending on a line-by-line outcome), and the recovery itself, a
 * password-protected PKCS#12 download, one request at a time. Several decisions end on
 * one message, or on a line-by-line outcome when one failed.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Prohibit, DownloadSimple, Warning, Question } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { WorkButton, BulkOutcome, runEach, rememberFocus } from '../../components/work'
import { keyRecoveryService } from '../../services'
import { useNotification } from '../../contexts'
import { downloadBlob } from '../../lib/utils'

export const recoveryChanged = () => window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'key_recovery' } }))
const nameOf = (req) => req.cert_cn || req.cert_refid || `#${req.cert_id}`

/** onDone reloads after an action; refocus places the focus once the dialog is gone (else it goes back where it was). */
export function useRecoveryActions({ onDone, refocus } = {}) {
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
  const back = useRef(null)

  const open = (kind, requests) => {
    back.current = rememberFocus()
    setAsk({ kind, requests }); setNote(''); setPassword(''); setLegacy(false); setInvalid(false); setOutcome(null)
  }
  const close = () => { setAsk(null); setOutcome(null); setPassword(''); setNote('') }
  // Leaving without acting gives the focus back to the opening control; leaving the outcome, to the queue
  const settle = () => (refocus ? requestAnimationFrame(refocus) : back.current?.())
  const dismiss = () => {
    const acted = !!outcome
    close()
    if (acted) settle()
    else back.current?.()
  }

  const finish = async (report = false) => {
    recoveryChanged()
    await onDone?.()
    if (!report) settle()
  }

  const decide = async () => {
    const { kind, requests } = ask
    setBusy(true)
    let report = false
    try {
      if (requests.length === 1) {
        try {
          await keyRecoveryService[kind](requests[0].id, note.trim() || undefined)
          showSuccess(t(`keyRecovery.work.toast.${kind === 'approve' ? 'approvedOne' : 'rejectedOne'}`, { id: requests[0].id }))
        } catch (e) {
          showError(e?.message || t('keyRecovery.actionFailed'))
        }
        close()
      } else {
        const done = await runEach(requests, (req) => keyRecoveryService[kind](req.id, note.trim() || undefined))
        // All through: one message; a failure keeps the line-by-line outcome open
        if (done.every((o) => o.ok)) {
          showSuccess(t(`keyRecovery.work.toast.${kind === 'approve' ? 'approvedMany' : 'rejectedMany'}`, { count: done.length }))
          close()
        } else {
          report = true
          setOutcome(done)
        }
      }
    } finally {
      setBusy(false)
      await finish(report)
    }
  }

  const recover = async () => {
    const req = ask.requests[0]
    if (password.length < 8) { setInvalid(true); pwd.current?.focus(); return }
    setBusy(true)
    let failed = false
    try {
      const blob = await keyRecoveryService.recover(req.id, password, legacy)
      downloadBlob(blob, `${req.cert_cn || req.cert_refid || 'recovered'}.p12`)
      showSuccess(t('keyRecovery.recovered'))
      close()
    } catch (e) {
      // The dialog stays open on the failure, the focus with it
      failed = true
      showError(e?.message || t('keyRecovery.actionFailed'))
    } finally {
      setBusy(false)
      await finish(failed)
    }
  }

  const kind = ask?.kind
  const many = ask?.requests.length > 1
  const title = !ask ? '' : outcome ? t('work.bulk.title')
    : kind === 'recover' ? t('keyRecovery.recoverTitle')
      : t(`keyRecovery.work.dialog.${kind}${many ? 'Many' : 'One'}`)
  const subtitle = !ask ? '' : many ? t('work.dialog.requests', { count: ask.requests.length }) : t('work.dialog.request', { id: ask.requests[0].id })

  const dialog = (
    <Modal open={!!ask} onOpenChange={(v) => { if (!v) dismiss() }} title={title} subtitle={subtitle} size="md">
      {ask && outcome ? (
        <BulkOutcome outcome={outcome} nameOf={(req) => `#${req.id} · ${nameOf(req)}`} onClose={dismiss} />
      ) : ask && kind === 'recover' ? (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); recover() }}>
          <p className="wk-notice is-warn"><Warning aria-hidden="true" /><span>{t('keyRecovery.recoverWarning')}</span></p>
          <div className="wk-review">
            <ul className="wk-dialog-list">
              <li><strong>#{ask.requests[0].id}</strong> · {nameOf(ask.requests[0])} <span className="wk-muted">({ask.requests[0].requested_by})</span></li>
            </ul>
          </div>
          <div className="wk-field">
            <label htmlFor="recover-password">{t('keyRecovery.p12Password')}</label>
            <input id="recover-password" ref={pwd} type="password" autoComplete="new-password" value={password} autoFocus
              onChange={(e) => { setPassword(e.target.value); if (invalid) setInvalid(false) }}
              aria-invalid={invalid || undefined} aria-describedby={invalid ? 'recover-hint recover-error' : 'recover-hint'} />
            <small id="recover-hint">{t('keyRecovery.p12PasswordHint')}</small>
            {invalid && <p className="wk-field-error" id="recover-error" role="alert"><Warning aria-hidden="true" /><span>{t('keyRecovery.passwordTooShort')}</span></p>}
          </div>
          <label className="wk-check-line">
            <input type="checkbox" checked={legacy} onChange={(e) => setLegacy(e.target.checked)} />
            <span>{t('export.legacyPkcs12')}<br /><span className="wk-muted">{t('export.legacyPkcs12Desc')}</span></span>
          </label>
          <div className="lv-dialog-actions">
            <WorkButton onClick={dismiss}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary icon={DownloadSimple} disabled={busy}>{t('keyRecovery.download')}</WorkButton>
          </div>
        </form>
      ) : ask && (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); decide() }}>
          <div className="wk-review">
            <ul className="wk-dialog-list">
              {ask.requests.map((req) => (
                <li key={req.id}><strong>#{req.id}</strong> · {nameOf(req)} <span className="wk-muted">({req.requested_by})</span></li>
              ))}
            </ul>
          </div>
          <div className="wk-field">
            <label htmlFor="recovery-note">
              {t('keyRecovery.work.dialog.note')} <span className="wk-optional">{t('approvals.work.dialog.optional')}</span>
            </label>
            <textarea id="recovery-note" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} autoFocus
              aria-describedby="recovery-note-hint" />
            <small id="recovery-note-hint">{t('keyRecovery.work.dialog.noteHint')}</small>
          </div>
          <p className="wk-notice">
            <Question aria-hidden="true" />
            <span>
              {t(`keyRecovery.work.dialog.${kind === 'approve' ? 'approveNote' : 'rejectNote'}${many ? 'Many' : ''}`)}
              {many && <> {t('approvals.work.dialog.manyNote')}</>}
            </span>
          </p>
          <div className="lv-dialog-actions">
            <WorkButton onClick={dismiss}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary={kind === 'approve'} danger={kind === 'reject'} icon={kind === 'approve' ? Check : Prohibit}
              disabled={busy} data-testid="recovery-confirm">
              {t(kind === 'approve' ? 'keyRecovery.work.approve' : 'keyRecovery.work.reject')}{many ? ` (${ask.requests.length})` : ''}
            </WorkButton>
          </div>
        </form>
      )}
    </Modal>
  )

  return { open, dialog }
}
