/**
 * The authority and HSM tiles of the overview (maquette-3), composed from GET /cas, /crl,
 * /hsm/providers and the per-CA series of /dashboard/issuance (no request here).
 */
import { daysUntil, elapsedPercent } from './overviewTime'
import { nameOf } from './overviewHierarchy'

export const TILE_COUNT = 6
// The validity gauge turns amber in its last third; an authority this close to its end is said
const LATE_SHARE = 67
const EXPIRY_WARN_DAYS = 90
const ACTIVITY_DAYS = 7
const RANK = { bad: 0, warn: 1, good: 2, muted: 3 }
const DAY = 86400000
const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0)

/** The CRL of an authority: off (no distribution point), missing, stale or current with its next update. */
function crlOf(ca, crls, now) {
  if (!ca.cdp_enabled) return { state: 'off' }
  if (!crls) return { state: 'unknown' }
  const crl = crls.get(ca.id)
  if (!crl) return { state: 'missing' }
  const next = Date.parse(crl.next_update)
  if (crl.is_stale || (Number.isFinite(next) && next <= now)) return { state: 'stale', next_update: crl.next_update }
  return { state: 'current', next_update: crl.next_update }
}

/** The state an authority's badge says, worst first: its tone, its i18n key and the count it needs. */
function stateOf(ca, crl, now) {
  const status = String(ca.status || 'active').toLowerCase()
  const left = daysUntil(ca.valid_to, now)
  if (status === 'revoked' || ca.revoked) return { tone: 'bad', key: 'revoked' }
  if (left !== null && left <= 0) return { tone: 'bad', key: 'expired' }
  if (crl.state === 'stale') return { tone: 'bad', key: 'crlStale' }
  if (crl.state === 'missing') return { tone: 'bad', key: 'crlMissing' }
  if (left !== null && left <= EXPIRY_WARN_DAYS) return { tone: 'warn', key: 'expiresIn', count: left }
  if (status === 'pending' || ca.pending) return { tone: 'warn', key: 'pending' }
  return { tone: 'good', key: ca.offline ? 'offline' : 'inService' }
}

function hsmState(p) {
  const status = String(p.status || 'unknown').toLowerCase()
  if (status === 'connected') return { tone: 'good', key: 'reachable' }
  if (status === 'error') return { tone: 'bad', key: 'hsmError' }
  if (status === 'disconnected') return { tone: 'muted', key: 'disconnected' }
  return { tone: 'muted', key: p.last_tested_at ? 'unknown' : 'untested' }
}

/**
 * At most TILE_COUNT tiles: the authorities in alert first, then the most active, then by name; the
 * HSM modules after them (two places, more when there are fewer authorities), modules in error first.
 */
export function chooseTiles({ cas, crls, providers, issuance, now = Date.now() }) {
  const crlMap = Array.isArray(crls) ? new Map(crls.filter((c) => !c.is_delta).map((c) => [c.ca_id, c])) : null
  const series = new Map((Array.isArray(issuance?.by_ca) ? issuance.by_ca : []).map((e) => [e.caref, e]))
  const caTiles = (Array.isArray(cas) ? cas : []).map((ca) => {
    const crl = crlOf(ca, crlMap, now)
    const periods = series.get(ca.refid)?.periods
    const activity = Array.isArray(periods) ? periods.slice(-ACTIVITY_DAYS).map((p) => n(p.issued) + n(p.renewed)) : null
    const elapsed = elapsedPercent(ca.valid_from, ca.valid_to, now)
    return {
      kind: 'ca', id: ca.id, name: nameOf(ca), ...stateOf(ca, crl, now), crl,
      algo: ca.key_type || ca.key_algorithm || null,
      guard: ca.uses_hsm ? { hsm: ca.hsm_provider_name || ca.hsm_provider_type || '' } : { software: Boolean(ca.has_private_key) },
      elapsed, late: elapsed !== null && elapsed >= LATE_SHARE, validTo: ca.valid_to,
      ocsp: Boolean(ca.ocsp_enabled), activity, issued: activity ? activity.reduce((a, b) => a + b, 0) : 0,
    }
  }).sort((a, b) => RANK[a.tone] - RANK[b.tone] || b.issued - a.issued || a.name.localeCompare(b.name))

  const served = new Map()
  for (const ca of Array.isArray(cas) ? cas : []) if (ca.hsm_provider_id) served.set(ca.hsm_provider_id, (served.get(ca.hsm_provider_id) || 0) + 1)
  const hsmTiles = (Array.isArray(providers) ? providers : []).map((p) => ({
    kind: 'hsm', id: p.id, name: p.name || `#${p.id}`, ...hsmState(p), type: p.provider_type || p.type || null,
    certification: p.certification || null, keys: n(p.key_count), cas: served.get(p.id) || 0, tested: p.last_tested_at || null,
  })).sort((a, b) => RANK[a.tone] - RANK[b.tone] || b.cas - a.cas || a.name.localeCompare(b.name))

  const hsmShown = Math.min(hsmTiles.length, Math.max(2, TILE_COUNT - caTiles.length))
  return {
    tiles: [...caTiles.slice(0, TILE_COUNT - hsmShown), ...hsmTiles.slice(0, hsmShown)],
    authorities: caTiles.length, modules: hsmTiles.length,
  }
}

/** Whole days since a past date, one at least (« CRL échue depuis 192 j »). */
export const daysSince = (date, now = Date.now()) => Math.max(1, Math.floor((now - Date.parse(date)) / DAY))

/** The three parts of the active authorities, in the bar's order. */
export function coverParts(data) {
  return [
    { key: 'current', value: n(data?.current), color: 'var(--good)' },
    { key: 'toPublish', value: n(data?.stale) + n(data?.missing), color: 'var(--bad)' },
    { key: 'noCdp', value: n(data?.no_cdp), color: 'var(--s0)' },
  ]
}

