/**
 * Session expiry warning: a banner over the console in the last minutes of the
 * inactivity timeout (backend session_timeout, from /auth/verify), with Extend.
 * At the end, once the server confirms the session is gone, the screen locks:
 * the console unmounts and the sign-in page keeps the current page in ?next=.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock, ArrowClockwise } from '@phosphor-icons/react'
import { useAuth, useNotification } from '../contexts'
import { authService } from '../services'
import { focusPageTitle } from '../lib/focusPageTitle'
import './auth/auth.css'

const WARNING_BEFORE = 5 * 60 * 1000 // Show warning 5 minutes before expiry
const UNKNOWN_RECHECK = 30 * 1000 // Server unreachable: ask again after this
const UNKNOWN_MAX = 5 * 60 * 1000 // ...and lock the tab locally after this long
const FALLBACK_TIMEOUT = 8 * 60 * 60 * 1000 // 8h fallback (matches backend default)

const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

export function SessionWarning() {
  const { t } = useTranslation()
  const { user, lock, checkSession } = useAuth()
  const { showSuccess } = useNotification()
  const [showWarning, setShowWarning] = useState(false)
  // Announced once: the time left when the banner appears, then what Extend did
  const [announce, setAnnounce] = useState('')
  const [secondsLeft, setSecondsLeft] = useState(0)
  const [lastActivity, setLastActivity] = useState(Date.now())
  const sessionTimeoutRef = useRef(FALLBACK_TIMEOUT)
  const checkingRef = useRef(false)
  const recheckAtRef = useRef(0)
  const unknownSinceRef = useRef(null)

  // Fetch actual session timeout from backend on mount
  useEffect(() => {
    if (!user) return
    recheckAtRef.current = 0 // a new sign-in starts a fresh countdown
    unknownSinceRef.current = null
    const fetchTimeout = async () => {
      try {
        const response = await authService.getCurrentUser()
        const data = response.data || response
        if (data.session_timeout) {
          sessionTimeoutRef.current = data.session_timeout * 1000 // seconds → ms
        }
      } catch {
        // Keep fallback
      }
    }
    fetchTimeout()
  }, [user])

  // Track user activity; once the warning shows, only Extend keeps the session
  const warningRef = useRef(false)
  warningRef.current = showWarning
  useEffect(() => {
    const updateActivity = () => { if (!warningRef.current) setLastActivity(Date.now()) }

    const events = ['mousedown', 'keydown', 'scroll', 'touchstart']
    events.forEach(event => window.addEventListener(event, updateActivity, { passive: true }))
    
    return () => {
      events.forEach(event => window.removeEventListener(event, updateActivity))
    }
  }, [])

  // Check session expiry
  useEffect(() => {
    if (!user) return

    const checkExpiry = () => {
      const sessionTimeout = sessionTimeoutRef.current
      const timeSinceActivity = Date.now() - lastActivity
      const timeUntilExpiry = sessionTimeout - timeSinceActivity

      if (timeUntilExpiry <= 0) {
        // Verify with backend before logging out — session may still be valid
        if (!checkingRef.current && Date.now() >= recheckAtRef.current) handleExpired()
        return
      }

      if (timeUntilExpiry <= WARNING_BEFORE && !showWarning) {
        setShowWarning(true)
        setSecondsLeft(Math.floor(timeUntilExpiry / 1000))
        setAnnounce(t('session.announceLeft', { time: formatTime(Math.floor(timeUntilExpiry / 1000)) }))
      }

      if (showWarning) {
        setSecondsLeft(Math.max(0, Math.floor(timeUntilExpiry / 1000)))
      }
    }

    const interval = setInterval(checkExpiry, 1000)
    return () => clearInterval(interval)
  }, [user, lastActivity, showWarning])

  // Verify with backend before actually logging out
  const handleExpired = useCallback(async () => {
    checkingRef.current = true
    try {
      const stillValid = await checkSession()
      if (stillValid) {
        // Backend says session is still valid — reset timer
        unknownSinceRef.current = null
        setLastActivity(Date.now())
        setShowWarning(false)
        return
      }
      if (stillValid === null) {
        // Server unreachable (e.g. a laptop waking before the network is
        // back): wait for it, but not forever, the expired tab still shows data
        unknownSinceRef.current ??= Date.now()
        if (Date.now() - unknownSinceRef.current < UNKNOWN_MAX) {
          recheckAtRef.current = Date.now() + UNKNOWN_RECHECK
          return
        }
      }
    } catch {
      // Truly expired
    } finally {
      checkingRef.current = false
    }
    recheckAtRef.current = Infinity // one lock, not one per tick while it runs
    lock()
  }, [checkSession, lock])

  const extendSession = useCallback(async () => {
    // /auth/verify refreshes the server session; only a server that says it
    // is gone signs out, an unreachable one leaves the warning up
    const stillValid = await checkSession()
    if (stillValid) {
      unknownSinceRef.current = null
      setLastActivity(Date.now())
      setShowWarning(false)
      const extended = t('session.extended', { minutes: Math.round(sessionTimeoutRef.current / 60000) })
      setAnnounce(extended)
      showSuccess(extended)
      // The button goes with the banner: the focus goes to the page's title, not to the body
      focusPageTitle()
    } else if (stillValid === false) {
      lock()
    }
  }, [checkSession, lock, showSuccess, t])

  // The region stays mounted so its announcement is read, the banner shown or not
  const live = <span className="sr-only" aria-live="polite">{announce}</span>
  if (!user) return null
  if (!showWarning) return live

  return (
    <div className="session-banner" role="region" aria-labelledby="session-banner-title">
      <Clock size={20} aria-hidden="true" />
      <p>
        <strong id="session-banner-title">{t('session.expiresIn', { time: formatTime(secondsLeft) })}</strong>
        <span>{t('session.lockNotice')}</span>
      </p>
      {/* Announced once, not at every tick of the countdown */}
      {live}
      <button type="button" className="auth-btn is-primary" onClick={extendSession}>
        <ArrowClockwise size={17} aria-hidden="true" />{t('session.extend')}
      </button>
    </div>
  )
}

export default SessionWarning
