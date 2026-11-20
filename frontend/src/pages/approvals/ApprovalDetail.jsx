/**
 * Approval request in the inspector: heading (state, Approve… and Reject… while
 * it waits), then the Request and Log sections.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, Check, Prohibit } from '@phosphor-icons/react'
import { StatusPill } from '../../components/list'
import { WorkButton, WorkRecord, WorkRecords } from '../../components/work'
import { SectionTabs, tabId, panelId } from '../../components/inspector/InspectorTabs'
import { usePermission } from '../../hooks'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { approvalsService } from '../../services'
import { formatDate } from '../../lib/utils'
import { requestDeadline, stateOf, requesterOf, lastVote, typeLabel, subjectOf, loadCaIndex, sanLine } from './approvalModel'
import { useApprovalDecision } from './useApprovalDecision'
import '../../components/work/work.css'

const APPROVAL_SECTIONS = ['request', 'log']

function Props({ rows }) {
  return (
    <dl className="ins-props">
      {rows.filter(Boolean).map(([k, v]) => (
        <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></div>
      ))}
    </dl>
  )
}

function Section({ title, children }) {
  return <section><h3 className="ins-section-title">{title}</h3>{children}</section>
}

// Name and level of an authority ("Services CA G2 · level 2"), for a reader of the CAs; null until known
function useCaLabel(id) {
  const { canRead } = usePermission()
  const [label, setLabel] = useState(null)
  const allowed = !!id && canRead('cas')
  useEffect(() => {
    if (!allowed) return undefined
    let live = true
    loadCaIndex().then((index) => { if (live) setLabel(index.get(String(id)) || null) })
    return () => { live = false }
  }, [id, allowed])
  return allowed ? label : null
}

export function ApprovalRequestPanel({ req }) {
  const { t } = useTranslation()
  const openEntity = useOpenEntity()
  const s = req.request_summary || {}
  const pending = req.status === 'pending'
  const vote = lastVote(req)
  const ca = useCaLabel(s.ca_id || s.target_ca_id)
  const link = (type, id, text) => (
    <button type="button" className="ins-link" onClick={() => openEntity(type, id)}>{text}</button>
  )
  const caText = (id) => (ca?.name
    ? <>{ca.name} <span className="ins-muted">· {t('cas.tree.level', { level: ca.level })}</span></>
    : `#${id}`)
  const target = s.certificate_id || req.certificate_id
  const signing = s.csr || req.request_type === 'csr'
  return (
    <div className="wk-detail-grid">
      <Section title={t('approvals.work.detail.request')}>
        <Props rows={[
          [t('approvals.work.detail.id'), <span className="ins-mono">#{req.id}</span>],
          [t('common.type'), typeLabel(req, t)],
          [t('approvals.requester'), requesterOf(req, t)],
          req.policy_name && [t('approvals.policy'), req.policy_name],
          [t('approvals.work.detail.submitted'), formatDate(req.created_at, { time: true })],
          pending && [t('approvals.work.detail.due'), formatDate(requestDeadline(req), { time: true })],
          [t('approvals.work.detail.state'), <StatusPill {...stateOf(req, t)} />],
          (req.required_approvals || 1) > 1 && [t('approvals.work.detail.votes'),
            t('approvals.work.votes', { count: (req.approvals || []).filter((v) => v.action === 'approve').length, need: req.required_approvals })],
          req.requester_comment && [t('approvals.work.detail.reason'), req.requester_comment],
        ]} />
      </Section>
      <Section title={signing ? t('approvals.work.detail.csr') : t('approvals.work.detail.object')}>
        <Props rows={[
          s.cn && [t('approvals.work.detail.subject'), req.request_type === 'csr' ? `CN=${s.cn}` : s.cn],
          s.ca_id && [t('approvals.work.detail.ca'), link('ca', s.ca_id, caText(s.ca_id))],
          s.target_ca_id && [t('approvals.work.detail.ca'), link('ca', s.target_ca_id, caText(s.target_ca_id))],
          s.csr_id && [t('approvals.work.detail.csrId'), `#${s.csr_id}`],
          target && [t('approvals.certificateId'), link('certificate', target, `#${target}`)],
          s.serial_number && [t('approvals.summarySerial'), <span className="ins-mono">{s.serial_number}</span>],
          s.reason && [t('revocation.reasonLabel'), t(`revocation.reasons.${s.reason}`, s.reason)],
          s.invalidity_at && [t('approvals.summaryInvalidity'), formatDate(s.invalidity_at)],
          s.trigger === 'auto' && [t('approvals.summaryTrigger'), t('approvals.triggerScheduler')],
          s.protocol && [t('approvals.summaryProtocol'), `${s.protocol.toUpperCase()}${s.operation ? ` (${s.operation})` : ''}`],
          s.protocol && [t('approvals.summaryIdentity'), <span className="ins-mono">{s.identity || '—'}</span>],
          s.validity_days && [t('approvals.work.detail.validity'), t('approvals.work.detail.days', { count: s.validity_days })],
          s.extra_ekus?.length > 0 && [t('approvals.summaryExtraEkus'), <span className="ins-mono">{s.extra_ekus.join(', ')}</span>],
          s.extra_san?.length > 0 && [t('approvals.work.detail.extraSan'),
            <>{s.extra_san.map((v, i) => <span key={i}>{i > 0 && <br />}{sanLine(v, t)}</span>)}</>],
        ]} />
        {s.csr && (
          <details className="ins-more">
            <summary>{t('approvals.summaryCsr')}</summary>
            <pre className="wk-pre">{s.csr}</pre>
          </details>
        )}
      </Section>
      {!pending && (
        <Section title={t('approvals.work.detail.decision')}>
          <Props rows={[
            [t('approvals.work.detail.decision'), <StatusPill {...stateOf(req, t)} />],
            vote && [t('approvals.work.detail.by'), vote.username],
            req.resolved_at && [t('approvals.work.detail.on'), formatDate(req.resolved_at, { time: true })],
            [t('approvals.work.dialog.reason'), vote?.comment || <span className="ins-muted">{t('approvals.work.detail.noReason')}</span>],
          ]} />
        </Section>
      )}
    </div>
  )
}

// The mockup's journal: what happened, its detail under it, who and when on the right
export function ApprovalLog({ req }) {
  const { t } = useTranslation()
  const when = (d) => formatDate(d, { time: true })
  const entries = [
    { at: req.created_at, label: t('approvals.work.log.submitted'), meta: t('approvals.work.log.what', { what: typeLabel(req, t), subject: subjectOf(req) }), actor: requesterOf(req, t) },
    ...(req.approvals || []).map((v) => ({
      at: v.timestamp,
      label: t(v.action === 'approve' ? 'approvals.work.log.approved' : 'approvals.work.log.rejected'),
      meta: v.comment || t('approvals.work.log.noReason'),
      actor: v.username,
    })),
    ['expired', 'cancelled'].includes(req.status) && req.resolved_at
      && { at: req.resolved_at, label: t(`approvals.work.log.${req.status}`), meta: '' },
  ].filter(Boolean).sort((a, b) => new Date(b.at) - new Date(a.at))
  return (
    <WorkRecords empty={t('approvals.work.log.none')}>
      {entries.map((e, i) => (
        <WorkRecord key={i} title={e.label} meta={e.meta}
          badge={<span className="wk-rl-meta">{[e.actor, when(e.at)].filter(Boolean).join(' · ')}</span>} />
      ))}
    </WorkRecords>
  )
}

export function ApprovalDetail({ data: req, objectKey, title, section, onSection, onChanged }) {
  const { t } = useTranslation()
  const { canWrite } = usePermission()
  // After a decision the request is read again: its state and votes changed
  const decision = useApprovalDecision({
    onDone: () => approvalsService.getById(req.id).then((res) => { if (res?.data) onChanged?.(res.data) }).catch(() => {}),
  })
  const pending = req.status === 'pending'
  return (
    <>
      <header className="ins-heading">
        <div className="ins-title">
          <CheckCircle className="ins-title-icon" aria-hidden="true" />
          <h2>{title}</h2>
          <StatusPill {...stateOf(req, t)} />
        </div>
        {pending && canWrite('approvals') && (
          <div className="ins-actions">
            <WorkButton icon={Check} onClick={() => decision.open('approve', [req])}
              aria-label={t('approvals.work.approveNamed', { name: title })}>{t('approvals.work.approveAsk')}</WorkButton>
            <WorkButton quiet icon={Prohibit} onClick={() => decision.open('reject', [req])}
              aria-label={t('approvals.work.rejectNamed', { name: title })}>{t('approvals.work.rejectAsk')}</WorkButton>
          </div>
        )}
      </header>
      <SectionTabs objectKey={objectKey} sections={APPROVAL_SECTIONS} current={section} onSelect={onSection}
        labelOf={(s) => t(`approvals.work.sections.${s}`)} />
      <div role="tabpanel" id={`${panelId(objectKey)}-section`} aria-labelledby={`${tabId(objectKey)}-${section}`}
        className="ins-panel" tabIndex={0}>
        {section === 'request' ? <ApprovalRequestPanel req={req} /> : <ApprovalLog req={req} />}
      </div>
      {decision.dialog}
    </>
  )
}

export default ApprovalDetail
