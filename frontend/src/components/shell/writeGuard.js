/**
 * Central write guard: while writes are suspended (offline, cluster maintenance), every write
 * control of the page, the inspector and the open dialogs is disabled in place and points to
 * the banner sentence that says why. Only the controls disabled here are given back.
 */
import { useEffect } from 'react'

// What reads as a write: a primary or danger action, a form submission, or an explicit marker.
// A primary control that only reads (retry a load, export, close) opts out with data-write="false".
export const WRITE_SELECTOR = [
  '[data-write]',
  '.lv-btn.is-primary',
  '.lv-btn.is-danger',
  '.wk-btn.is-primary',
  '.wk-btn.is-danger',
  '.shell-btn.is-primary',
  '.btn-gradient',
  'button[type="submit"]',
  'input[type="submit"]',
].join(',')
// Where writes live: the page and the inspector, and the dialogs portalled out of them
export const GUARD_SCOPE = '.shell-main, [role="dialog"], [role="alertdialog"]'
const MARK = 'data-write-blocked'
const ARIA_MARK = 'data-write-blocked-aria'

const isWrite = (el) => el.matches(WRITE_SELECTOR) && el.getAttribute('data-write') !== 'false'
  && !!el.closest(GUARD_SCOPE) && !el.closest('[data-write-guard="off"]')
const canDisable = (el) => 'disabled' in el && el.tagName !== 'A'

function describe(el, noteId, add) {
  const ids = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean).filter(id => id !== noteId)
  if (add) ids.push(noteId)
  if (ids.length) el.setAttribute('aria-describedby', ids.join(' '))
  else el.removeAttribute('aria-describedby')
}

function block(el, noteId) {
  if (el.hasAttribute(MARK)) {
    // A re-render gave the control back: take it again
    if (canDisable(el) && !el.disabled) el.disabled = true
    return
  }
  if (canDisable(el)) {
    if (el.disabled) return // disabled by its own view: left alone, never re-enabled here
    el.disabled = true
  } else {
    if (el.getAttribute('aria-disabled') === 'true') return
    el.setAttribute('aria-disabled', 'true')
    el.setAttribute(ARIA_MARK, '')
  }
  el.setAttribute(MARK, noteId)
  describe(el, noteId, true)
}

function release(el) {
  const noteId = el.getAttribute(MARK)
  if (canDisable(el)) el.disabled = false
  if (el.hasAttribute(ARIA_MARK)) {
    el.removeAttribute('aria-disabled')
    el.removeAttribute(ARIA_MARK)
  }
  el.removeAttribute(MARK)
  describe(el, noteId, false)
}

/** Disables the write controls of `root` (default: the document) while `guard.suspended`. */
export function applyWriteGuard(guard, root = document.body) {
  const noteId = guard?.suspended ? guard.noteId : null
  for (const el of root.querySelectorAll(`[${MARK}]`)) {
    if (el.getAttribute(MARK) !== noteId) release(el)
  }
  if (!noteId) return
  for (const el of root.querySelectorAll(WRITE_SELECTOR)) {
    if (isWrite(el)) block(el, noteId)
  }
}

// Links and controls that cannot be disabled, and forms sent another way (Enter, a script):
// their activation is stopped before the page sees it
function isBlockedSubmit(e) {
  if (e.submitter) return e.submitter.hasAttribute(MARK)
  return !!e.target.querySelector?.(`button[type="submit"][${MARK}], input[type="submit"][${MARK}]`)
}
function stopBlocked(e) {
  const target = e.target instanceof Element ? e.target : null
  const blocked = e.type === 'submit' ? !!target && isBlockedSubmit(e) : !!target?.closest(`[${MARK}]`)
  if (!blocked) return
  e.preventDefault()
  e.stopPropagation()
}

export function useCentralWriteGuard(guard) {
  const noteId = guard?.suspended ? guard.noteId : null
  useEffect(() => {
    const state = { suspended: !!noteId, noteId }
    applyWriteGuard(state)
    if (!noteId) return undefined
    let queued = false
    const observer = new MutationObserver(() => {
      if (queued) return
      queued = true
      queueMicrotask(() => { queued = false; applyWriteGuard(state) })
    })
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'class', 'type', 'data-write'] })
    document.addEventListener('click', stopBlocked, true)
    document.addEventListener('submit', stopBlocked, true)
    return () => {
      observer.disconnect()
      document.removeEventListener('click', stopBlocked, true)
      document.removeEventListener('submit', stopBlocked, true)
      applyWriteGuard({ suspended: false })
    }
  }, [noteId])
}
