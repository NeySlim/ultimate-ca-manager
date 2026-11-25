import { useLayoutEffect, useRef } from 'react'

const BAR_IDS = ['settings-state', 'settings-reset', 'settings-save']

/**
 * A page whose save bar moves between the head and the form as `phone` flips: the control of the bar
 * that held the focus holds it again in the new bar. Read at the render of the flip, while the old bar is still drawn.
 */
export function useSaveBarFocus(phone) {
  const shown = useRef(phone)
  const carried = useRef(null)
  if (shown.current !== phone) {
    shown.current = phone
    const id = typeof document !== 'undefined' ? document.activeElement?.id : null
    carried.current = BAR_IDS.includes(id) ? id : null
  }
  useLayoutEffect(() => {
    const id = carried.current
    carried.current = null
    if (id) document.getElementById(id)?.focus()
  }, [phone])
}
