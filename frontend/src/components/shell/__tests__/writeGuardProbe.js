/**
 * Test helper for the central write guard: whether a control is taken while writes are
 * suspended (then given back), its render container standing for the shell's page.
 */
import { applyWriteGuard } from '../writeGuard'

export function blockedWhileSuspended(el) {
  let host = el
  while (host.parentElement && host.parentElement !== document.body) host = host.parentElement
  const added = !host.classList.contains('shell-main')
  if (added) host.classList.add('shell-main')
  applyWriteGuard({ suspended: true, noteId: 'probe-note' })
  const blocked = el.disabled === true || el.getAttribute('aria-disabled') === 'true'
  applyWriteGuard({ suspended: false })
  if (added) host.classList.remove('shell-main')
  return blocked
}
