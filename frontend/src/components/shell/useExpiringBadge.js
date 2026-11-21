/** Expiring or expired certificates count (polled), dismissible until the count changes. */
import { useCallback, useEffect, useState } from 'react'
import { certificatesService } from '../../services'

const DISMISS_KEY = 'ucm_badge_dismissed'
const POLL_MS = 5 * 60 * 1000

export function useExpiringBadge() {
  const [count, setCount] = useState(0)
  const [dismissed, setDismissed] = useState(() => {
    try {
      const stored = localStorage.getItem(DISMISS_KEY)
      return stored ? JSON.parse(stored) : { count: 0, at: 0 }
    } catch { return { count: 0, at: 0 } }
  })

  useEffect(() => {
    // The interval stops the next poll, not the one in flight
    let cancelled = false
    const load = async () => {
      try {
        const stats = await certificatesService.getStats()
        if (cancelled) return
        setCount((stats?.data?.expiring || 0) + (stats?.data?.expired || 0))
      } catch { /* the badge is optional */ }
    }
    load()
    const timer = setInterval(load, POLL_MS)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  const dismiss = useCallback(() => {
    const state = { count, at: Date.now() }
    setDismissed(state)
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify(state)) } catch { /* storage is optional */ }
  }, [count])

  return { count: dismissed.count === count ? 0 : count, dismiss }
}
