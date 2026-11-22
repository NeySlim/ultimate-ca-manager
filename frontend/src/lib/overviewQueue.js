/** Work queue of the overview: the filter groups, and what only needs watching. */

/** The filter chips: every kind of the queue belongs to one group. */
export const QUEUE_GROUPS = {
  renew: ['manual_renewal_due', 'client_renewal_overdue', 'auto_renewal_blocked', 'renewal_declined'],
  acme: ['acme_order_failed', 'acme_client_renewal_failed'],
  request: ['approval_pending', 'scep_request_pending', 'key_recovery_pending'],
  crl: ['crl_due', 'crl_missing'],
  ca: ['ca_expiring', 'truststore_expiring'],
  deploy: ['deploy_binding_left_behind', 'https_binding_left_behind'],
}
export const GROUP_OF = Object.fromEntries(
  Object.entries(QUEUE_GROUPS).flatMap(([group, kinds]) => kinds.map((kind) => [kind, group])))

// Nothing to do today: the client renews on its own, or the expiry is still far
export const WATCH_KINDS = ['client_renewal_overdue', 'ca_expiring', 'truststore_expiring']
/** Kinds whose date is when it happened, not a deadline. */
export const SINCE_KINDS = ['acme_order_failed', 'acme_client_renewal_failed', 'scep_request_pending', 'key_recovery_pending']

/** Kinds the server dates with the time of the request: there is no deadline to show. */
export const UNDATED_KINDS = ['crl_missing']

/** A row to watch is never a critical one: those stay among the interventions. */
export const isWatch = (item) => WATCH_KINDS.includes(item.kind) && item.tier !== 'critical'

/** Interventions and rows to watch in the whole queue, from the totals per kind and the critical rows loaded. */
export function queueSplit(data) {
  const counts = data?.counts && typeof data.counts === 'object' ? data.counts : {}
  const items = Array.isArray(data?.items) ? data.items : []
  const total = typeof data?.total === 'number' ? data.total : null
  const ofKind = WATCH_KINDS.reduce((sum, kind) => sum + (Number(counts[kind]) || 0), 0)
  const critical = items.filter((i) => WATCH_KINDS.includes(i.kind) && i.tier === 'critical').length
  const watch = Math.max(0, ofKind - critical)
  return { total, watch, act: total === null ? null : Math.max(0, total - watch) }
}

export const DAY_MS = 86400000
// The countdown bar measures what is left of the last 30 days before a deadline still to come
export const COUNTDOWN_DAYS = 30

/** Share of the countdown left (1 a month ahead or more, 0 at the deadline); null once it is past. */
export function countdownShare(at, now = Date.now()) {
  if (!Number.isFinite(at) || at <= now) return null
  return Math.min(1, (at - now) / (COUNTDOWN_DAYS * DAY_MS))
}

