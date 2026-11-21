/**
 * Return target after sign-in. Only an internal path the registry knows is
 * accepted; anything else (absolute URL, `//host`, backslash, unknown path) is null.
 */
import { isKnownPath } from './registry'

const NEVER_BACK = ['/login', '/forgot-password', '/reset-password']

export function safeNext(raw) {
  if (typeof raw !== 'string' || raw.length > 512) return null
  // One leading slash, then printable ASCII without spaces or backslashes
  if (!/^\/(?![/\\])[\x21-\x5b\x5d-\x7e]*$/.test(raw)) return null
  const path = raw.split(/[?#]/)[0]
  if (path.includes('%')) return null
  if (NEVER_BACK.some(p => path === p || path.startsWith(p + '/'))) return null
  return isKnownPath(path) ? raw : null
}

/** `/login` carrying the page to come back to (its query and anchor), left out for the landing page itself. */
export function loginUrl(pathname, search = '', hash = '') {
  const target = `${pathname || '/'}${search || ''}${hash || ''}`
  if (pathname === '/' || pathname === '/dashboard' || !safeNext(target)) return '/login'
  return `/login?next=${encodeURIComponent(target)}`
}
