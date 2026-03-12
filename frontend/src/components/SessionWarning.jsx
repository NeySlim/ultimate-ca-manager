/**
 * SessionWarning Component - Warn user before session expires
 * Shows countdown popup when session is about to expire.
 * Uses the actual backend session_timeout (from /auth/verify) instead of a hardcoded value.
 * Before logging out, verifies with the backend that the session is truly expired.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Timer, ArrowsClockwise } from '@phosphor-icons/react'
import { Modal, Button } from '../components'
import { useAuth } from '../contexts'
import { authService } from '../services'

const WARNING_BEFORE = 5 * 60 * 1000 // Show warning 5 minutes before expiry
const FALLBACK_TIMEOUT = 8 * 60 * 60 * 1000 // 8h fallback (matches backend default)

export function SessionWarning() {
  const { t } = useTranslation()
  const { user, logout, checkSession } = useAuth()
  const [showWarning, setShowWarning] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)
  const [lastActivity, setLastActivity] = useState(Date.now())
  const sessionTimeoutRef = useRef(FALLBACK_TIMEOUT)

  // Fetch actual session timeout from backend on mount
  useEffect(() => {
    if (!user) return
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

  // Track user activity
  useEffect(() => {
    const updateActivity = () => setLastActivity(Date.now())
    
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
        handleExpired()
        return
      }

      if (timeUntilExpiry <= WARNING_BEFORE && !showWarning) {
        setShowWarning(true)
        setSecondsLeft(Math.floor(timeUntilExpiry / 1000))
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
    try {
      const stillValid = await checkSession()
      if (stillValid) {
        // Backend says session is still valid — reset timer
        setLastActivity(Date.now())
        setShowWarning(false)
        return
      }
    } catch {
      // Network error or truly expired
    }
    logout()
  }, [checkSession, logout])

  const extendSession = useCallback(async () => {
    try {
      // Make authenticated request to refresh backend session
      await authService.getCurrentUser()
      setLastActivity(Date.now())
      setShowWarning(false)
    } catch {
      // If verify fails, session is already expired
      logout()
    }
  }, [logout])

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  if (!user || !showWarning) return null

  return (
    <Modal
      open={showWarning}
      onClose={() => {}} // Don't allow closing by clicking outside
      title={t('session.expiring')}
    >
      <div className="p-4 text-center space-y-4">
        <div className="flex justify-center">
          <div className="p-4 rounded-full bg-accent-warning-op15">
            <Timer size={48} weight="duotone" className="text-accent-warning" />
          </div>
        </div>
        
        <div>
          <p className="text-text-primary font-medium">
            {t('session.willExpireIn')}
          </p>
          <p className="text-3xl font-bold text-accent-warning mt-2">
            {formatTime(secondsLeft)}
          </p>
        </div>
        
        <p className="text-sm text-text-secondary">
          {t('session.clickToContinue')}
        </p>
        
        <div className="flex gap-3 justify-center pt-2">
          <Button type="button" variant="secondary" onClick={logout}>
            {t('session.logOutNow')}
          </Button>
          <Button type="button" onClick={extendSession}>
            <ArrowsClockwise size={16} />
            {t('session.stayLoggedIn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default SessionWarning
