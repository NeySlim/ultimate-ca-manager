/**
 * SessionWarning Component - Warn user before session expires
 * Shows countdown popup when session is about to expire
 */
import { useState, useEffect, useCallback } from 'react'
import { Timer, ArrowsClockwise } from '@phosphor-icons/react'
import { Modal, Button } from '../components'
import { useAuth } from '../contexts'

// Default session timeout from settings (30 minutes)
const DEFAULT_SESSION_TIMEOUT = 30 * 60 * 1000 // 30 minutes in ms
const WARNING_BEFORE = 5 * 60 * 1000 // Show warning 5 minutes before expiry

export function SessionWarning() {
  const { user, logout } = useAuth()
  const [showWarning, setShowWarning] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)
  const [lastActivity, setLastActivity] = useState(Date.now())

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
      const sessionTimeout = DEFAULT_SESSION_TIMEOUT
      const timeSinceActivity = Date.now() - lastActivity
      const timeUntilExpiry = sessionTimeout - timeSinceActivity

      if (timeUntilExpiry <= 0) {
        // Session expired
        logout()
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
  }, [user, lastActivity, showWarning, logout])

  const extendSession = useCallback(async () => {
    try {
      // Make any authenticated request to refresh session
      await fetch('/api/v2/auth/verify', { credentials: 'include' })
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
      title="Session Expiring"
    >
      <div className="p-4 text-center space-y-4">
        <div className="flex justify-center">
          <div className="p-4 rounded-full bg-accent-warning/15">
            <Timer size={48} weight="duotone" className="text-accent-warning" />
          </div>
        </div>
        
        <div>
          <p className="text-text-primary font-medium">
            Your session will expire in
          </p>
          <p className="text-3xl font-bold text-accent-warning mt-2">
            {formatTime(secondsLeft)}
          </p>
        </div>
        
        <p className="text-sm text-text-secondary">
          Click below to continue working, or you'll be logged out automatically.
        </p>
        
        <div className="flex gap-3 justify-center pt-2">
          <Button variant="secondary" onClick={logout}>
            Log Out Now
          </Button>
          <Button onClick={extendSession}>
            <ArrowsClockwise size={16} />
            Stay Logged In
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default SessionWarning
