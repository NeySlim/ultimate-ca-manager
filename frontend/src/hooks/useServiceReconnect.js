/**
 * useServiceReconnect - Hook for waiting on service restart/update
 * Shows a fullscreen overlay that polls the health endpoint until the service is back.
 * Detects restart by comparing started_at timestamp from /api/health.
 */
import { useState, useCallback, useRef } from 'react'

const HEALTH_URL = '/api/health'
const POLL_INTERVAL = 2000
const MAX_ATTEMPTS = 90 // 3 minutes max

export function useServiceReconnect() {
  const [reconnecting, setReconnecting] = useState(false)
  const [status, setStatus] = useState('') // 'waiting', 'connecting', 'reloading'
  const [attempt, setAttempt] = useState(0)
  const abortRef = useRef(null)

  const waitForRestart = useCallback((opts = {}) => {
    const { delay = 3000, onSuccess, expectedVersion } = opts
    
    setReconnecting(true)
    setStatus('waiting')
    setAttempt(0)

    // Capture current started_at before restart
    let initialStartedAt = null
    fetch(HEALTH_URL, { cache: 'no-store' })
      .then(r => r.json())
      .then(d => { initialStartedAt = d.started_at })
      .catch(() => {})

    let attempts = 0

    // Wait initial delay before polling
    setTimeout(() => {
      setStatus('connecting')

      const poll = async () => {
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
            if (initialStartedAt && data.started_at && data.started_at <= initialStartedAt) {
              setTimeout(poll, POLL_INTERVAL)
              return
            }
            if (expectedVersion && data.version !== expectedVersion) {
              setTimeout(poll, POLL_INTERVAL)
              return
            }
            setStatus('reloading')
            setTimeout(() => {
              if (onSuccess) onSuccess()
              else window.location.reload()
            }, 500)
            return
          }
        } catch {
          // Service not ready yet
        }

        setTimeout(poll, POLL_INTERVAL)
      }

      poll()
    }, delay)
  }, [])

  const cancel = useCallback(() => {
    if (abortRef.current) abortRef.current.abort()
    setReconnecting(false)
    setStatus('')
    setAttempt(0)
  }, [])

  return { reconnecting, status, attempt, waitForRestart, cancel }
}

export default useServiceReconnect
