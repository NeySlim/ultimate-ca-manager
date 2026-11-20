/**
 * What an approval request shows in the work queue: its title, type pill, facts,
 * deadline and urgency group. The deadline is the server's (services/approval_gate.py):
 * expires_at, else seven days after creation.
 */
import { Warning, Clock } from '@phosphor-icons/react'
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

export function stateOf(req, t) {
  const status = req?.status
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

/** Urgency groups of the open requests, in the mockup's order; empty ones are left out by the queue. */
export function approvalGroups(pending, t, now = Date.now()) {
  const due = (r) => requestDeadline(r)?.getTime() ?? Infinity
  const sorted = [...pending].sort((a, b) => due(a) - due(b))
  return [
    { id: 'overdue', label: t('approvals.work.groups.overdue'), icon: Warning, tone: 'bad', test: (r) => due(r) < now },
    { id: 'soon', label: t('approvals.work.groups.soon'), icon: Clock, tone: 'warn', test: (r) => due(r) >= now && due(r) - now < 48 * HOUR },
    { id: 'later', label: t('approvals.work.groups.later'), icon: Clock, tone: '', test: (r) => due(r) - now >= 48 * HOUR },
  ].map(({ test, ...g }) => ({ ...g, requests: sorted.filter(test) }))
}

/** The last vote of a decided request, or null. */
export const lastVote = (req) => (req?.approvals?.length ? req.approvals[req.approvals.length - 1] : null)

/** "alice · 9 Nov 2026, 16:20 · reason" for a decided request. */
export function decisionMeta(req) {
  const vote = lastVote(req)
  return [vote?.username, req?.resolved_at ? formatDate(req.resolved_at, { time: true }) : '', vote?.comment].filter(Boolean).join(' · ')
}
