/**
 * Account menu: identity, sign-in method, account and settings, the theme and
 * language choices the old sidebar menu carried, and sign out.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { UserCircle, Gear, SignOut, Check } from '@phosphor-icons/react'
import { useAuth } from '../../contexts/AuthContext'
import { useTheme } from '../../contexts/ThemeContext'
import { persistPreference } from '../../stores/userPreferencesStore'
import { isVisible, moduleById } from '../../navigation/registry'
import { languages } from '../../i18n'
import { useDisclosure, moveFocus } from './useDisclosure'

const MODES = [
  { id: 'system', labelKey: 'settings.followSystem' },
  { id: 'dark', labelKey: 'settings.dark' },
  { id: 'light', labelKey: 'settings.light' },
]
const METHOD_KEYS = {
  password: 'shell.method.password',
  mtls: 'shell.method.mtls',
  webauthn: 'shell.method.webauthn',
  session: 'shell.method.session',
}

const initialsOf = (name) => (name || '?').slice(0, 2).toUpperCase()

export function UserMenu({ can }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { user, logout, authMethod } = useAuth()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const username = user?.username || 'User'
  const lang = i18n.language?.split('-')[0] || 'en'
  const showSettings = isVisible(moduleById('settings'), can)
  const items = () => [...(panelRef.current?.querySelectorAll('a, button') || [])]

  useEffect(() => {
    if (open) items()[0]?.focus()
  }, [open])

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    if (open && panelRef.current?.contains(e.target)) moveFocus(e, items())
  }

  const handleLogout = async () => {
    close()
    await logout()
    navigate('/login')
  }

  const pickLanguage = (code) => {
    i18n.changeLanguage(code)
    try { localStorage.setItem('i18nextLng', code) } catch { /* storage is optional */ }
    persistPreference('language', code)
  }

  return (
    <div className="shell-pop-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-avatar"
        aria-expanded={open}
        aria-controls="shell-user-menu"
        aria-label={`${t('common.account')}: ${username}`}
        onClick={() => setOpen(!open)}
      >
        {initialsOf(username)}
      </button>
      <div id="shell-user-menu" ref={panelRef} className="shell-pop" hidden={!open}>
        <div className="shell-user-id">
          <strong>{username}</strong>
          <span>{user?.role || ''}</span>
          {authMethod && (
            <span className="shell-muted">
              {t('shell.signedInWith', { method: METHOD_KEYS[authMethod] ? t(METHOD_KEYS[authMethod]) : authMethod })}
            </span>
          )}
        </div>
        <Link to="/account" className="shell-pop-item" onClick={() => close()}>
          <UserCircle size={16} aria-hidden="true" />{t('common.account')}
        </Link>
        {showSettings && (
          <Link to="/settings" className="shell-pop-item" onClick={() => close()}>
            <Gear size={16} aria-hidden="true" />{t('common.settings')}
          </Link>
        )}

        <div role="group" aria-label={t('settings.colorTheme')} className="shell-pop-group">
          <span className="shell-pop-label">{t('settings.colorTheme')}</span>
          {themes.map(theme => (
            <button key={theme.id} type="button" className="shell-pop-item" aria-pressed={themeFamily === theme.id}
              onClick={() => setThemeFamily(theme.id)}>
              <span className="shell-swatch" style={{ background: theme.accent }} aria-hidden="true" />
              <span className="shell-grow">{t(theme.nameKey)}</span>
              {themeFamily === theme.id && <Check size={14} weight="bold" aria-hidden="true" />}
            </button>
          ))}
        </div>
        <div role="group" aria-label={t('settings.appearanceMode')} className="shell-pop-group">
          <span className="shell-pop-label">{t('settings.appearanceMode')}</span>
          {MODES.map(opt => (
            <button key={opt.id} type="button" className="shell-pop-item" aria-pressed={mode === opt.id}
              onClick={() => setMode(opt.id)}>
              <span className="shell-grow">{t(opt.labelKey)}</span>
              {mode === opt.id && <Check size={14} weight="bold" aria-hidden="true" />}
            </button>
          ))}
        </div>
        <div role="group" aria-label={t('settings.language')} className="shell-pop-group">
          <span className="shell-pop-label">{t('settings.language')}</span>
          {languages.map(l => (
            <button key={l.code} type="button" className="shell-pop-item" aria-pressed={lang === l.code}
              onClick={() => pickLanguage(l.code)}>
              <span aria-hidden="true">{l.flag}</span>
              <span className="shell-grow">{l.name}</span>
              {lang === l.code && <Check size={14} weight="bold" aria-hidden="true" />}
            </button>
          ))}
        </div>

        <button type="button" className="shell-pop-item shell-danger" onClick={handleLogout}>
          <SignOut size={16} aria-hidden="true" />{t('auth.logout')}
        </button>
      </div>
    </div>
  )
}
