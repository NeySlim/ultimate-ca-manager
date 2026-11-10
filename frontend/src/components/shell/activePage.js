/**
 * Active module id from the URL, the single source of truth for the shell:
 * exact module path first, then the longest parent path (detail pages), then
 * the first URL segment for pages the registry does not list. '/' is ''.
 */
import { MODULES } from '../../navigation/registry'

const ROUTED = MODULES.filter(m => m.path !== '/')

export function resolveActivePageId(pathname) {
  if (pathname === '/') return ''
  const exact = ROUTED.find(m => m.path === pathname)
  if (exact) return exact.id
  const prefix = ROUTED
    .filter(m => pathname.startsWith(m.path + '/'))
    .sort((a, b) => b.path.length - a.path.length)[0]
  if (prefix) return prefix.id
  return pathname.split('/')[1] || ''
}
