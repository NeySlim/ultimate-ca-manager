/**
 * Account menu, as the mockup draws it: identity (name, role and login), the sign-in method with
 * the inactivity lock, then My account and Sign out. The language is chosen in the account
 * preferences and on the sign-in page; Settings is reached from the Modules menu and the palette.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Users, SignOut } from '@phosphor-icons/react'
import { useAuth } from '../../contexts/AuthContext'
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

export function UserMenu() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, logout, authMethod } = useAuth()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const [minutes, setMinutes] = useState(null)
  const username = user?.username || 'User'
  const name = user?.full_name || username
  const role = user?.role ? t(roleKey(user.role), { defaultValue: user.role }) : ''
  const items = () => [...(panelRef.current?.querySelectorAll('a, button') || [])]

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
    if (open && panelRef.current?.contains(e.target)) moveFocus(e, items())
  }

  const handleLogout = async () => {
    close()
    await logout()
    navigate('/login')
  }

  const method = !authMethod || authMethod === 'session' ? null : METHOD_KEYS[authMethod] ? t(METHOD_KEYS[authMethod]) : authMethod

  return (
    <div className="shell-pop-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-avatar"
        aria-expanded={open}
        aria-controls="shell-user-menu"
        aria-label={role ? t('shell.accountLabel', { name, role }) : t('shell.accountLabelName', { name })}
        title={name}
        onClick={() => setOpen(!open)}
      >
        {initialsOf(username)}
      </button>
      <div id="shell-user-menu" ref={panelRef} className="shell-pop shell-user-menu" hidden={!open}>
        <div className="shell-user-id">
          <strong>{name}</strong>
          <span>{role && <>{role} · </>}<span className="shell-mono">{username}</span></span>
          {method || minutes ? (
            <span className="shell-muted">
              {method && t('shell.signedInWith', { method })}
              {method && minutes ? ' ' : null}
              {minutes ? t('shell.lockAfter', { count: minutes }) : null}
            </span>
          ) : null}
        </div>
        <Link to="/account" className="shell-pop-item" onClick={() => close()}>
          <Users size={17} aria-hidden="true" />{t('common.account')}
        </Link>
        <button type="button" className="shell-pop-item" onClick={handleLogout}>
          <SignOut size={17} aria-hidden="true" />{t('shell.signOut')}
        </button>
      </div>
    </div>
  )
}
