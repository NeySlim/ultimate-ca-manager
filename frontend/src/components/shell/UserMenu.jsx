/**
 * Account menu, the mockup's userMenu(): identity (name, role and login), the sign-in method with
 * the inactivity lock, then My account and Sign out. Deviation asked by the maintainer: Settings
 * between them, for who may see the Settings module. The language is chosen from the bar's globe
 * menu (from this menu on a phone), the account preferences and the sign-in pages.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { useAuth } from '../../contexts/AuthContext'
import { languages } from '../../i18n'
import { chooseLanguage } from '../../lib/chooseLanguage'
import { glyphOf, isVisible, menuLabelKey, moduleById } from '../../navigation/registry'
import { authService } from '../../services/auth.service'
import { useDisclosure, moveFocus } from './useDisclosure'

// The mockup's methods; a session restored from the browser ('session') no longer knows its own,
// so the menu then says the lock alone
const METHOD_KEYS = {
  password: 'shell.method.password',
  mtls: 'shell.method.mtls',
  webauthn: 'shell.method.webauthn',
}

const initialsOf = (name) => (name || '?').slice(0, 2).toUpperCase()
const roleKey = (role) => (role === 'admin' ? 'users.admin' : `common.${role}`)

// The inactivity timeout of the server (seconds), read once per page load
let timeoutRead = null
const readTimeout = () => {
  timeoutRead ||= authService.getCurrentUser()
    .then(res => Number((res?.data ?? res)?.session_timeout) || null)
    .catch(() => { timeoutRead = null; return null })
  return timeoutRead
}

export function UserMenu({ can }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { user, logout, authMethod } = useAuth()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const [minutes, setMinutes] = useState(null)
  const username = user?.username || 'User'
  const name = user?.full_name || username
  const role = user?.role ? t(roleKey(user.role), { defaultValue: user.role }) : ''
  const items = () => [...(panelRef.current?.querySelectorAll('a, button') || [])]
  // Without a `can` nothing proves the right: no Settings entry
  const settings = moduleById('settings')
  const showSettings = !!can && isVisible(settings, can)

  useEffect(() => {
    if (!open) return undefined
    items()[0]?.focus()
    let alive = true
    readTimeout().then(s => { if (alive && s) setMinutes(Math.round(s / 60)) })
    return () => { alive = false }
  }, [open])

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    // The language list keeps its own arrows
    if (open && panelRef.current?.contains(e.target) && e.target.tagName !== 'SELECT') moveFocus(e, items())
  }

  const handleLogout = async () => {
    close()
    await logout()
    navigate('/login')
  }

  const method = !authMethod || authMethod === 'session' ? null : METHOD_KEYS[authMethod] ? t(METHOD_KEYS[authMethod]) : authMethod

  const label = role ? t('shell.accountLabel', { name, role }) : t('shell.accountLabelName', { name })
  return (
    <div className="pop-wrap user-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="avatar"
        id="user-button"
        data-action="user-menu"
        aria-expanded={open}
        aria-controls="user-menu"
        aria-label={label}
        title={name}
        onClick={() => setOpen(!open)}
      >
        {initialsOf(username)}
      </button>
      <div className="pop-menu user-menu" id="user-menu" ref={panelRef} hidden={!open}>
        <div className="user-id">
          <strong id="user-name">{name}</strong>
          <span id="user-role">{role && <>{role} · </>}<span className="mono">{username}</span></span>
          {method || minutes ? (
            <span className="muted">
              {method && t('shell.signedInWith', { method })}
              {method && minutes ? ' ' : null}
              {minutes ? t('shell.lockAfter', { count: minutes }) : null}
            </span>
          ) : null}
        </div>
        {/* On a phone the bar has no room for the language menu: it moves here (adjust.css) */}
        <div className="pop-item user-lang">
          <Icon name="globe" /><label className="pop-label" htmlFor="user-language">{t('settings.language')}</label>
          <select id="user-language" value={i18n.language?.split('-')[0] || 'en'} onChange={(e) => { chooseLanguage(i18n, e.target.value); close(true) }}>
            {languages.map(l => <option key={l.code} value={l.code} lang={l.code}>{l.name}</option>)}
          </select>
        </div>
        <button type="button" className="pop-item" id="user-account" data-action="my-account" onClick={() => { close(); navigate('/account') }}>
          <Icon name="users" />{t('common.account')}
        </button>
        {showSettings && (
          <button type="button" className="pop-item" id="user-settings" data-action="settings" onClick={() => { close(); navigate(settings.path) }}>
            <Icon name={glyphOf(settings)} />{t(menuLabelKey(settings))}
          </button>
        )}
        <button type="button" className="pop-item" id="user-logout" data-action="logout" onClick={handleLogout}>
          <Icon name="logout" />{t('shell.signOut')}
        </button>
      </div>
    </div>
  )
}
