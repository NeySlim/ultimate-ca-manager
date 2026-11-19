/**
 * The latest ACME failure the work queue holds for a certificate: an order that ended
 * invalid, or a renewal its client could not complete, for one of its names. The queue
 * names an order by its identifiers, so the match is made on them.
 */
import { useEffect, useState } from 'react'
import { dashboardService } from '../../../services'
import { usePermission } from '../../../hooks'
import { extractCN } from '../../../lib/utils'

const KINDS_BY_SOURCE = {
  acme: ['acme_order_failed'],
  acme_client: ['acme_client_renewal_failed'],
  letsencrypt: ['acme_client_renewal_failed'],
}

const namesOf = (cert) => {
  const names = new Set()
  const add = (v) => { if (v) names.add(String(v).trim().toLowerCase()) }
  add(cert.common_name || cert.cn || extractCN(cert.subject))
  for (const entry of cert.extensions?.subject_alt_names?.entries || []) if (entry.type === 'DNS') add(entry.value)
  return names
}

/** The newest queue item of `kinds` whose identifiers name the certificate, or null. */
export function matchFailure(items, cert, kinds) {
  const names = namesOf(cert)
  const hits = (items || []).filter((item) => kinds.includes(item.kind)
    && String(item.label || '').split(',').some((id) => names.has(id.trim().toLowerCase())))
  if (!hits.length) return null
  const [last] = hits.sort((a, b) => new Date(b.due_at || 0) - new Date(a.due_at || 0))
  const href = typeof last.href_hint === 'string' && last.href_hint.startsWith('/') ? last.href_hint : null
  return { kind: last.kind, label: last.label || '', at: last.due_at || null, href }
}

export function useLastFailure(cert) {
  const { hasPermission } = usePermission()
  const [failure, setFailure] = useState(null)
  const kinds = KINDS_BY_SOURCE[cert?.source]
  const allowed = !!kinds && !cert.revoked && hasPermission('read:dashboard')
  const id = cert?.id

  useEffect(() => {
    setFailure(null)
    if (!allowed) return undefined
    let cancelled = false
    dashboardService.getQueue(kinds)
      .then((res) => { if (!cancelled) setFailure(matchFailure(res?.data?.items, cert, kinds)) })
      .catch(() => { /* no queue, no failure line */ })
    return () => { cancelled = true }
  }, [id, allowed]) // eslint-disable-line react-hooks/exhaustive-deps

  return failure
}
