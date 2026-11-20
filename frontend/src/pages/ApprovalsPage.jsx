/**
 * ApprovalsPage: the open approval requests of every source (issue form, CSR
 * signing, renewals, revocations, ACME, EST, SCEP, WSTEP) as a work queue grouped
 * by deadline, approved or rejected one by one or together; the decided ones in
 * the folded history. A subject opens the request in the inspector.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Check, Prohibit } from '@phosphor-icons/react'
import { ResponsiveLayout } from '../components'
import { StatusPill } from '../components/list'
import { WorkQueue, WorkButton, WorkRecord, WorkRecords, workSpot, focusWork, loadCause, PolicyIcon } from '../components/work'
import { approvalsService } from '../services'
import { useNotification, useInspector } from '../contexts'
import { usePermission } from '../hooks'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { useLinkedId } from '../hooks/useLinkedId'
import { formatDate } from '../lib/utils'
import { stateLabel } from '../lib/stateLabel'
import {
  approvalGroups, requestTitle, typeLabel, subjectOf, requestKind, requestFacts, requestDeadline,
  stateOf, decisionMeta, loadCaIndex,
} from './approvals/approvalModel'
import { useApprovalDecision } from './approvals/useApprovalDecision'

// The decided requests the history shows, newest first
const HISTORY_SIZE = 100

export default function ApprovalsPage() {
  const { t } = useTranslation()
  const { showError, showInfo } = useNotification()
  const { canWrite, canRead, hasPermission } = usePermission()
  const inspector = useInspector()
  const openEntity = useOpenEntity()
  const root = useRef(null)
  const spot = useRef(-1)

  const [requests, setRequests] = useState([])
  const [state, setState] = useState('loading')
  const [failure, setFailure] = useState(null)
  const [linked, setLinked] = useState(null)
  const [caNames, setCaNames] = useState({})

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setState((s) => (s === 'ready' ? s : 'loading'))
    try {
      const res = await approvalsService.list('all')
      setRequests(Array.isArray(res?.data) ? res.data : [])
      setState('ready')
    } catch (err) {
      setFailure(err || null)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  // A decision taken in the inspector or elsewhere reloads the queue
  useEffect(() => {
    const onChange = (e) => { if (e.detail?.type === 'approval') load({ quiet: true }) }
    window.addEventListener('ucm:data-changed', onChange)
    return () => window.removeEventListener('ucm:data-changed', onChange)
  }, [load])

  // Authority names of the facts line, for a reader of the CAs
  const needCas = canRead('cas') && requests.some((r) => r.status === 'pending' && r.request_summary?.ca_id)
  useEffect(() => {
    if (!needCas) return undefined
    let cancelled = false
    loadCaIndex().then((index) => {
      if (!cancelled) setCaNames(Object.fromEntries([...index].map(([id, ca]) => [id, ca.name])))
    })
    return () => { cancelled = true }
  }, [needCas])

  // /approvals?request=N (work queue) and ?id=N (e-mails already sent) open that request
  const linkedId = useLinkedId('request', 'id')
  useEffect(() => {
    if (!linkedId) return undefined
    let cancelled = false
    approvalsService.getById(linkedId)
      .then((res) => {
        if (cancelled || !res?.data) return
        setLinked(res.data)
        openEntity('approval', res.data.id, { data: res.data })
        if (res.data.status !== 'pending') {
          showInfo(t('overview.link.handled', { id: res.data.id, status: stateLabel(t, res.data.status) }))
        }
      })
      .catch((err) => {
        if (cancelled) return
        if (err?.status === 404) showInfo(t('overview.link.gone', { id: linkedId }))
        else showError(t('approvals.loadFailed'))
      })
    return () => { cancelled = true }
  }, [linkedId, showError, showInfo, t]) // eslint-disable-line react-hooks/exhaustive-deps

  // The linked request is shown even when the list does not hold it; the listed copy wins
  const all = useMemo(() => {
    if (!linked || requests.some((r) => r.id === linked.id)) return requests
    return [linked, ...requests]
  }, [requests, linked])
  const pending = all.filter((r) => r.status === 'pending')
  const decided = all.filter((r) => r.status !== 'pending')
    .sort((a, b) => new Date(b.resolved_at || b.created_at) - new Date(a.resolved_at || a.created_at))

  // After a decision the focus goes to the action of the row now at the same place
  const decision = useApprovalDecision({
    onDone: () => load({ quiet: true }),
    refocus: () => focusWork(root.current, spot.current),
  })
  const ask = (kind, reqs) => {
    spot.current = workSpot(root.current, reqs.map((r) => r.id))
    decision.open(kind, reqs)
  }
  const mayDecide = canWrite('approvals')
  const open = (req) => openEntity('approval', req.id, { data: req })
  const activeKey = inspector?.activeKey || ''
  const openedId = activeKey.startsWith('approval:') ? Number(activeKey.slice(9)) : linked?.id

  const title = (req) => <>{typeLabel(req, t)}{t('work.sep')}<span>{subjectOf(req)}</span></>
  const decisionButtons = (reqs, disabled, name) => (
    <>
      <WorkButton icon={Check} disabled={disabled} onClick={() => ask('approve', reqs)}
        aria-label={name ? t('approvals.work.approveNamed', { name }) : undefined}>{t('approvals.work.approveAsk')}</WorkButton>
      <WorkButton quiet icon={Prohibit} disabled={disabled} onClick={() => ask('reject', reqs)}
        aria-label={name ? t('approvals.work.rejectNamed', { name }) : undefined}>{t('approvals.work.rejectAsk')}</WorkButton>
    </>
  )

  const groups = approvalGroups(pending, t).map((g) => ({
    ...g,
    items: g.requests.map((req) => ({
      id: req.id,
      title: requestTitle(req, t),
      titleNode: title(req),
      kind: requestKind(req, t),
      facts: requestFacts(req, t, { caName: caNames[String(req.request_summary?.ca_id)] }),
      due: requestDeadline(req),
      dueDate: formatDate(requestDeadline(req), { time: true }),
      onOpen: () => open(req),
      actions: mayDecide ? (disabled) => decisionButtons([req], disabled, requestTitle(req, t)) : undefined,
    })),
  }))

  const byId = new Map(pending.map((r) => [r.id, r]))
  const bulkActions = mayDecide ? (ids) => decisionButtons(ids.map((id) => byId.get(id)).filter(Boolean), false) : undefined

  const policiesLink = canRead('policies') && (
    <Link className="wk-btn" to="/policies"><PolicyIcon aria-hidden="true" />{t('approvals.work.seePolicies')}</Link>
  )

  return (
    <>
      <ResponsiveLayout
        className="wk-page"
        title={t('common.approvals')}
        total={state === 'ready' ? t('approvals.work.total', { count: pending.length }) : ''}
        intent={t('approvals.work.intent')}
        helpPageKey="approvals"
      >
        <WorkQueue
          rootRef={root}
          label={t('common.approvals')}
          state={state}
          error={{ title: t('approvals.loadFailed'), cause: loadCause(failure, t), onRetry: () => load(), journal: hasPermission('read:audit') && '/audit' }}
          hint={mayDecide ? t('approvals.work.hint') : t('approvals.work.hintRead')}
          groups={groups}
          bulkActions={bulkActions}
          openedId={openedId}
          empty={{ title: t('approvals.work.emptyTitle'), text: t('approvals.work.emptyText'), action: policiesLink }}
          history={{
            label: t('approvals.work.history'),
            count: decided.length,
            children: (
              <WorkRecords empty={t('work.historyEmpty')}>
                {decided.slice(0, HISTORY_SIZE).map((req) => (
                  <WorkRecord key={req.id}
                    title={<button type="button" className="wk-subject" onClick={() => open(req)}>#{req.id} · <span>{subjectOf(req)}</span></button>}
                    meta={decisionMeta(req) || formatDate(req.created_at, { time: true })}
                    badge={<StatusPill {...stateOf(req, t)} />} />
                ))}
              </WorkRecords>
            ),
          }}
        />
      </ResponsiveLayout>
      {decision.dialog}
    </>
  )
}
