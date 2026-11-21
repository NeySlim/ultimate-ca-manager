/**
 * What an approval request shows in the work queue: its title, type pill, facts,
 * deadline and urgency group. The deadline is the server's (services/approval_gate.py):
 * expires_at, else seven days after creation.
 */
import { casService } from '../../services'
import { compactAgo } from '../../lib/relativeTime'
import { formatDate } from '../../lib/utils'

const HOUR = 3600000
export const REQUEST_LIFETIME_MS = 7 * 24 * HOUR
export const PROTOCOL_TYPES = ['acme_order', 'est_enroll', 'scep_request', 'wstep_request']
export const REQUEST_TYPES = ['certificate', 'csr', 'renewal', 'revocation', 'ca_revocation', 'cross_revocation', ...PROTOCOL_TYPES]

// Request state -> pill tone; the label is approvals.work.state.<status>
export const STATE_TONES = { pending: 'warn', approved: 'good', rejected: 'bad', expired: 'muted', cancelled: 'muted' }

export function requestDeadline(req) {
  if (req?.expires_at) return new Date(req.expires_at)
  if (req?.created_at) return new Date(new Date(req.created_at).getTime() + REQUEST_LIFETIME_MS)
  return null
}

/** The type's wording ("CSR to sign"), the raw type when it is not known. */
export const typeLabel = (req, t) => (REQUEST_TYPES.includes(req?.request_type)
  ? t(`approvals.work.what.${req.request_type}`) : (req?.request_type || ''))

export const subjectOf = (req) => req?.request_summary?.cn || `#${req?.id}`

// "CSR to sign: payments.example.com"; the separator follows the language (work.sep)
export const requestTitle = (req, t) => `${typeLabel(req, t)}${t('work.sep')}${subjectOf(req)}`

/** The pill: "Approval · ACME", "Approval · CSR"... */
export const requestKind = (req, t) => t('approvals.work.kind', {
  source: REQUEST_TYPES.includes(req?.request_type) ? t(`approvals.work.source.${req.request_type}`) : (req?.request_type || ''),
})

export function stateOf(req, t, now = Date.now()) {
  const status = isLapsed(req, now) ? 'expired' : req?.status
  return {
    tone: STATE_TONES[status] || 'muted',
    label: STATE_TONES[status] ? t(`approvals.work.state.${status}`) : (status || ''),
  }
}

export function requesterOf(req, t) {
  if (req?.requester_username) return req.requester_username
  return req?.request_summary?.trigger === 'auto' ? t('approvals.work.scheduler') : t('approvals.work.unknownRequester')
}

/** The facts line: who asked and when, the policy, the authority, the votes still owed. */
export function requestFacts(req, t, { caName } = {}) {
  const votes = req?.approvals?.filter((v) => v.action === 'approve').length || 0
  const need = req?.required_approvals || 1
  return [
    t('approvals.work.requestedBy', { user: requesterOf(req, t), ago: compactAgo(req?.created_at, t) }),
    req?.policy_name || '',
    caName || '',
    need > 1 ? t('approvals.work.votes', { count: votes, need }) : '',
  ].filter(Boolean)
}

/** A pending request past its deadline: the server expires it at its next read, nobody may decide it. */
export const isLapsed = (req, now = Date.now()) => req?.status === 'pending' && (requestDeadline(req)?.getTime() ?? Infinity) < now

/**
 * Urgency groups of the open requests, in the mockup's order; empty ones are left out by the
 * queue. The mockup's « En retard » is not drawn: a request past its deadline (isLapsed) is
 * expired, not late, and the page leaves it out of the open ones.
 */
export function approvalGroups(pending, t, now = Date.now()) {
  const due = (r) => requestDeadline(r)?.getTime() ?? Infinity
  const sorted = [...pending].sort((a, b) => due(a) - due(b))
  return [
    { id: 'soon', label: t('approvals.work.groups.soon'), icon: 'clock', tone: 'warn', test: (r) => due(r) - now < 48 * HOUR },
    { id: 'later', label: t('approvals.work.groups.later'), icon: 'clock', tone: '', test: (r) => due(r) - now >= 48 * HOUR },
  ].map(({ test, ...g }) => ({ ...g, requests: sorted.filter(test) }))
}

/** The last vote of a decided request, or null. */
export const lastVote = (req) => (req?.approvals?.length ? req.approvals[req.approvals.length - 1] : null)

/** "alice · 9 Nov 2026, 16:20 · reason" for a decided request. */
export function decisionMeta(req) {
  const vote = lastVote(req)
  return [vote?.username, req?.resolved_at ? formatDate(req.resolved_at, { time: true }) : '', vote?.comment].filter(Boolean).join(' · ')
}

// The authorities by id, with their level (1 for a root), read once for the queue and its inspector
const CA_INDEX_TTL = 60000
let caIndex = null
const caLabel = (ca) => ca?.common_name || ca?.descr || ca?.name || ''
export function caIndexOf(list) {
  const byId = new Map(list.map((ca) => [String(ca.id), ca]))
  const out = new Map()
  for (const ca of list) {
    let level = 1
    for (let c = ca, seen = new Set(); c?.parent_id != null && !seen.has(c.id); level += 1) {
      seen.add(c.id)
      c = byId.get(String(c.parent_id))
      if (!c) break
    }
    out.set(String(ca.id), { name: caLabel(ca), level })
  }
  return out
}
export function loadCaIndex(now = Date.now()) {
  if (caIndex && now - caIndex.at < CA_INDEX_TTL) return caIndex.promise
  const promise = Promise.resolve(casService?.getAll?.())
    .then((res) => caIndexOf(Array.isArray(res?.data) ? res.data : []))
    .catch(() => { caIndex = null; return new Map() })
  caIndex = { at: now, promise }
  return promise
}
export const resetCaIndex = () => { caIndex = null }

/** "DNS : name", "IP : 192.0.2.1", "E-mail : a@b", "URI : https://…": the type read from the value. */
export function sanLine(value, t) {
  const v = String(value || '')
  const kind = /^[a-z][a-z0-9+.-]*:\/\//i.test(v) ? 'uri'
    : v.includes('@') ? 'email'
      : (/^\d{1,3}(\.\d{1,3}){3}$/.test(v) || (v.includes(':') && /^[0-9a-f:]+$/i.test(v))) ? 'ip' : 'dns'
  return t(`approvals.work.detail.san.${kind}`, { value: v })
}
