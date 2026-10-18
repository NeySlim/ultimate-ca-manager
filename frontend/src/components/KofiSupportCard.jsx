/**
 * KofiSupportCard: a dismissible corner card inviting admins to support UCM,
 * shown once per UCM version. The dismissed version is a server-side
 * preference (`kofi_seen_version`), so it follows the user across browsers.
 */
import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Coffee, X } from '@phosphor-icons/react'
import { useAuth } from '../contexts/AuthContext'
import { usePermission } from '../hooks/usePermission'
import {
  arePreferencesLoaded, getPreferences, persistPreference, subscribePreferences,
} from '../stores/userPreferencesStore'
import { KOFI_URL } from '../lib/support'

const OPEN_DIALOG_SELECTOR = '[role="dialog"]:not([data-state="closed"]), [role="alertdialog"]'

function isDialogOpen() {
  return typeof document !== 'undefined' && !!document.querySelector(OPEN_DIALOG_SELECTOR)
}

export function KofiSupportCard({ version = __APP_VERSION__ }) {
  const { t } = useTranslation()
  const location = useLocation()
  const { user, forcePasswordChange, mustEnroll2fa } = useAuth()
  const { isAdmin } = usePermission()
  const admin = isAdmin()
  const [prefs, setPrefs] = useState(() => ({
    loaded: arePreferencesLoaded(), seen: getPreferences().kofi_seen_version,
  }))
  const [dialogOpen, setDialogOpen] = useState(isDialogOpen)

  useEffect(() => {
    const read = (next) => setPrefs({ loaded: arePreferencesLoaded(), seen: next.kofi_seen_version })
    read(getPreferences())
    return subscribePreferences(read)
  }, [])

  // Only once the server prefs are in the store: the dismissal PUT sends them all.
  const pending = !!user?.id && admin && !!version && prefs.loaded && prefs.seen !== version

  // Radix portals mount on <body>; navigation is the fallback re-check.
  useEffect(() => {
    if (!pending) return
    const update = () => setDialogOpen(isDialogOpen())
    update()
    const observer = new MutationObserver(update)
    observer.observe(document.body, { childList: true })
    return () => observer.disconnect()
  }, [pending, location.pathname])

  const acknowledge = useCallback(() => {
    persistPreference('kofi_seen_version', version)
  }, [version])

  if (!pending || dialogOpen || forcePasswordChange || mustEnroll2fa) return null

  return (
    <aside
      aria-label={t('kofi.label')}
      className="fixed z-30 bottom-3 left-3 right-3 sm:left-auto sm:right-8 sm:bottom-12 sm:w-80 rounded-xl border border-border bg-bg-secondary shadow-xl p-3"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5 text-accent-primary">
          <Coffee size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-text-secondary">{t('kofi.message')}</p>
          <a
            href={KOFI_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={acknowledge}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium btn-soft text-text-primary focus-ring"
          >
            {t('kofi.support')}
          </a>
        </div>
        <button
          type="button"
          onClick={acknowledge}
          aria-label={t('kofi.dismiss')}
          className="flex-shrink-0 w-7 h-7 -mt-1 -mr-1 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors focus-ring"
        >
          <X size={16} />
        </button>
      </div>
    </aside>
  )
}
