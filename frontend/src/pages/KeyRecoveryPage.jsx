/**
 * Key recovery: dual-control private-key recovery (escrow). The mockup has no screen for it: the
 * page takes its work queue template, workView() and the moduleInspector() dock of the approvals.
 * Requests wait for an administrator's decision (another one than the requester while dual
 * control is on), then for their recovery as a PKCS#12; the closed ones are in the folded history.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Zone, PageHead, WorkView, Btn, Pill, RecordRow, LoadError, LoadCause, workSpot, focusWork } from '../components/atelier'
import { keyRecoveryService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { useLinkedId } from '../hooks/useLinkedId'
import { useDockParam, asId } from '../components/atelier/useDockParam'
import { stateLabel } from '../lib/stateLabel'
import { formatDate } from '../lib/utils'
import { compactAgo } from '../lib/relativeTime'
import { recoveryRights, recoveryState, recoveryGroups, recoveryName as nameOf } from './keyRecovery/recoveryRules'
import { useRecoveryActions } from './keyRecovery/useRecoveryActions'
import { KeyRecoveryDock, RecoveryButtons } from './keyRecovery/KeyRecoveryDetail'
const when = (d) => formatDate(d, { time: true })

const RECOVERY_SECTIONS = ['request', 'log']

export default function KeyRecoveryPage() {
  const { t } = useTranslation()
  const { showError, showInfo } = useNotification()
  const { hasPermission, username, userId } = usePermission()
  const spot = useRef(-1)
  // The open request and its section live in the URL (`item`, `section`); the work queue's ?request= opens it too
  const recDock = useDockParam({ sections: RECOVERY_SECTIONS, fallback: 'request', aliases: ['request'] })
  const openId = recDock.item == null ? null : asId(recDock.item)
  const { section, setSection } = recDock

  const [requests, setRequests] = useState([])
  const [dualControl, setDualControl] = useState(true)
  const [state, setState] = useState('loading')
  const [failure, setFailure] = useState(null)
  const [linked, setLinked] = useState(null)

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setState((s) => (s === 'ready' ? s : 'loading'))
    try {
      const res = await keyRecoveryService.list()
      const data = res?.data || res || {}
      setRequests(data.requests || [])
      setDualControl(data.dual_control !== false)
      setState('ready')
    } catch (e) {
      setFailure(e || null)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const onChange = (e) => { if (e.detail?.type === 'key_recovery') load({ quiet: true }) }
    window.addEventListener('ucm:data-changed', onChange)
    return () => window.removeEventListener('ucm:data-changed', onChange)
  }, [load])

  // /key-recovery?request=N shows that request, even past the 500 the list holds
  const linkedId = useLinkedId('request')
  useEffect(() => {
    if (!linkedId) return undefined
    let cancelled = false
    keyRecoveryService.get(linkedId)
      .then((res) => {
        if (cancelled) return
        const row = res?.data || res
        setLinked(row)
        if (row.status !== 'pending') {
          showInfo(t('overview.link.handled', { id: row.id, status: stateLabel(t, row.status) }))
        }
      })
      .catch((e) => {
        if (cancelled) return
        if (e?.status === 404) showInfo(t('overview.link.gone', { id: linkedId }))
        else showError(e?.message || t('keyRecovery.loadFailed'))
      })
    return () => { cancelled = true }
  }, [linkedId, showError, showInfo, t])

  // The linked request is shown even when the list does not hold it; the listed copy wins
  const all = useMemo(() => {
    const list = requests.map((r) => ({ ...r, dual_control: dualControl }))
    if (!linked || list.some((r) => r.id === linked.id)) return list
    return [{ ...linked, dual_control: dualControl }, ...list]
  }, [requests, linked, dualControl])

  const actions = useRecoveryActions({
    onDone: () => load({ quiet: true }),
    refocus: () => focusWork(spot.current),
  })
  const ask = (kind, reqs) => {
    spot.current = workSpot(reqs.map((r) => r.id))
    actions.open(kind, reqs)
  }
  const who = { hasPermission, username, userId, dualControl }
  const open = (req) => recDock.open(req.id)
  // An open request past the 500 the list holds (a reload) is read by id; one that no longer exists leaves the URL
  useEffect(() => {
    if (state !== 'ready' || openId == null || linkedId || requests.some((r) => r.id === openId) || linked?.id === openId) return undefined
    let cancelled = false
    keyRecoveryService.get(openId).then((res) => { if (!cancelled) setLinked(res?.data || res) }, () => { if (!cancelled) recDock.close() })
    return () => { cancelled = true }
  }, [state, openId, linkedId, requests, linked]) // eslint-disable-line react-hooks/exhaustive-deps
  const opened = all.find((r) => r.id === openId) || null

  const groups = recoveryGroups(all, t, dualControl).map((g) => {
    const approveSlot = g.requests.some((r) => recoveryRights(r, who).approve)
    return {
      ...g,
      items: g.requests.map((req) => {
        const at = req.status === 'approved' ? req.decided_at || req.requested_at : req.requested_at
        return {
          id: req.id,
          title: nameOf(req),
          kind: t('keyRecovery.work.kind'),
          facts: [
            t('keyRecovery.work.requestedBy', { user: req.requested_by, ago: compactAgo(req.requested_at, t) }),
            req.reason && t('keyRecovery.work.reason', { reason: req.reason }),
            req.status === 'approved' && req.decided_by && t('keyRecovery.decidedBy', { user: req.decided_by }),
          ].filter(Boolean),
          // No deadline: the date the request reached this step
          due: at,
          dueLabel: compactAgo(at, t),
          dueDate: when(at),
          tone: '',
          onOpen: () => open(req),
          // Only a request the user may decide on goes into a bulk decision
          selectable: recoveryRights(req, who).reject,
          // A row without Approuver… where its group has some keeps the button's place: the due dates line up
          actions: (disabled) => <RecoveryButtons req={req} who={who} disabled={disabled} slot={approveSlot} onAsk={(kind) => ask(kind, [req])} />,
        }
      }),
    }
  })

  const pendingById = new Map(all.filter((r) => r.status === 'pending').map((r) => [r.id, r]))
  const bulk = hasPermission('admin:key_recovery') ? (ids) => {
    const reqs = ids.map((id) => pendingById.get(id)).filter(Boolean)
    return (
      <>
        <Btn icon="check" write onClick={() => ask('approve', reqs)}>{t('keyRecovery.work.approveAsk')}</Btn>
        <Btn tone="quiet" icon="block" write onClick={() => ask('reject', reqs)}>{t('keyRecovery.work.rejectAsk')}</Btn>
      </>
    )
  } : undefined

  const closed = all.filter((r) => !['pending', 'approved'].includes(r.status))
  const open_ = all.filter((r) => ['pending', 'approved'].includes(r.status)).length

  const dock = opened && (
    <KeyRecoveryDock req={opened} section={section} onSection={setSection} onClose={recDock.close}
      onAsk={(kind) => ask(kind, [opened])} />
  )

  return (
    <Zone dock={dock} after={actions.dialog}>
      <PageHead title={t('keyRecovery.title')} total={state === 'ready' ? t('keyRecovery.work.total', { count: open_ }) : ''}
        intent={t('keyRecovery.work.intent')} />
      <WorkView
        state={state}
        error={(
          <LoadError id="key-recovery" title={t('keyRecovery.loadFailed')} onRetry={() => load()} journal={hasPermission('read:audit') && '/audit'}
            cause={failure && <LoadCause error={{ status: failure.status, request: failure.status && 'GET /api/v2/key-recovery', message: failure.message }} />} />
        )}
        hint={t(dualControl ? 'keyRecovery.work.hintDual' : 'keyRecovery.work.hint')}
        groups={groups}
        bulk={bulk}
        openedId={openId}
        empty={{ title: t('keyRecovery.empty'), text: t('keyRecovery.work.emptyText') }}
        history={{
          label: t('approvals.work.history'),
          count: closed.length,
          children: closed.map((req) => {
            const s = recoveryState(req, t)
            return (
              <RecordRow key={req.id}
                title={<button type="button" className="text-link" data-item={req.id} data-open={req.id} onClick={() => open(req)}>#{req.id} · {nameOf(req)}</button>}
                meta={[req.recovered_by || req.decided_by || req.requested_by, when(req.recovered_at || req.decided_at || req.requested_at), req.decision_note].filter(Boolean).join(' · ')}
                badge={<Pill label={s.label} tone={s.tone} />} />
            )
          }),
        }}
      />
    </Zone>
  )
}
