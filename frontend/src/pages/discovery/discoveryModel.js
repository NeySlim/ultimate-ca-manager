/**
 * What the discovery page reads off the server's scan profiles, runs and discovered
 * certificates: the mockup's « analyses » (a profile and its last run), their states, and the
 * checks a target passes before it is sent.
 */
import { useTranslation } from 'react-i18next'
import { formatDate } from '../../lib/utils'

const when = (d) => (d ? formatDate(d, { time: true }) : '—')

const listOf = (v, fallback) => {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v) {
    try { const parsed = JSON.parse(v); if (Array.isArray(parsed)) return parsed } catch { /* comma list */ }
    return v.split(',').map((s) => s.trim()).filter(Boolean)
  }
  return fallback
}
export const targetsOf = (p) => listOf(p.targets_list || p.targets, [])
export const portsOf = (p) => listOf(p.ports_list || p.ports, [443]).map(String)

/** The newest run of each profile, by profile id. */
export function lastRuns(runs) {
  const last = new Map()
  for (const r of runs) {
    if (r.scan_profile_id == null) continue
    const seen = last.get(r.scan_profile_id)
    if (!seen || new Date(r.started_at) > new Date(seen.started_at)) last.set(r.scan_profile_id, r)
  }
  return last
}

export const SCAN_TONES = { running: 'warn', done: 'good', failed: 'bad', scheduled: 'muted', never: 'muted' }

/** The mockup's state of an analysis: its last run, else whether one is planned. */
export function scanState(profile, run) {
  if (run?.status === 'running') return 'running'
  if (run?.status === 'completed') return 'done'
  if (run) return 'failed'
  return profile.schedule_enabled ? 'scheduled' : 'never'
}

export const RUN_TONES = { running: 'warn', completed: 'good', failed: 'bad' }
export const runState = (run) => (RUN_TONES[run.status] ? run.status : 'failed')

export const FOUND_TONES = { managed: 'good', unmanaged: 'warn', error: 'bad' }
export const foundState = (c) => (FOUND_TONES[c.status] ? c.status : 'error')

export const SCHEDULES = [0, 60, 360, 720, 1440, 10080]
export const PORT_PRESETS = [
  { id: 'https', ports: ['443'] },
  { id: 'alt', ports: ['443', '8443'] },
  { id: 'common', ports: ['443', '8443', '8080', '636', '993', '995', '465', '587'] },
]

// The scanner expands an IPv4 range into its hosts, up to this many; it does not expand IPv6 ranges
export const MAX_RANGE_HOSTS = 65536
const TARGET_RE = /^[a-zA-Z0-9._:\-[\]/]+$/

/**
 * Why a target is not sent, or null: a DNS wildcard and an IPv6 range name no host the scanner
 * can reach, and an IPv4 range past the scanner's cap is refused by it.
 */
export function targetProblem(target) {
  if (target.includes('*')) return 'wildcard'
  if (!TARGET_RE.test(target)) return 'format'
  const slash = target.indexOf('/')
  if (slash < 0) return null
  if (target.includes(':')) return 'ipv6Range'
  const bits = Number(target.slice(slash + 1))
  if (!/^\d{1,2}$/.test(target.slice(slash + 1)) || bits > 32) return 'format'
  const hosts = 2 ** (32 - bits)
  return (hosts > 2 ? hosts - 2 : hosts) > MAX_RANGE_HOSTS ? 'tooWide' : null
}

/** One target per line, or separated by commas or spaces. */
export const splitList = (text) => (text || '').split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean)

export const validPorts = (text) => splitList(text).map(Number).filter((n) => Number.isInteger(n) && n > 0 && n <= 65535)

export function durationLabel(seconds) {
  if (seconds == null) return null
  const s = Math.round(seconds)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

/** First part of a distinguished name, CN first, as the list names a certificate. */
export function cnOf(dn) {
  if (!dn) return ''
  const m = /(?:^|,\s*)CN=([^,]+)/i.exec(dn)
  return m ? m[1].trim() : ''
}

/** The parts of a distinguished name, in order: [[key, value], …]. */
export function dnParts(dn) {
  const parts = []
  if (!dn) return parts
  const re = /([\w.]+)=((?:\\,|[^,])*)/g
  let m
  while ((m = re.exec(dn)) !== null) parts.push([m[1].trim(), m[2].trim()])
  return parts
}

/** A troubleshooting hint for a scan error, as an i18n key, or null. */
export function errorHint(error) {
  const e = (error || '').toLowerCase()
  if (!e) return null
  if (e.includes('unrecognized_name') || e.includes('sni')) return 'discovery.errorHintSni'
  if (e.includes('connection refused') || e.includes('errno 111')) return 'discovery.errorHintRefused'
  if (e.includes('timed out') || e.includes('errno 110')) return 'discovery.errorHintTimeout'
  if (e.includes('no route') || e.includes('errno 113') || e.includes('network unreachable')) return 'discovery.errorHintNoRoute'
  if (e.includes('dns') || e.includes('name resolution') || e.includes('getaddrinfo')) return 'discovery.errorHintDns'
  if (e.includes('reset') || e.includes('errno 104')) return 'discovery.errorHintReset'
  return null
}

export const runTitle = (run, t) => run.profile_name || t('discovery.adHocScan')
export const foundTitle = (c, t) => (c.status === 'error' ? `${c.target}:${c.port || 443}` : cnOf(c.subject) || c.target || t('common.unknown'))

/** The analysis' figures, shared by the list cells and the dock. */
export function useScanFacts() {
  const { t } = useTranslation()
  return {
    range: (p) => {
      const list = targetsOf(p)
      return list.length > 2 ? `${list.slice(0, 2).join(', ')} +${list.length - 2}` : list.join(', ') || '—'
    },
    found: (p, run) => {
      if (!run) return t('discovery.scans.notScanned')
      if (run.status === 'running') return t('discovery.scans.state.running')
      if (run.status !== 'completed') return t('discovery.scans.interrupted')
      return run.new_certs > 0
        ? t('discovery.scans.foundNew', { count: run.new_certs, total: run.certs_found ?? 0 })
        : String(run.certs_found ?? 0)
    },
    last: (p, run) => {
      if (run?.started_at || p.last_scan_at) return when(run?.started_at || p.last_scan_at)
      return p.schedule_enabled && p.next_scan_at ? t('discovery.scans.plannedOn', { date: when(p.next_scan_at) }) : '—'
    },
    schedule: (p) => t(`discovery.form.every.${p.schedule_interval_minutes || 0}`, { defaultValue: t('discovery.everyNMin', { n: p.schedule_interval_minutes }) }),
  }
}

