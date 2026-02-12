/**
 * useServiceReconnect - Hook for waiting on service restart/update
 * Shows a fullscreen overlay that polls the health endpoint until the service is back.
 * Two phases: 1) wait for service to go DOWN, 2) wait for it to come back UP.
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

    let sawDown = false
    let attempts = 0

    // Wait initial delay before polling (must be longer than service shutdown time)
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
            if (!sawDown) {
              // Service hasn't gone down yet — keep waiting
              setTimeout(poll, POLL_INTERVAL)
              return
            }
            const data = await resp.json()
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
          sawDown = true
        } catch {
          sawDown = true
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
