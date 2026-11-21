import { useEffect, useRef } from 'react'

/**
 * A button disabled while its action runs loses the focus to the page: when `busy` ends,
 * the focus goes back to it, as the mockup returns it to its test button.
 */
export function useRefocusAfter(busy, ref) {
  const wasBusy = useRef(false)
  const hadFocus = useRef(false)
  useEffect(() => {
    if (busy && !wasBusy.current) {
      const active = document.activeElement
      hadFocus.current = !active || active === document.body || active === ref.current
    }
    if (!busy && wasBusy.current && hadFocus.current) {
      const active = document.activeElement
      // Only when nothing else took the focus meanwhile
      if (!active || active === document.body || active === ref.current) ref.current?.focus()
    }
    wasBusy.current = busy
  }, [busy, ref])
}
