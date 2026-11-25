import { act } from '@testing-library/react'

/**
 * A screen whose width the test sets: `(max-width: 800px)` matches while `phone` is true, and
 * `resize(phone)` tells every listener, as a browser does when the window crosses 800 px.
 */
export function phoneScreen(phone) {
  const listeners = new Set()
  const previous = window.matchMedia
  const state = { phone }
  window.matchMedia = (query) => ({
    get matches() { return query === '(max-width: 800px)' ? state.phone : false },
    media: query,
    addEventListener: (_type, fn) => listeners.add(fn),
    removeEventListener: (_type, fn) => listeners.delete(fn),
    addListener: (fn) => listeners.add(fn),
    removeListener: (fn) => listeners.delete(fn),
  })
  return {
    resize(next) {
      state.phone = next
      act(() => { for (const fn of [...listeners]) fn({ matches: next }) })
    },
    restore() { window.matchMedia = previous },
  }
}
