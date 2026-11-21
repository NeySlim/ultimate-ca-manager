/**
 * Decisions and recovery on key recovery requests, from the queue or the
 * inspector: approve with an optional note or reject with a reason (one or several
 * requests, several ending on a line-by-line outcome), and the recovery itself, a
 * password-protected PKCS#12 download, one request at a time. Several decisions end on
 * one message, or on a line-by-line outcome when one failed.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, Icon } from '../../components/atelier'
import { BulkOutcome, runEach } from '../../components/work'
import { keyRecoveryService } from '../../services'
import { useNotification } from '../../contexts'
import { downloadBlob } from '../../lib/utils'
import { REASON_MIN, REASON_MAX } from '../approvals/useApprovalDecision'

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
  const noteBox = useRef(null)

  const open = (kind, requests) => {
    setAsk({ kind, requests }); setNote(''); setPassword(''); setLegacy(false); setInvalid(false); setOutcome(null)
  }
  const close = () => { setAsk(null); setOutcome(null); setPassword(''); setNote('') }
  // Leaving without acting: the dialog gives the focus back to its opener; after an action, to the
  // queue (the row now at the same place), once the dialog's own return has run
  // The queue's focus once the dialog's own return ran; dropped if the page went away meanwhile
  const frame = useRef(0)
  useEffect(() => () => cancelAnimationFrame(frame.current), [])
  const settle = () => { frame.current = requestAnimationFrame(() => { frame.current = requestAnimationFrame(() => refocus?.()) }) }
  const dismiss = () => {
    const acted = !!outcome
    close()
    if (acted) settle()
  }

  const finish = async (report = false) => {
    recoveryChanged()
    await onDone?.()
    if (!report) settle()
  }

  const decide = async () => {
    const { kind, requests } = ask
    // A refusal says why, as the queue template asks of every refusal
    if (kind === 'reject' && note.trim().length < REASON_MIN) { setInvalid(true); noteBox.current?.focus(); return }
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

  const list = (requests) => (
    <div className="review-summary">
      <ul className="decision-list">
        {requests.map((req) => (
          <li key={req.id}><strong>#{req.id}</strong> · {nameOf(req)} <span className="muted">({req.requested_by})</span></li>
        ))}
      </ul>
    </div>
  )
  const actions = (submit) => (
    <div className="modal-actions">
      <Btn data-action="close-modal" onClick={dismiss}>{t('common.cancel')}</Btn>
      {submit}
    </div>
  )

  const dialog = ask && (
    <AtelierDialog title={title} subtitle={subtitle} onClose={dismiss} testId="recovery-dialog">
      {outcome ? (
        <BulkOutcome outcome={outcome} nameOf={(req) => `#${req.id} · ${nameOf(req)}`} onClose={dismiss} />
      ) : kind === 'recover' ? (
        <form noValidate onSubmit={(e) => { e.preventDefault(); recover() }}>
          <div className="notice warn" style={{ margin: '0 0 16px' }}><Icon name="warning" />{t('keyRecovery.recoverWarning')}</div>
          {list(ask.requests.slice(0, 1))}
          <div className="field decision-field">
            <label htmlFor="recover-password">{t('keyRecovery.p12Password')}</label>
            <input id="recover-password" ref={pwd} type="password" autoComplete="new-password" value={password} data-autofocus=""
              onChange={(e) => { setPassword(e.target.value); if (invalid) setInvalid(false) }}
              aria-invalid={invalid || undefined} aria-describedby={invalid ? 'recover-hint err-recover' : 'recover-hint'} />
            {invalid && <p className="field-error" id="err-recover" role="alert"><Icon name="warning" /><span>{t('keyRecovery.passwordTooShort')}</span></p>}
            <small id="recover-hint">{t('keyRecovery.p12PasswordHint')}</small>
          </div>
          <label className="checkbox-line decision-field">
            <input type="checkbox" checked={legacy} onChange={(e) => setLegacy(e.target.checked)} />
            <span>{t('export.legacyPkcs12')}<br /><small className="muted">{t('export.legacyPkcs12Desc')}</small></span>
          </label>
          {actions(<Btn type="submit" tone="primary" icon="download" disabled={busy || undefined}>{t('keyRecovery.download')}</Btn>)}
        </form>
      ) : (
        <form noValidate onSubmit={(e) => { e.preventDefault(); decide() }}>
          {list(ask.requests)}
          <div className="field decision-field">
            <label htmlFor="recovery-note">
              {kind === 'approve'
                ? <>{t('keyRecovery.work.dialog.note')} <span className="optional">{t('keyRecovery.work.dialog.optional')}</span></>
                : t('approvals.work.dialog.reason')}
            </label>
            <textarea id="recovery-note" ref={noteBox} rows={3} maxLength={REASON_MAX} value={note} data-autofocus=""
              onChange={(e) => { setNote(e.target.value); if (invalid) setInvalid(false) }}
              aria-invalid={invalid || undefined}
              aria-describedby={invalid ? 'recovery-note-hint err-recovery-note' : 'recovery-note-hint'} />
            <small id="recovery-note-hint">{t(kind === 'approve' ? 'keyRecovery.work.dialog.noteHint' : 'approvals.work.dialog.rejectHint')}</small>
            {invalid && (
              <p className="field-error" id="err-recovery-note"><Icon name="warning" /><span>{t('approvals.work.dialog.reasonRequired', { min: REASON_MIN })}</span></p>
            )}
          </div>
          <div className="notice" style={{ margin: '16px 0 0' }}>
            <Icon name="help" />{t(`keyRecovery.work.dialog.${kind === 'approve' ? 'approveNote' : 'rejectNote'}${many ? 'Many' : ''}`)}
          </div>
          {actions(
            <Btn type="submit" tone={kind === 'approve' ? 'primary' : 'danger'} icon={kind === 'approve' ? 'check' : 'block'}
              disabled={busy || undefined} data-testid="recovery-confirm">
              {t(kind === 'approve' ? 'keyRecovery.work.approve' : 'keyRecovery.work.reject')}{many ? ` (${ask.requests.length})` : ''}
            </Btn>,
          )}
        </form>
      )}
    </AtelierDialog>
  )

  return { open, dialog }
}
