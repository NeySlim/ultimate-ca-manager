/**
 * Drafts of the issue form, one per operation ('issue', 'renew:<id>'), kept in memory only:
 * closing the form without issuing keeps it for the next opening, a reload forgets it.
 */
const drafts = new Map()

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

export function keepDraft(op, draft) { drafts.set(op, pick(draft)) }

/** The kept draft of *op*, removed from the store (the form now holds it), or null. */
export function takeDraft(op) {
  const draft = drafts.get(op)
  drafts.delete(op)
  return draft ?? null
}

export function dropDraft(op) { drafts.delete(op) }

export const hasDraft = (op) => drafts.has(op)

/** Forgets every draft (tests). */
export function clearDrafts() { drafts.clear() }
