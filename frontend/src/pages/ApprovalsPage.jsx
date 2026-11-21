/**
 * Approvals: the mockup's approvals module, a workView() (the open requests grouped by their
 * deadline, decided one by one or together, the decided ones in the folded history) and its
 * moduleInspector() dock, over every source of requests (issue form, CSR signing, renewals,
 * revocations, ACME, EST, SCEP, WSTEP). A subject opens the request in the dock.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Zone, PageHead, WorkView, Btn, Pill, RecordRow, LoadError, LoadCause, workSpot, focusWork } from '../components/atelier'
import { approvalsService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { useLinkedId } from '../hooks/useLinkedId'
import { formatDate } from '../lib/utils'
import { stateLabel } from '../lib/stateLabel'
import {
  approvalGroups, requestTitle, subjectOf, requestKind, requestFacts, requestDeadline,
  stateOf, decisionMeta, loadCaIndex, isLapsed,
} from './approvals/approvalModel'
import { ApprovalDock, DecisionButtons } from './approvals/ApprovalDetail'
import { useApprovalDecision } from './approvals/useApprovalDecision'

// The decided requests the history shows, newest first
const HISTORY_SIZE = 100

export default function ApprovalsPage() {
  const { t } = useTranslation()
  const { showError, showInfo } = useNotification()
  const { canWrite, canRead, hasPermission } = usePermission()

  const [requests, setRequests] = useState([])
  const [state, setState] = useState('loading')
  const [failure, setFailure] = useState(null)
  const [linked, setLinked] = useState(null)
  const [caNames, setCaNames] = useState({})
  const [openId, setOpenId] = useState(null)
  const [section, setSection] = useState('request')
  const spot = useRef(-1)

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

  // A decision taken elsewhere reloads the queue
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
        setOpenId(res.data.id)
        setSection('request')
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
  }, [linkedId, showError, showInfo, t])

  // The linked request is shown even when the list does not hold it; the listed copy wins
  const all = useMemo(() => {
    if (!linked || requests.some((r) => r.id === linked.id)) return requests
    return [linked, ...requests]
  }, [requests, linked])
  const pending = all.filter((r) => r.status === 'pending' && !isLapsed(r))
  const decided = all.filter((r) => r.status !== 'pending' || isLapsed(r))
    .sort((a, b) => new Date(b.resolved_at || b.created_at) - new Date(a.resolved_at || a.created_at))
  const opened = all.find((r) => r.id === openId) || null

  // After a decision the focus goes to the action of the row now at the same place
  const decision = useApprovalDecision({
    onDone: () => load({ quiet: true }),
    refocus: () => focusWork(spot.current),
  })
  const ask = (kind, reqs) => {
    spot.current = workSpot(reqs.map((r) => r.id))
    decision.open(kind, reqs)
  }
  const mayDecide = canWrite('approvals')
  const open = (req) => {
    if (req.id !== openId) setSection('request')
    setOpenId(req.id)
  }

  const groups = approvalGroups(pending, t).map((g) => ({
    ...g,
    items: g.requests.map((req) => ({
      id: req.id,
      title: requestTitle(req, t),
      kind: requestKind(req, t),
      facts: requestFacts(req, t, { caName: caNames[String(req.request_summary?.ca_id)] }),
      due: requestDeadline(req),
      dueDate: formatDate(requestDeadline(req), { time: true }),
      onOpen: () => open(req),
      actions: mayDecide ? (disabled) => <DecisionButtons onDecide={(kind) => ask(kind, [req])} disabled={disabled} name={requestTitle(req, t)} /> : undefined,
    })),
  }))

  const byId = new Map(pending.map((r) => [r.id, r]))
  const bulk = mayDecide ? (ids) => <DecisionButtons onDecide={(kind) => ask(kind, ids.map((id) => byId.get(id)).filter(Boolean))} /> : undefined

  const dock = opened && (
    <ApprovalDock req={opened} section={section} onSection={setSection} onClose={() => setOpenId(null)}
      onDecide={(kind) => ask(kind, [opened])} />
  )

  return (
    <Zone dock={dock} after={decision.dialog}>
      <PageHead title={t('common.approvals')} total={state === 'ready' ? t('approvals.work.total', { count: pending.length }) : ''}
        intent={t('approvals.work.intent')} />
      <WorkView
        state={state}
        error={(
          <LoadError id="approvals" title={t('approvals.loadFailed')} onRetry={() => load()} journal={hasPermission('read:audit') && '/audit'}
            cause={failure && <LoadCause error={{ status: failure.status, request: failure.status && 'GET /api/v2/approvals', message: failure.message }} />} />
        )}
        hint={mayDecide ? t('approvals.work.hint') : t('approvals.work.hintRead')}
        groups={groups}
        bulk={bulk}
        openedId={openId}
        empty={{
          title: t('approvals.work.emptyTitle'),
          text: t('approvals.work.emptyText'),
          action: canRead('policies') && <Btn to="/policies" icon="policy" data-module="policies">{t('approvals.work.seePolicies')}</Btn>,
        }}
        history={{
          label: t('approvals.work.history'),
          count: decided.length,
          children: decided.slice(0, HISTORY_SIZE).map((req) => {
            const s = stateOf(req, t)
            return (
              <RecordRow key={req.id}
                title={<button type="button" className="text-link" data-item={req.id} data-open={req.id} onClick={() => open(req)}>#{req.id} · {subjectOf(req)}</button>}
                meta={decisionMeta(req) || formatDate(req.created_at, { time: true })}
                badge={<Pill label={s.label} tone={s.tone} />} />
            )
          }),
        }}
      />
    </Zone>
  )
}
