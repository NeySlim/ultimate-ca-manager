/**
 * KeyRecoveryPage: dual-control private-key recovery (escrow) as a work queue.
 * Requests wait for an administrator's decision (another one than the requester
 * while dual control is on), then for their recovery as a PKCS#12; the closed
 * ones are in the folded history. A subject opens the request in the inspector.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Prohibit, DownloadSimple } from '@phosphor-icons/react'
import { ResponsiveLayout } from '../components'
import { StatusPill } from '../components/list'
import { WorkQueue, WorkButton, WorkRecord, WorkRecords, workSpot, focusWork, loadCause } from '../components/work'
import { keyRecoveryService } from '../services'
import { useNotification, useInspector } from '../contexts'
import { usePermission } from '../hooks'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { useLinkedId } from '../hooks/useLinkedId'
import { stateLabel } from '../lib/stateLabel'
import { formatDate } from '../lib/utils'
import { compactAgo } from '../lib/relativeTime'
import { recoveryRights, recoveryState, recoveryGroups } from './keyRecovery/recoveryRules'
import { useRecoveryActions } from './keyRecovery/useRecoveryActions'

const nameOf = (r) => r.cert_cn || r.cert_refid || `#${r.cert_id}`
const when = (d) => formatDate(d, { time: true })

export default function KeyRecoveryPage() {
  const { t } = useTranslation()
  const { showError, showInfo } = useNotification()
  const { hasPermission, username } = usePermission()
  const inspector = useInspector()
  const openEntity = useOpenEntity()
  const root = useRef(null)
  const spot = useRef(-1)

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
        openEntity('key_recovery', row.id, { data: row })
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
  }, [linkedId, showError, showInfo, t]) // eslint-disable-line react-hooks/exhaustive-deps

  // The linked request is shown even when the list does not hold it; the listed copy wins
  const all = useMemo(() => {
    const list = requests.map((r) => ({ ...r, dual_control: dualControl }))
    if (!linked || list.some((r) => r.id === linked.id)) return list
    return [{ ...linked, dual_control: dualControl }, ...list]
  }, [requests, linked, dualControl])

  const actions = useRecoveryActions({
    onDone: () => load({ quiet: true }),
    refocus: () => focusWork(root.current, spot.current),
  })
  const ask = (kind, reqs) => {
    spot.current = workSpot(root.current, reqs.map((r) => r.id))
    actions.open(kind, reqs)
  }
  const who = { hasPermission, username, dualControl }
  const open = (req) => openEntity('key_recovery', req.id, { data: req })
  const activeKey = inspector?.activeKey || ''
  const openedId = activeKey.startsWith('key_recovery:') ? Number(activeKey.slice(13)) : linked?.id

  // A row without Approve… where its group has some keeps the button's place: the due dates line up
  const rowActions = (req, approveSlot) => (disabled) => {
    const rights = recoveryRights(req, who)
    const name = nameOf(req)
    return (
      <>
        {rights.approve ? (
          <WorkButton icon={Check} disabled={disabled} onClick={() => ask('approve', [req])}
            aria-label={t('keyRecovery.work.approveNamed', { name })}>{t('keyRecovery.work.approveAsk')}</WorkButton>
        ) : approveSlot && (
          <span className="wk-btn is-placeholder" aria-hidden="true"><Check aria-hidden="true" />{t('keyRecovery.work.approveAsk')}</span>
        )}
        {rights.reject && (
          <WorkButton quiet icon={Prohibit} disabled={disabled} onClick={() => ask('reject', [req])}
            aria-label={t('keyRecovery.work.rejectNamed', { name })}>{t('keyRecovery.work.rejectAsk')}</WorkButton>
        )}
        {rights.recover && (
          <WorkButton icon={DownloadSimple} disabled={disabled} onClick={() => ask('recover', [req])}
            aria-label={t('keyRecovery.work.recoverNamed', { name })}>{t('keyRecovery.work.recoverAsk')}</WorkButton>
        )}
      </>
    )
  }

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
          actions: rowActions(req, approveSlot),
        }
      }),
    }
  })

  const pendingById = new Map(all.filter((r) => r.status === 'pending').map((r) => [r.id, r]))
  const bulkActions = hasPermission('admin:key_recovery') ? (ids) => {
    const reqs = ids.map((id) => pendingById.get(id)).filter(Boolean)
    return (
      <>
        <WorkButton icon={Check} onClick={() => ask('approve', reqs)}>{t('keyRecovery.work.approveAsk')}</WorkButton>
        <WorkButton quiet icon={Prohibit} onClick={() => ask('reject', reqs)}>{t('keyRecovery.work.rejectAsk')}</WorkButton>
      </>
    )
  } : undefined

  const closed = all.filter((r) => !['pending', 'approved'].includes(r.status))
  const open_ = all.filter((r) => ['pending', 'approved'].includes(r.status)).length

  return (
    <>
      <ResponsiveLayout
        className="wk-page"
        title={t('keyRecovery.title')}
        total={state === 'ready' ? t('keyRecovery.work.total', { count: open_ }) : ''}
        intent={t('keyRecovery.work.intent')}
        helpPageKey="keyRecovery"
      >
        <WorkQueue
          rootRef={root}
          label={t('keyRecovery.title')}
          state={state}
          error={{ title: t('keyRecovery.loadFailed'), cause: loadCause(failure, t), onRetry: () => load(), journal: hasPermission('read:audit') && '/audit' }}
          hint={t(dualControl ? 'keyRecovery.work.hintDual' : 'keyRecovery.work.hint')}
          groups={groups}
          bulkActions={bulkActions}
          openedId={openedId}
          empty={{ title: t('keyRecovery.empty'), text: t('keyRecovery.work.emptyText') }}
          history={{
            label: t('approvals.work.history'),
            count: closed.length,
            children: (
              <WorkRecords empty={t('work.historyEmpty')}>
                {closed.map((req) => (
                  <WorkRecord key={req.id}
                    title={<button type="button" className="wk-subject" onClick={() => open(req)}>#{req.id} · <span>{nameOf(req)}</span></button>}
                    meta={[req.recovered_by || req.decided_by || req.requested_by, when(req.recovered_at || req.decided_at || req.requested_at), req.decision_note].filter(Boolean).join(' · ')}
                    badge={<StatusPill {...recoveryState(req, t)} />} />
                ))}
              </WorkRecords>
            ),
          }}
        />
      </ResponsiveLayout>
      {actions.dialog}
    </>
  )
}
