// One request for the callers that ask for the same route together (a page and the shell around it,
// two sections opened at once). A caller joins one still in flight; it joins one that ended less than
// `reuseMs` ago only when it says so, and any data change forgets the ended ones.
const entries = new Map()

// Each joiner gets its own copy: one caller sorting or editing its rows leaves the others' alone
const copy = (value) => {
  try { return JSON.parse(JSON.stringify(value)) } catch { return value }
}

// What a section opening with the page accepts: an answer the page itself just read
export const OPENING_REUSE_MS = 5000

export function sharedRequest(key, run, { reuseMs = 0 } = {}) {
  const hit = entries.get(key)
  if (hit && (hit.pending || Date.now() - hit.endedAt < reuseMs)) return hit.promise.then(copy)
  const entry = { pending: true, endedAt: 0 }
  entry.promise = Promise.resolve().then(run)
  entries.set(key, entry)
  entry.promise.then(
    () => { entry.pending = false; entry.endedAt = Date.now() },
    () => { if (entries.get(key) === entry) entries.delete(key) },
  )
  return entry.promise
}

export function dropSharedRequests() {
  entries.clear()
}

if (typeof window !== 'undefined') {
  window.addEventListener('ucm:data-changed', () => {
    for (const [key, entry] of entries) if (!entry.pending) entries.delete(key)
  })
}
