/**
 * The account of a session locked after inactivity, kept for this tab only so the
 * sign-in page can show the lock screen. The page to return to travels in ?next=.
 */
const KEY = 'ucm_locked_session'

export function saveLock(account) {
  if (!account?.username) return
  try {
    sessionStorage.setItem(KEY, JSON.stringify({
      username: String(account.username),
      name: account.name ? String(account.name) : '',
      role: account.role ? String(account.role) : '',
      method: account.method ? String(account.method) : '',
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
