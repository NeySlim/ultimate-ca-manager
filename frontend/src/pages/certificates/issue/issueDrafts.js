/**
 * Drafts of the issue form, one per operation ('issue', 'renew:<id>'), kept in memory only:
 * closing the form without issuing keeps it for the next opening, a reload forgets it.
 * They live in the session's draft memory, so a sign-out or another account drops them.
 */
import { hasDraft as held, keepDraft as hold, readDraft } from '../../../lib/draftMemory'

const keyOf = (op) => `issue-form:${op}`
const ops = new Set()

// The only fields a draft keeps: form entries, never a private key nor a password
export const DRAFT_FIELDS = [
  'template', 'ca_id', 'cn', 'description', 'keySource', 'csr', 'key', 'keyBy',
  'validityMode', 'validity_days', 'daysBy', 'expiry_date', 'sans', 'advanced', 'cert_type', 'extra_ekus',
  'ocsp_must_staple', 'subject', 'customExt', 'hybrid', 'hybrid_classical', 'hybrid_pq',
  'showAllTemplates', 'showHiddenCas',
]

export const draftOp = (mode, certificateId) => (mode === 'renew' ? `renew:${certificateId}` : 'issue')

const pick = (draft) => JSON.parse(JSON.stringify(
  Object.fromEntries(DRAFT_FIELDS.filter((k) => draft?.[k] !== undefined).map((k) => [k, draft[k]])),
))

export function keepDraft(op, draft) { ops.add(op); hold(keyOf(op), pick(draft)) }

/** The kept draft of *op*, removed from the store (the form now holds it), or null. */
export function takeDraft(op) {
  const draft = readDraft(keyOf(op))
  dropDraft(op)
  return draft ?? null
}

export function dropDraft(op) { ops.delete(op); hold(keyOf(op), null) }

export const hasDraft = (op) => held(keyOf(op))

/** Forgets every draft of the form (tests). */
export function clearDrafts() { for (const op of [...ops]) dropDraft(op) }
