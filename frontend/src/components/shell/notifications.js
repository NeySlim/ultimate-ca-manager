/**
 * Bell items, derived from what the API returns: the work queue (critical items and
 * approvals; needs read:dashboard) and notable journal events (needs read:audit).
 * A source the user has no right on is not asked and shows nothing, not an error.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { dashboardService } from '../../services/dashboard.service'
import auditService from '../../services/audit.service'
import { useWebSocket } from '../../hooks/useWebSocket'
import { getPreferences, subscribePreferences, persistPreference } from '../../stores/userPreferencesStore'

export const BELL_KINDS = ['acme_order_failed', 'acme_client_renewal_failed', 'approval_pending', 'crl_due',
  'crl_missing', 'manual_renewal_due', 'auto_renewal_blocked', 'ca_expiring']
// Journal events worth a notification: a revoked session, a failed scheduled backup.
// Failures are asked for on their own so successful runs cannot push them out of the page.
const SESSION_ACTIONS = ['session_revoke', 'session_revoke_all']
const FAILURE_ACTIONS = ['system_backup']
const MAX_MARKS = 200
const REFRESH_DELAY_MS = 1500

const keyOf = (prefix, id) => `${prefix}:${id}`.replace(/[^A-Za-z0-9_.:-]/g, '_').slice(0, 120)

export function queueItems(data) {
  const rows = Array.isArray(data?.items) ? data.items : []
  return rows
    .filter(i => i && (i.tier === 'critical' || i.kind === 'approval_pending'))
    .map(i => ({
      key: keyOf(i.kind, i.id), source: 'queue', kind: i.kind, tier: i.tier, title: i.label || '',
      at: i.due_at || null, href: typeof i.href_hint === 'string' && i.href_hint.startsWith('/') ? i.href_hint : null,
    }))
}

export function auditItems(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(e => e && (e.action.startsWith('session_') || e.success === false))
    .map(e => ({
      key: keyOf('audit', e.id), source: 'audit', kind: e.action, tier: e.success === false ? 'critical' : 'warning',
      title: e.resource_name || e.username || '', at: e.timestamp || null,
      href: `/audit`,
    }))
}

function useReadMarks() {
  const [marks, setMarks] = useState(() => getPreferences().notifications_read || [])
  useEffect(() => subscribePreferences(p => setMarks(Array.isArray(p.notifications_read) ? p.notifications_read : [])), [])
  return marks
}

export function useNotifications(can) {
  const canQueue = !!can?.hasPermission?.('read:dashboard')
  const canAudit = !!can?.hasPermission?.('read:audit')
  const { lastEvent } = useWebSocket()
  const [parts, setParts] = useState({ queue: [], audit: [], failures: [] })
  const marks = useReadMarks()
  const alive = useRef(true)

  const refresh = useCallback(async () => {
    const [q, a, f] = await Promise.allSettled([
      canQueue ? dashboardService.getQueue(BELL_KINDS) : Promise.resolve(null),
      canAudit ? auditService.getLogs({ action: SESSION_ACTIONS, per_page: 20 }) : Promise.resolve(null),
      canAudit ? auditService.getLogs({ action: FAILURE_ACTIONS, success: false, per_page: 20 }) : Promise.resolve(null),
    ])
    if (!alive.current) return
    // A transient failure keeps what was shown; a refused call (rights changed) empties the source
    const next = (res, prev, make) => {
      if (res.status === 'fulfilled') return res.value ? make(res.value) : []
      const status = res.reason?.status
      return status === 401 || status === 403 ? [] : prev
    }
    setParts(p => ({
      queue: next(q, p.queue, v => queueItems(v.data ?? v)),
      audit: next(a, p.audit, v => auditItems(v.data ?? v)),
      failures: next(f, p.failures, v => auditItems(v.data ?? v)),
    }))
  }, [canQueue, canAudit])

  useEffect(() => {
    alive.current = true
    refresh()
    return () => { alive.current = false }
  }, [refresh])

  // Real-time events refresh the list once the burst has passed
  useEffect(() => {
    if (!lastEvent) return undefined
    const timer = setTimeout(refresh, REFRESH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [lastEvent, refresh])

  const items = [...parts.queue, ...[...parts.audit, ...parts.failures].sort((x, y) => (y.at || '').localeCompare(x.at || ''))]
    .filter((item, i, all) => all.findIndex(o => o.key === item.key) === i)
    .map(item => ({ ...item, unread: !marks.includes(item.key) }))
  const unread = items.filter(i => i.unread).length

  // Marks of items that left their source are dropped, and the list stays bounded
  const writeMarks = (keys) => {
    const present = new Set(items.map(i => i.key))
    persistPreference('notifications_read', keys.filter(k => present.has(k)).slice(-MAX_MARKS))
  }
  const markRead = (key) => { if (!marks.includes(key)) writeMarks([...marks, key]) }
  const markAllRead = () => writeMarks([...new Set([...marks, ...items.map(i => i.key)])])

  return { items, unread, refresh, markRead, markAllRead }
}
