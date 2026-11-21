/**
 * An approval request in the module's dock: the mockup's moduleInspector() for approvals, its
 * one open tab, the heading with Approuver… and Refuser… while it waits, then requestPanel()
 * (Demande, CSR or Objet, Décision) and requestLog() (Journal). What the product knows more of a
 * request (policy, votes, protocol, identity, revocation reason, the CSR itself) are further rows.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Dock, DockBody, Pill, Props, RecordList, RecordRow, Section } from '../../components/atelier'
import { usePermission } from '../../hooks'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { formatDate } from '../../lib/utils'
import { requestDeadline, stateOf, requesterOf, lastVote, typeLabel, subjectOf, loadCaIndex, sanLine, requestTitle, isLapsed } from './approvalModel'

const when = (d) => formatDate(d, { time: true })

// Name and level of an authority ("Services CA G2 · niveau 2"), for a reader of the CAs; null until known
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
  const pending = req.status === 'pending' && !isLapsed(req)
  const vote = lastVote(req)
  const caId = s.ca_id || s.target_ca_id
  const ca = useCaLabel(caId)
  const state = stateOf(req, t)
  const target = s.certificate_id || req.certificate_id
  const signing = s.csr || req.request_type === 'csr'
  // The authority reads as the mockup's text, and still opens the CA
  const caText = ca?.name ? <>{ca.name} <span className="muted">· {t('cas.tree.level', { level: ca.level })}</span></> : `#${caId}`
  return (
    <div className="module-detail">
      <Section title={t('approvals.work.detail.request')}>
        <Props items={[
          [t('approvals.work.detail.id'), <span className="mono">#{req.id}</span>],
          [t('common.type'), typeLabel(req, t)],
          [t('approvals.requester'), requesterOf(req, t)],
          [t('approvals.work.detail.submitted'), when(req.created_at)],
          pending && [t('approvals.work.detail.due'), when(requestDeadline(req))],
          [t('approvals.work.detail.state'), <Pill label={state.label} tone={state.tone} />],
          req.requester_comment && [t('approvals.work.detail.reason'), req.requester_comment],
          req.policy_name && [t('approvals.policy'), req.policy_name],
          (req.required_approvals || 1) > 1 && [t('approvals.work.detail.votes'),
            t('approvals.work.votes', { count: (req.approvals || []).filter((v) => v.action === 'approve').length, need: req.required_approvals })],
        ]} />
      </Section>
      <Section title={signing ? t('approvals.work.detail.csr') : t('approvals.work.detail.object')}>
        <Props items={[
          s.cn && [t('approvals.work.detail.subject'), req.request_type === 'csr' ? `CN=${s.cn}` : s.cn],
          caId && [t('approvals.work.detail.ca'), <button type="button" className="text-link" onClick={() => openEntity('ca', caId)}>{caText}</button>],
          s.validity_days && [t('approvals.work.detail.validity'), t('approvals.work.detail.days', { count: s.validity_days })],
          s.extra_san?.length > 0 && [t('approvals.work.detail.extraSan'),
            <>{s.extra_san.map((v, i) => <span key={i}>{i > 0 && <br />}{sanLine(v, t)}</span>)}</>],
          s.csr_id && [t('approvals.work.detail.csrId'), `#${s.csr_id}`],
          target && [t('approvals.certificateId'), <button type="button" className="text-link" onClick={() => openEntity('certificate', target)}>#{target}</button>],
          s.serial_number && [t('approvals.summarySerial'), <span className="mono">{s.serial_number}</span>],
          s.reason && [t('revocation.reasonLabel'), t(`revocation.reasons.${s.reason}`, s.reason)],
          s.invalidity_at && [t('approvals.summaryInvalidity'), formatDate(s.invalidity_at)],
          s.trigger === 'auto' && [t('approvals.summaryTrigger'), t('approvals.triggerScheduler')],
          s.protocol && [t('approvals.summaryProtocol'), `${s.protocol.toUpperCase()}${s.operation ? ` (${s.operation})` : ''}`],
          s.protocol && [t('approvals.summaryIdentity'), <span className="mono">{s.identity || '—'}</span>],
          s.extra_ekus?.length > 0 && [t('approvals.summaryExtraEkus'), <span className="mono">{s.extra_ekus.join(', ')}</span>],
        ]} />
      </Section>
      {s.csr && <Section title={t('approvals.summaryCsr')}><pre className="code-preview">{s.csr}</pre></Section>}
      {!pending && (
        <Section title={t('approvals.work.detail.decision')}>
          <Props items={[
            [t('approvals.work.detail.decision'), <Pill label={state.label} tone={state.tone} />],
            vote && [t('approvals.work.detail.by'), vote.username],
            req.resolved_at && [t('approvals.work.detail.on'), when(req.resolved_at)],
            [t('approvals.work.dialog.reason'), vote?.comment || <span className="muted">{t('approvals.work.detail.noReason')}</span>],
          ]} />
        </Section>
      )}
    </div>
  )
}

/** The mockup's journal(): what happened, its detail under it, who and when on the right. */
export function ApprovalLog({ req }) {
  const { t } = useTranslation()
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
    <RecordList empty={t('approvals.work.log.none')}>
      {entries.map((e, i) => (
        <RecordRow key={i} title={e.label} meta={e.meta || undefined}
          badge={<span className="rl-meta">{[e.actor, when(e.at)].filter(Boolean).join(' · ')}</span>} />
      ))}
    </RecordList>
  )
}

/** The two decision buttons of the mockup (decisionButtons()), named after the request when given. */
export function DecisionButtons({ onDecide, disabled, name }) {
  const { t } = useTranslation()
  return (
    <>
      <Btn icon="check" write disabled={disabled || undefined} data-decision="approve" onClick={() => onDecide('approve')}
        aria-label={name ? t('approvals.work.approveNamed', { name }) : undefined}>{t('approvals.work.approveAsk')}</Btn>
      <Btn tone="quiet" icon="block" write disabled={disabled || undefined} data-decision="refuse" onClick={() => onDecide('reject')}
        aria-label={name ? t('approvals.work.rejectNamed', { name }) : undefined}>{t('approvals.work.rejectAsk')}</Btn>
    </>
  )
}

/** The dock of the open request; onDecide(kind) asks for a decision on it. */
export function ApprovalDock({ req, section, onSection, onClose, onDecide }) {
  const { t } = useTranslation()
  const { canWrite } = usePermission()
  const title = requestTitle(req, t)
  const state = stateOf(req, t)
  const decidable = req.status === 'pending' && !isLapsed(req) && canWrite('approvals')
  return (
    <Dock label={t('atelier.detailOf', { name: t('common.approvals') })} tabsLabel={t('atelier.openItem')} activeKey={req.id}
      tabs={[{ key: req.id, title, icon: 'approve' }]} onClose={onClose}>
      <DockBody icon="approve" title={title} badge={<Pill label={state.label} tone={state.tone} />}
        actions={decidable && <DecisionButtons onDecide={onDecide} name={title} />}
        sections={[['request', t('approvals.work.sections.request')], ['log', t('approvals.work.sections.log')]]}
        section={section} onSection={onSection} sectionsLabel={t('atelier.sectionsOf', { name: title })}>
        {section === 'log' ? <ApprovalLog req={req} /> : <ApprovalRequestPanel req={req} />}
      </DockBody>
    </Dock>
  )
}
