/**
 * KofiSupportCard: a dismissible corner card inviting admins to support UCM, in the gabarit of the
 * mockup's floating card (its session banner), shown once per UCM version; `inline` puts it in the
 * page flow, where it covers nothing. The dismissed version is a server-side
 * preference (`kofi_seen_version`), so it follows the user across browsers.
 */
import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Coffee } from '@phosphor-icons/react'
import { Icon } from './atelier/Icon'
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

export function KofiSupportCard({ version = __APP_VERSION__, inline = false }) {
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

  const card = (
    <aside aria-label={t('kofi.label')} className={`session-banner kofi-card${inline ? ' kofi-inline' : ''}`}>
      <Coffee className="icon" weight="bold" aria-hidden="true" />
      <p><span>{t('kofi.message')}</span></p>
      <a href={KOFI_URL} target="_blank" rel="noopener noreferrer" onClick={acknowledge} className="btn primary kofi-button">
        {t('kofi.support')}
      </a>
      <button type="button" className="icon-btn quiet" onClick={acknowledge} aria-label={t('kofi.dismiss')}>
        <Icon name="close" />
      </button>
    </aside>
  )
  // In a zone (the overview) the scope is there; floating over another page, the card carries its own
  return inline ? card : <div className="atl atl-island">{card}</div>
}
