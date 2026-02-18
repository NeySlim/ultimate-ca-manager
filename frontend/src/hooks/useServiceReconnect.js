/**
 * useServiceReconnect - Hook for waiting on service restart/update
 * 
 * Flow:
 * 1. countdown (30s) - visual countdown before any polling
 * 2. connecting - polls /api/health until service is back with new started_at
 * 3. redirecting - service is back, clears cache & redirects to /login
 * 4. timeout - max attempts exceeded
 */
import { useState, useCallback, useRef, useEffect } from 'react'

const HEALTH_URL = '/api/v2/health'
const POLL_INTERVAL = 2000
const MAX_ATTEMPTS = 90 // 3 minutes max after countdown
const COUNTDOWN_SECONDS = 60

export function useServiceReconnect() {
  const [reconnecting, setReconnecting] = useState(false)
  const [status, setStatus] = useState('') // 'countdown', 'connecting', 'redirecting', 'timeout'
  const [attempt, setAttempt] = useState(0)
  const [countdown, setCountdown] = useState(0)
  const abortRef = useRef(null)
  const countdownRef = useRef(null)
  const cancelledRef = useRef(false)

  // Cleanup countdown interval on unmount
  useEffect(() => {
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current)
    }
  }, [])

  const waitForRestart = useCallback((opts = {}) => {
    const { expectedVersion } = opts
    
    cancelledRef.current = false
    setReconnecting(true)
    setStatus('countdown')
    setCountdown(COUNTDOWN_SECONDS)
    setAttempt(0)

    // Capture current started_at before restart
    let initialStartedAt = null
    fetch(HEALTH_URL, { cache: 'no-store' })
      .then(r => r.json())
      .then(d => { initialStartedAt = d.started_at })
      .catch(() => {})

    // Phase 1: Countdown
    let remaining = COUNTDOWN_SECONDS
    countdownRef.current = setInterval(() => {
      remaining--
      setCountdown(remaining)
      if (remaining <= 0) {
        clearInterval(countdownRef.current)
        countdownRef.current = null
        if (!cancelledRef.current) {
          startPolling(initialStartedAt, expectedVersion)
        }
      }
    }, 1000)

    // Phase 2: Polling
    const startPolling = (initStartedAt, expVersion) => {
      setStatus('connecting')
      let attempts = 0

      const poll = async () => {
        if (cancelledRef.current) return
        attempts++
        setAttempt(attempts)

        if (attempts > MAX_ATTEMPTS) {
          setStatus('timeout')
          return
        }

        try {
          const controller = new AbortController()
          abortRef.current = controller
          const resp = await fetch(HEALTH_URL, {
            signal: controller.signal,
            cache: 'no-store'
          })

          if (resp.ok) {
            const data = await resp.json()
            // Wait until started_at changes (service actually restarted)
            if (initStartedAt && data.started_at && data.started_at <= initStartedAt) {
              setTimeout(poll, POLL_INTERVAL)
              return
            }
            if (expVersion && data.version !== expVersion) {
              setTimeout(poll, POLL_INTERVAL)
              return
            }
            // Wait until WebSocket server is ready
            if (!data.websocket) {
              setTimeout(poll, POLL_INTERVAL)
              return
            }
            // Service + WebSocket are back — clear cache and redirect to login
            onServiceBack()
            return
          }
        } catch {
          // Service not ready yet
        }

        setTimeout(poll, POLL_INTERVAL)
      }

      poll()
    }

    const onServiceBack = async () => {
      setStatus('redirecting')

      // Invalidate browser caches (CSS, JS bundles)
      try {
        if ('caches' in window) {
          const keys = await caches.keys()
          await Promise.all(keys.map(k => caches.delete(k)))
        }
      } catch { /* cache API may not be available */ }

      // Clear local/session storage (auth tokens, preferences cache)
      try {
        sessionStorage.clear()
      } catch { /* ignore */ }

      // Force logout by redirecting to login — backend session is invalid after restart
      setTimeout(() => {
        window.location.href = '/login'
      }, 1500)
    }
  }, [])

  const cancel = useCallback(() => {
    cancelledRef.current = true
    if (countdownRef.current) {
      clearInterval(countdownRef.current)
      countdownRef.current = null
    }
    if (abortRef.current) abortRef.current.abort()
    setReconnecting(false)
    setStatus('')
    setAttempt(0)
    setCountdown(0)
  }, [])

  return { reconnecting, status, attempt, countdown, waitForRestart, cancel }
}

export default useServiceReconnect
