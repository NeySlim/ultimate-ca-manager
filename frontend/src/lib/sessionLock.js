/**
 * The account of a locked session (by hand or after inactivity), kept for this tab only so the
 * sign-in page can show the lock screen. The page to return to travels in ?next=.
 */
const KEY = 'ucm_locked_session'
const CHANNEL = 'ucm-session-lock'
const SHARED_KEY = 'ucm_session_lock_shared'

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

// The lock as its tab made it, for the tabs that miss its message (loading, frozen, no channel):
// only the account name and the reason leave the tab; the tabs of that account take it once
// they find the session gone. A sign-in or a sign-out removes it.
export function shareLock(account) {
  if (!account?.username) return
  try {
    localStorage.setItem(SHARED_KEY, JSON.stringify({
      username: String(account.username),
      reason: account.reason === 'manual' ? 'manual' : 'idle',
    }))
  } catch { /* the other tabs then show the sign-in page */ }
}

export function readSharedLock() {
  try {
    const value = JSON.parse(localStorage.getItem(SHARED_KEY) || 'null')
    if (!value || typeof value.username !== 'string' || !value.username) return null
    return { username: value.username, reason: value.reason === 'manual' ? 'manual' : 'idle' }
  } catch {
    return null
  }
}

export function clearSharedLock() {
  try { localStorage.removeItem(SHARED_KEY) } catch { /* noop */ }
}

// A lock sent to the server and not yet confirmed (its POST failed, or the page went first): the
// next load of any tab sends it again before showing the console. Confirmed, or the session
// signed out instead, it goes.
const UNCONFIRMED_KEY = 'ucm_session_lock_unconfirmed'

export function markLockUnconfirmed(account) {
  if (!account?.username) return
  try {
    localStorage.setItem(UNCONFIRMED_KEY, JSON.stringify({
      username: String(account.username),
      reason: account.reason === 'manual' ? 'manual' : 'idle',
    }))
  } catch { /* the lock is still sent and retried */ }
}

export function readUnconfirmedLock() {
  try {
    const value = JSON.parse(localStorage.getItem(UNCONFIRMED_KEY) || 'null')
    if (!value || typeof value.username !== 'string' || !value.username) return null
    return { username: value.username, reason: value.reason === 'manual' ? 'manual' : 'idle' }
  } catch {
    return null
  }
}

export function clearUnconfirmedLock() {
  try { localStorage.removeItem(UNCONFIRMED_KEY) } catch { /* noop */ }
}

// The account this tab is signed in as, set by the auth context, for a request refused outside it
let tabAccount = null

export function setTabAccount(account) {
  tabAccount = account?.username ? { ...account, username: String(account.username) } : null
}

/** Keeps the lock screen of this tab's account when its lock was made in another tab. */
export function adoptSharedLock() {
  const shared = readSharedLock()
  if (!shared || !tabAccount || shared.username !== tabAccount.username) return false
  saveLock({ ...tabAccount, reason: shared.reason })
  return true
}

// The 401 of a session the server holds locked: the account it names gets its lock screen
export const SESSION_LOCKED_PROBLEM = 'urn:ucm:problem:session-locked'

/** Keeps the lock screen of the account a locked session's refusal names, with what this tab knew of it. */
export function adoptServerLock(details) {
  const username = typeof details?.username === 'string' ? details.username : ''
  if (!username) return false
  const known = tabAccount?.username === username ? tabAccount : {}
  saveLock({ ...known, username, reason: details.reason === 'manual' ? 'manual' : 'idle' })
  return true
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
