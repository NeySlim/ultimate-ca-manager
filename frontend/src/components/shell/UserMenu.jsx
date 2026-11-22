/**
 * Account menu, the mockup's userMenu(): identity, then My account and Sign out. Deviations asked by the
 * maintainer: the identity is the lock screen's account card (.auth-user: the avatar's initials, the name,
 * role and login) over the session's facts read from the server at each opening (e-mail, sign-in method
 * and provider, second factors, inactivity lock and end of the session, as .props); Settings after
 * My account for who may see it, a separator before Lock (also Alt+Shift+L) and Sign out. The language is
 * chosen from the bar's globe menu (from this menu on a phone), the account preferences and the sign-in pages.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { Facts } from '../atelier/Detail'
import { useAuth } from '../../contexts/AuthContext'
import { languages } from '../../i18n'
import { chooseLanguage } from '../../lib/chooseLanguage'
import { glyphOf, isVisible, menuLabelKey, moduleById } from '../../navigation/registry'
import { authService } from '../../services/auth.service'
import { formatDate } from '../../lib/utils'
import { useDisclosure, moveFocus } from './useDisclosure'

// The mockup's methods; a session the server cannot name ('session') says the lock alone
const METHOD_KEYS = {
  password: 'shell.method.password',
  mtls: 'shell.method.mtls',
  certificate: 'shell.method.mtls',
  webauthn: 'shell.method.webauthn',
  sso: 'shell.method.sso',
  ldap: 'shell.method.ldap',
}

const initialsOf = (name) => (name || '?').slice(0, 2).toUpperCase()
const roleKey = (role) => (role === 'admin' ? 'users.admin' : `common.${role}`)

const FACTOR_KEYS = { totp: 'shell.mfaMethod.totp', webauthn: 'shell.method.webauthn' }

// What the server knows of this session (GET /auth/verify), read again at each opening
const readFacts = () => authService.getCurrentUser()
  .then(res => {
    const data = res?.data ?? res ?? {}
    return {
      method: data.auth_method || null,
      provider: data.auth_provider || null,
      mfa: data.mfa || null,
      idle: Number(data.session?.idle_timeout_s ?? data.session_timeout) || null,
      endsAt: data.session?.expires_at || null,
    }
  })
  .catch(() => null)

// The shortcut of Lock: Alt+Shift+L (Option+Shift+L on a Mac), left to a text field, where it may type a character
const isLockKey = (e) => e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && (e.code === 'KeyL' || e.key?.toLowerCase() === 'l')
const inTextField = (el) => el?.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el?.tagName)

export function UserMenu({ can }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { user, logout, lock, authMethod } = useAuth()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const [facts, setFacts] = useState(null)
  const username = user?.username || 'User'
  const name = user?.full_name || username
  const email = user?.email || ''
  const initials = initialsOf(username)
  const role = user?.role ? t(roleKey(user.role), { defaultValue: user.role }) : ''
  const items = () => [...(panelRef.current?.querySelectorAll('a, button') || [])]
  // Without a `can` nothing proves the right: no Settings entry
  const settings = moduleById('settings')
  const showSettings = !!can && isVisible(settings, can)

  useEffect(() => {
    if (!open) return undefined
    items()[0]?.focus()
    let alive = true
    readFacts().then(f => { if (alive && f) setFacts(f) })
    return () => { alive = false }
  }, [open])

  const lockRef = useRef(lock)
  lockRef.current = lock
  useEffect(() => {
    const onKey = (e) => {
      if (!isLockKey(e) || e.defaultPrevented || inTextField(e.target)) return
      e.preventDefault()
      lockRef.current?.('manual')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    // The language list keeps its own arrows
    if (open && panelRef.current?.contains(e.target) && e.target.tagName !== 'SELECT') moveFocus(e, items())
  }

  const handleLock = () => {
    close()
    lock('manual')
  }

  const handleLogout = async () => {
    close()
    await logout()
    navigate('/login')
  }

  // The server's answer wins: a reload left the context with no method, or 'session'
  const via = facts?.method && facts.method !== 'session' ? facts.method : authMethod
  const methodName = !via || via === 'session' ? null : METHOD_KEYS[via] ? t(METHOD_KEYS[via]) : via
  const method = methodName && facts?.provider ? t('shell.userCard.methodVia', { method: methodName, provider: facts.provider }) : methodName
  const mfaOn = !!(facts?.mfa?.enabled && facts.mfa.methods?.length)
  const factors = facts?.mfa
    ? (mfaOn
      ? t('shell.userCard.mfaOn', { methods: facts.mfa.methods.map(m => (FACTOR_KEYS[m] ? t(FACTOR_KEYS[m]) : m)).join(', ') })
      : t('shell.userCard.mfaOff'))
    : null
  const minutes = facts?.idle ? Math.round(facts.idle / 60) : null
  const endsAt = facts?.endsAt ? formatDate(facts.endsAt, { time: true }) : null

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
        {initials}
      </button>
      <div className="pop-menu user-menu" id="user-menu" ref={panelRef} hidden={!open}>
        <div className="user-id">
          <p className="auth-user">
            <span className="avatar" aria-hidden="true">{initials}</span>
            <span>
              <strong id="user-name">{name}</strong>
              <span id="user-role">{role && <>{role} · </>}<span className="mono">{username}</span></span>
            </span>
          </p>
          {(email || method || factors || minutes || endsAt) ? (
            <Facts className="user-facts" items={[
              email && [t('common.email'), email],
              method && [t('shell.userCard.signIn'), method],
              // Second factors off: a neutral state, no policy here says it should be on
              factors && { label: t('shell.userCard.mfa'), ...(mfaOn ? { value: factors } : { state: ['muted', factors] }) },
              (minutes || endsAt) && {
                label: t('shell.userCard.session'), long: true,
                value: minutes ? t('shell.userCard.lockIn', { minutes }) : t('shell.userCard.endsAt', { date: endsAt }),
                sub: minutes && endsAt ? t('shell.userCard.endsAt', { date: endsAt }) : undefined,
              },
            ]} />
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
        <div role="separator" className="pop-sep" />
        <button type="button" className="pop-item" id="user-lock" data-action="lock" aria-keyshortcuts="Alt+Shift+L" onClick={handleLock}>
          <Icon name="lock" />{t('shell.lock')}
        </button>
        <button type="button" className="pop-item" id="user-logout" data-action="logout" onClick={handleLogout}>
          <Icon name="logout" />{t('shell.signOut')}
        </button>
      </div>
    </div>
  )
}
