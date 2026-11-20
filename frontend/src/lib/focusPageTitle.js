/**
 * Focus the heading of the console page shown, once it has rendered (a lazy page may take a
 * moment): after signing in and after Extend, as the design does. Gives up after `timeout` ms.
 */
const HEADING = '.shell-stage h1'

export function focusPageTitle(timeout = 4000) {
  const focus = () => {
    const h1 = document.querySelector(HEADING)
    if (!h1) return false
    if (!h1.hasAttribute('tabindex')) h1.setAttribute('tabindex', '-1')
    h1.focus({ preventScroll: true })
    return true
  }
  if (focus() || typeof MutationObserver === 'undefined') return
  const observer = new MutationObserver(() => { if (focus()) stop() })
  const timer = setTimeout(() => stop(), timeout)
  function stop() {
    observer.disconnect()
    clearTimeout(timer)
  }
  observer.observe(document.body, { childList: true, subtree: true })
}
