/**
 * Drafts of the sectioned pages, held in memory for the life of the tab: a page left with
 * changes pending finds them on its return. Never written to browser storage (a draft may
 * hold a secret); a sign-out, or another account signing in, drops them all.
 */
const drafts = new Map()
let owner = null

/** Keeps `value` under `key`, or forgets the key when `value` is null or undefined. */
export function keepDraft(key, value) {
  if (value === null || value === undefined) drafts.delete(key)
  else drafts.set(key, value)
}

export function readDraft(key) {
  return drafts.get(key)
}

export function hasDraft(key) {
  return drafts.has(key)
}

export function dropAllDrafts() {
  drafts.clear()
}

/** The signed-in account: another one than the drafts' owner drops them. */
export function setDraftOwner(name) {
  if (!name) return
  if (owner !== null && owner !== name) drafts.clear()
  owner = name
}

/** Sign-out: the drafts go with the session. */
export function signOutDrafts() {
  drafts.clear()
  owner = null
}
