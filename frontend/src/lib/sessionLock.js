/**
 * The account of a locked session (by hand or after inactivity), kept for this tab only so the
 * sign-in page can show the lock screen. The page to return to travels in ?next=.
 */
const KEY = 'ucm_locked_session'
const CHANNEL = 'ucm-session-lock'

export function saveLock(account) {
  if (!account?.username) return
  try {
    sessionStorage.setItem(KEY, JSON.stringify({
      username: String(account.username),
      name: account.name ? String(account.name) : '',
      role: account.role ? String(account.role) : '',
      method: account.method ? String(account.method) : '',
      reason: account.reason === 'manual' ? 'manual' : 'idle',
    }))
  } catch { /* storage is optional: the plain sign-in page shows instead */ }
}

export function readLock() {
  try {
    const value = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    return value && typeof value.username === 'string' && value.username ? value : null
  } catch {
    return null
  }
}

export function clearLock() {
  try { sessionStorage.removeItem(KEY) } catch { /* noop */ }
}

// The tabs of a browser share one session: a lock in one closes it for all, and tells the others
export function announceLock(username, reason) {
  if (!username || typeof BroadcastChannel === 'undefined') return
  try {
    const channel = new BroadcastChannel(CHANNEL)
    channel.postMessage({ type: 'locked', username: String(username), reason: reason === 'manual' ? 'manual' : 'idle' })
    channel.close()
  } catch { /* the other tabs lock on their next refused call */ }
}

export function listenForLocks(onLock) {
  if (typeof BroadcastChannel === 'undefined') return () => {}
  const channel = new BroadcastChannel(CHANNEL)
  channel.onmessage = (event) => {
    const data = event?.data
    if (data?.type !== 'locked' || typeof data.username !== 'string' || !data.username) return
    onLock({ username: data.username, reason: data.reason === 'manual' ? 'manual' : 'idle' })
  }
  return () => channel.close()
}

// Set by the in-app lock and taken once by the lock screen: a reload or an address typed
// in opens it quietly, the lock that just happened moves the focus and is announced.
let justLocked = false

export function markJustLocked() {
  justLocked = true
}

export function takeJustLocked() {
  const was = justLocked
  justLocked = false
  return was
}

// Set by a sign-out and taken once by the sign-in page: it says so and focuses its title, as the design does.
let justSignedOut = false

export function markSignedOut() {
  justSignedOut = true
}

export function takeSignedOut() {
  const was = justSignedOut
  justSignedOut = false
  return was
}
