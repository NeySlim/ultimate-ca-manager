// One request for the callers that open together on the same route (a page and the shell around it,
// two sections opened at once). Only a caller passing `reuseMs` joins one in flight or one that ended
// less than `reuseMs` ago; any other caller and any data change start a fresh read.
const entries = new Map()

// Each joiner gets its own copy: one caller sorting or editing its rows leaves the others' alone
const copy = (value) => {
  try { return JSON.parse(JSON.stringify(value)) } catch { return value }
}

// What a section opening with the page accepts: an answer the page itself just read
export const OPENING_REUSE_MS = 5000

export function sharedRequest(key, run, { reuseMs = 0 } = {}) {
  const hit = entries.get(key)
  if (hit && reuseMs > 0 && (hit.pending || Date.now() - hit.endedAt < reuseMs)) return hit.promise.then(copy)
  const entry = { pending: true, endedAt: 0 }
  entry.promise = Promise.resolve().then(run)
  entries.set(key, entry)
  entry.promise.then(
    () => { entry.pending = false; entry.endedAt = Date.now() },
    () => { if (entries.get(key) === entry) entries.delete(key) },
  )
  return entry.promise.then(copy)
}

export function dropSharedRequests() {
  entries.clear()
}

if (typeof window !== 'undefined') {
  window.addEventListener('ucm:data-changed', () => {
    entries.clear()
  })
}
