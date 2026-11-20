/**
 * Approve or reject approval requests, from the queue (one or several) or the
 * inspector: a confirmation with a reason (required to reject, as the server asks),
 * then one call per request. One request keeps the outcome messages of each case
 * (issued, revoked, deferred to the client, closed, failed) and opens what it
 * issued; several end on a line-by-line outcome.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Prohibit, Warning, Question } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { WorkButton, BulkOutcome, runEach } from '../../components/work'
import { approvalsService } from '../../services'
import { useNotification } from '../../contexts'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { showNotices } from '../../lib/notices'
import { approvedLocalOnlyRevocationWarning } from '../../lib/revocationOutcome'
import { requestTitle, requesterOf } from './approvalModel'

// The decision went through but issued nothing: closed, or the issuance failed and the request stays
function approvalFailure(result, t) {
  const d = result?.data
  if (d?.request_closed) return t('approvals.requestClosed', { reason: d.issue_error || '' })
  if (d?.certificate_issued === false && !d?.deferred) return t('approvals.issuanceFailed', { reason: d.issue_error || '' })
  return null
}

export const changedEvent = () => window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'approval' } }))

export function useApprovalDecision({ onDone } = {}) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const openEntity = useOpenEntity()
  const [ask, setAsk] = useState(null) // { kind: 'approve'|'reject', requests }
  const [comment, setComment] = useState('')
  const [invalid, setInvalid] = useState(false)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState(null)
  const box = useRef(null)

  const open = (kind, requests) => {
    setAsk({ kind, requests })
    setComment('')
    setInvalid(false)
    setOutcome(null)
  }
  const close = () => { setAsk(null); setOutcome(null); setComment('') }

  // One request: the messages of today's single decision
  const decideOne = async (kind, req) => {
    if (kind === 'reject') {
      await approvalsService.reject(req.id, comment.trim())
      showSuccess(t('approvals.rejectedSuccess'))
      return
    }
    const result = await approvalsService.approve(req.id, comment.trim() || undefined)
    const d = result?.data
    if (d?.certificate_issued && d.certificate?.revoked) {
      showSuccess(t('approvals.revocationPerformed'))
      const localOnly = approvedLocalOnlyRevocationWarning(d.certificate, t)
      if (localOnly) showWarning(localOnly)
    } else if (d?.certificate_issued) {
      showSuccess(t('approvals.certificateIssued'))
      showNotices(result, showWarning)
    } else if (d?.deferred) {
      // Approved: the protocol issues when its client comes back
      showSuccess(t('approvals.approvedSuccess'))
    } else if (approvalFailure(result, t)) {
      showError(approvalFailure(result, t))
    } else {
      showSuccess(t('approvals.approvedSuccess'))
    }
    // What the approval issued: a certificate, or a CA for an intermediate request
    const issued = d?.certificate_issued ? d.certificate : null
    if (issued?.id) openEntity('certificate', issued.id)
    else if (issued?.ca_id) openEntity('ca', issued.ca_id)
  }

  const confirm = async () => {
    if (!ask || busy) return
    const { kind, requests } = ask
    if (kind === 'reject' && !comment.trim()) {
      setInvalid(true)
      box.current?.focus()
      return
    }
    setBusy(true)
    try {
      if (requests.length === 1) {
        try {
          await decideOne(kind, requests[0])
        } catch (err) {
          // The server says why (already closed by someone else, expired...)
          showError(err?.message || t('approvals.actionFailed'))
        }
        close()
      } else {
        const done = await runEach(requests, async (req) => {
          const result = kind === 'approve'
            ? await approvalsService.approve(req.id, comment.trim() || undefined)
            : await approvalsService.reject(req.id, comment.trim())
          const failed = kind === 'approve' ? approvalFailure(result, t) : null
          if (failed) throw new Error(failed)
          return result
        })
        setOutcome(done)
      }
    } finally {
      setBusy(false)
      changedEvent()
      onDone?.()
    }
  }

  const many = ask?.requests.length > 1
  const approve = ask?.kind === 'approve'
  const title = !ask ? '' : outcome ? t('work.bulk.title')
    : t(`approvals.work.dialog.${approve ? 'approve' : 'reject'}${many ? 'Many' : 'One'}`)

  const dialog = (
    <Modal open={!!ask} onOpenChange={(v) => { if (!v) close() }} title={title} size="md">
      {ask && outcome ? (
        <BulkOutcome outcome={outcome} nameOf={(req) => `#${req.id} · ${requestTitle(req, t)}`} onClose={close} />
      ) : ask && (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); confirm() }}>
          <ul className="wk-dialog-list" data-testid="decision-list">
            {ask.requests.map((req) => (
              <li key={req.id}>
                <strong>#{req.id}</strong> · {requestTitle(req, t)} <span className="wk-muted">({requesterOf(req, t)})</span>
              </li>
            ))}
          </ul>
          <div className="wk-field">
            <label htmlFor="decision-reason">
              {t('approvals.work.dialog.reason')}
              {approve && <> <span className="wk-optional">{t('approvals.work.dialog.optional')}</span></>}
            </label>
            <textarea id="decision-reason" ref={box} rows={3} maxLength={2000} value={comment} autoFocus
              onChange={(e) => { setComment(e.target.value); if (invalid) setInvalid(false) }}
              aria-invalid={invalid || undefined}
              aria-describedby={invalid ? 'decision-hint decision-error' : 'decision-hint'} />
            <small id="decision-hint">{t(approve ? 'approvals.work.dialog.approveHint' : 'approvals.work.dialog.rejectHint')}</small>
            {invalid && (
              <p className="wk-field-error" id="decision-error"><Warning aria-hidden="true" /><span>{t('approvals.work.dialog.reasonRequired')}</span></p>
            )}
          </div>
          {many && (
            <p className="wk-notice"><Question aria-hidden="true" /><span>{t('approvals.work.dialog.manyNote')}</span></p>
          )}
          <div className="wk-dialog-actions">
            <WorkButton onClick={close}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary={approve} danger={!approve} icon={approve ? Check : Prohibit} disabled={busy}
              data-testid="decision-confirm">
              {t(approve ? 'approvals.work.approve' : 'approvals.work.reject')}{many ? ` (${ask.requests.length})` : ''}
            </WorkButton>
          </div>
        </form>
      )}
    </Modal>
  )

  return { open, dialog }
}
