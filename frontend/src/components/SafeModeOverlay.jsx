/**
 * SafeModeOverlay - Shown when UCM is in safe mode (encryption key missing)
 * Polls /api/health to detect when safe mode is resolved.
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldWarning, ArrowsClockwise, Key } from '@phosphor-icons/react'

const HEALTH_URL = '/api/health'
const POLL_INTERVAL = 5000

export function SafeModeOverlay() {
  const { t } = useTranslation()
  const [safeMode, setSafeMode] = useState(false)
  const [checking, setChecking] = useState(true)
  const timerRef = useRef(null)

  useEffect(() => {
    checkHealth()
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [])

  const checkHealth = async () => {
    try {
      const resp = await fetch(HEALTH_URL, { cache: 'no-store' })
      if (resp.ok) {
        const data = await resp.json()
        if (data.safe_mode) {
          setSafeMode(true)
          timerRef.current = setTimeout(checkHealth, POLL_INTERVAL)
        } else {
          if (safeMode) {
            // Was in safe mode, now resolved — reload
            window.location.reload()
          }
          setSafeMode(false)
        }
      }
    } catch {
      // Service unavailable
    }
    setChecking(false)
  }

  if (checking || !safeMode) return null

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="max-w-lg w-full mx-4 bg-bg-primary rounded-xl shadow-2xl border border-border p-8 text-center">
        <div className="w-16 h-16 rounded-full bg-amber-500/20 flex items-center justify-center mx-auto mb-4">
          <ShieldWarning size={32} className="text-amber-500" weight="fill" />
        </div>
        
        <h2 className="text-xl font-bold text-text-primary mb-2">
          {t('safeMode.title')}
        </h2>
        
        <p className="text-sm text-text-secondary mb-4">
          {t('safeMode.description')}
        </p>

        <div className="bg-bg-tertiary rounded-lg p-4 text-left mb-4 space-y-3">
          <div className="flex items-start gap-2">
            <Key size={18} className="text-accent-primary flex-shrink-0 mt-0.5" />
            <div className="text-sm text-text-primary">
              <p className="font-medium mb-1">{t('safeMode.step1Title')}</p>
              <code className="text-xs bg-bg-secondary px-2 py-1 rounded block">
                /etc/ucm/master.key
              </code>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <ArrowsClockwise size={18} className="text-accent-primary flex-shrink-0 mt-0.5" />
            <div className="text-sm text-text-primary">
              <p className="font-medium">{t('safeMode.step2Title')}</p>
              <code className="text-xs bg-bg-secondary px-2 py-1 rounded block mt-1">
                systemctl restart ucm
              </code>
            </div>
          </div>
        </div>

        <p className="text-xs text-text-tertiary mb-4">
          {t('safeMode.lostKeyHint')}
        </p>

        <div className="flex items-center justify-center gap-2 text-sm text-text-tertiary">
          <ArrowsClockwise size={14} className="animate-spin" />
          <span>{t('safeMode.polling')}</span>
        </div>
      </div>
    </div>
  )
}
