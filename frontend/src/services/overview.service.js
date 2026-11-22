/**
 * Overview aggregates (GET /dashboard/queue, health, compliance, issuance, expirations, revocation).
 */
import { apiClient, buildQueryString } from './apiClient'
import { WATCH_KINDS } from '../lib/overviewQueue'

const key = (item) => `${item.kind}-${item.id}`

export const overviewService = {
  /**
   * The queue, critical first then by due date, at most `limit` rows; past the limit the interventions fill it, so the
   * rows only to watch that its counts name are asked apart and added after them.
   */
  async getQueue(limit = 100) {
    const res = await apiClient.get(`/dashboard/queue${buildQueryString({ limit })}`)
    const data = res?.data
    const items = Array.isArray(data?.items) ? data.items : null
    if (!items || typeof data.total !== 'number' || items.length >= data.total) return res
    const counted = WATCH_KINDS.reduce((sum, kind) => sum + (Number(data.counts?.[kind]) || 0), 0)
    if (counted <= items.filter((i) => WATCH_KINDS.includes(i.kind)).length) return res
    const watch = await apiClient.get(`/dashboard/queue${buildQueryString({ limit, kind: WATCH_KINDS })}`)
    const listed = new Set(items.map(key))
    const more = (Array.isArray(watch?.data?.items) ? watch.data.items : []).filter((i) => !listed.has(key(i)))
    return { ...res, data: { ...data, items: [...items, ...more] } }
  },
  getHealth(days = 7) {
    return apiClient.get(`/dashboard/health${buildQueryString({ days })}`)
  },
  getCompliance() {
    return apiClient.get('/dashboard/compliance')
  },
  getIssuance(days = 30) {
    return apiClient.get(`/dashboard/issuance${buildQueryString({ days })}`)
  },
  /** Expirations per UTC day from today over `days` (1-365): total, manual, automatic, signers, CAs. */
  getExpirations(days = 90) {
    return apiClient.get(`/dashboard/expirations${buildQueryString({ days })}`)
  },
  /** Active CAs by CRL state, and at most `limit` CAs with a distribution point, the ones to publish first. */
  getRevocation(limit = 10) {
    return apiClient.get(`/dashboard/revocation${buildQueryString({ limit })}`)
  },
  /**
   * The certificate list query for the expirations of the UTC days `from` to `to` included (YYYY-MM-DD), on the
   * population of `filter_hint`: the list counts what the days of /dashboard/expirations count.
   */
  expirationQuery(filterHint, from, to = from) {
    const next = new Date(`${to}T00:00:00Z`)
    next.setUTCDate(next.getUTCDate() + 1)
    return { status: filterHint?.status ?? ['valid', 'expiring'], expires_from: from, expires_to: next.toISOString().slice(0, 10) }
  },
}
