import { useCallback, useRef, useState } from 'react'

/**
 * `run(fn)` calls fn unless a previous run is still pending, and `busy` is true meanwhile:
 * the ref blocks a second click in the same tick, before the state has rendered.
 */
export function useInFlight() {
  const inFlight = useRef(false)
  const [busy, setBusy] = useState(false)
  const run = useCallback(async (fn) => {
    if (inFlight.current) return undefined
    inFlight.current = true
    setBusy(true)
    try {
      return await fn()
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }, [])
  return [busy, run]
}
