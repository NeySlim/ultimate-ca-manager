/**
 * Auth Context - Global authentication state
 * 
 * On mount, ALWAYS calls /auth/verify to check for active session.
 * This enables mTLS auto-login: the middleware creates the session
 * during the TLS handshake, and checkSession() picks it up.
 */
import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { authService } from '../services/auth.service'
import { accountService } from '../services/account.service'
import { apiClient } from '../services/apiClient'
import { setAppTimezone } from '../stores/timezoneStore'
import { saveLock, markJustLocked, markSignedOut, announceLock, listenForLocks, shareLock, readSharedLock, clearSharedLock, setTabAccount } from '../lib/sessionLock'
import { setDateFormat, setShowTime } from '../stores/dateFormatStore'
import { applyServerPreferences, getPreferences, setAuthenticated as setPrefsAuthenticated } from '../stores/userPreferencesStore'
import i18n from '../i18n'
import { setDraftOwner, signOutDrafts } from '../lib/draftMemory'

const AuthContext = createContext()

const debug = import.meta.env.DEV ? console.log : () => {}

// The language to show is the merged one: a choice made while loading wins.
function applyPreferences(prefs) {
  applyServerPreferences(prefs)
  const language = getPreferences().language
  if (language && language !== i18n.language) {
    try { i18n.changeLanguage(language) } catch { /* noop */ }
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sessionChecked, setSessionChecked] = useState(false)
  const [permissions, setPermissions] = useState([])
  const [role, setRole] = useState(null)
  // How this session was opened; a restore only knows it is a session
  const [authMethod, setAuthMethod] = useState(null)
  const [forcePasswordChange, setForcePasswordChange] = useState(false)
  // #141: session authenticated but must enrol TOTP before full access.
  const [mustEnroll2fa, setMustEnroll2fa] = useState(false)

  // The lock, by hand ('manual') or after inactivity ('idle'): the console goes at once, the
  // account is kept for the lock screen, the server session is closed after (it may not answer)
  // and the other tabs of this browser, which share the session, lock too.
  const current = useRef({ user: null, authMethod: null })
  current.current = { user, authMethod }
  // A lock heard while this tab still checks its session: applied to the account the check finds
  const checking = useRef(false)
  const pendingLock = useRef(null)

  const lockHere = useCallback((reason) => {
    const { user: who, authMethod: via } = current.current
    // A custom role is kept by its name; a built-in one by its code, named on the lock screen
    const account = { username: who?.username, name: who?.full_name, role: who?.custom_role_name || who?.role, method: via, reason }
    saveLock(account)
    markJustLocked()
    current.current = { user: null, authMethod: null }
    setUser(null)
    setIsAuthenticated(false)
    setPermissions([])
    setRole(null)
    setAuthMethod(null)
    setForcePasswordChange(false)
    setMustEnroll2fa(false)
    setPrefsAuthenticated(false)
    return account
  }, [])

  // The session found gone in a tab of an account locked in another tab: its lock screen
  const lockedElsewhere = useCallback(() => {
    const who = current.current.user?.username
    const shared = who ? readSharedLock() : null
    return shared?.username === who ? shared : null
  }, [])

  const checkSession = useCallback(async () => {
    checking.current = true
    try {
      debug('🔍 Checking session...')
      const response = await authService.getCurrentUser()

      const userData = response.data || response
      // A 200 that is not the API (captive portal, proxy maintenance page)
      if (!userData || typeof userData !== 'object') return null

      if (!userData.authenticated) {
        debug('ℹ️ Not authenticated')
        const shared = lockedElsewhere()
        if (shared) {
          lockHere(shared.reason)
          return false
        }
        setUser(null)
        setIsAuthenticated(false)
        setPermissions([])
        setRole(null)
        setAuthMethod(null)
        setMustEnroll2fa(false)
        setForcePasswordChange(false)
        setPrefsAuthenticated(false)
        return false
      }

      const who = userData.user || userData
      // The ref follows at once: a lock message between this answer and the next render is kept
      current.current = { user: who, authMethod: current.current.authMethod || userData.auth_method || null }
      const pending = pendingLock.current
      pendingLock.current = null
      // The server answered before a lock another tab made reached it
      if (pending && pending.username === who?.username) {
        lockHere(pending.reason)
        return false
      }
      setUser(who)
      setIsAuthenticated(true)
      setPermissions(userData.permissions || [])
      setRole(userData.role || null)
      setAuthMethod(prev => prev || userData.auth_method || null)
      setMustEnroll2fa(userData.must_enroll_2fa || false)
      // A session restore must reach the same conclusion the login response
      // did. Without this a reload — and every SSO login, which reaches the
      // SPA through /verify after the sso-complete redirect — cleared the
      // forced password change and skipped the modal that enforces it.
      setForcePasswordChange(userData.force_password_change || false)
      if (userData.timezone) setAppTimezone(userData.timezone)
      if (userData.date_format) setDateFormat(userData.date_format)
      if (userData.show_time !== undefined) setShowTime(userData.show_time !== false)
      // Apply server-side UI preferences (issue #73)
      setPrefsAuthenticated(true)
      applyPreferences(userData.preferences || {})
      debug('✅ Session valid:', userData.user?.username)
      return true
    } catch (error) {
      debug('❌ Session check failed:', error.message)
      // An unreachable server (network down, restart) says nothing about the
      // session: keep the current state and answer null, "unknown"
      if (error?.status !== 401 && error?.status !== 403) return null
      const shared = lockedElsewhere()
      if (shared) {
        lockHere(shared.reason)
        return false
      }
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      setAuthMethod(null)
      setMustEnroll2fa(false)
      setPrefsAuthenticated(false)
      return false
    } finally {
      checking.current = false
      pendingLock.current = null
      setLoading(false)
      setSessionChecked(true)
    }
  }, [lockHere, lockedElsewhere])

  // Always check session on mount — enables mTLS auto-login on /login too
  useEffect(() => {
    checkSession()
  }, [checkSession])

  const login = async (username, password, preAuthData = null) => {
    setLoading(true)
    try {
      debug('🔐 Login called:', { username, hasPreAuthData: !!preAuthData })
      
      let response
      if (preAuthData) {
        // Already authenticated via multi-method (mTLS, WebAuthn, etc.)
        response = { data: preAuthData }
        // Store CSRF token from pre-auth response
        const csrfToken = preAuthData.csrf_token
        if (csrfToken) {
          apiClient.setCsrfToken(csrfToken)
        }
      } else {
        // Legacy password auth
        debug('🔐 Attempting password login for:', username)
        response = await authService.login(username, password)
      }
      
      debug('✅ Login response:', response)
      const userData = response.data?.user || response.user || { username }
      // Signed in again: no tab takes the lock made before any more
      clearSharedLock()
      current.current = { user: userData, authMethod: response.data?.auth_method || response.auth_method || null }
      setUser(userData)
      setIsAuthenticated(true)
      setPermissions(response.data?.permissions || response.permissions || [])
      setRole(response.data?.role || response.role || null)
      setAuthMethod(response.data?.auth_method || response.auth_method || null)
      setForcePasswordChange(response.data?.force_password_change || false)
      // Apply display settings from login response (timezone, date_format, show_time)
      const loginData = response.data || response
      // #141: forced-2FA-enrolment flag from the login response.
      setMustEnroll2fa(loginData.requires_2fa_enrollment || loginData.must_enroll_2fa || false)
      if (loginData.timezone) setAppTimezone(loginData.timezone)
      if (loginData.date_format) setDateFormat(loginData.date_format)
      if (loginData.show_time !== undefined) setShowTime(loginData.show_time !== false)
      // Apply server-side UI preferences (issue #73). Most login endpoints
      // don't include them, so we fetch them once auth is established.
      setPrefsAuthenticated(true)
      const loadPreferences = async () => {
        const prefsResp = await accountService.getPreferences()
        applyPreferences(prefsResp?.data || prefsResp || {})
      }
      try {
        await loadPreferences()
      } catch {
        // One retry; if it fails too, changes stay local until a later load.
        try { await loadPreferences() } catch { /* noop */ }
      }
      debug('✅ User authenticated:', userData)
      return response
    } catch (error) {
      debug('❌ Login failed:', error.message)
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      throw error
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    setLoading(true)
    // Unsaved drafts of the pages never outlive the session
    signOutDrafts()
    clearSharedLock()
    try {
      debug('🔓 Logging out...')
      await authService.logout()
      debug('✅ Logout successful')
    } catch (error) {
      debug('❌ Logout error:', error)
    } finally {
      // Always clear local state regardless of API success
      setUser(null)
      setIsAuthenticated(false)
      setPermissions([])
      setRole(null)
      setAuthMethod(null)
      setForcePasswordChange(false)
      setMustEnroll2fa(false)
      setPrefsAuthenticated(false)
      setLoading(false)
      markSignedOut()
      debug('🔓 Local session cleared')
    }
  }

  const lock = (reason = 'idle') => {
    const account = lockHere(reason)
    shareLock(account)
    announceLock(account.username, reason)
    authService.lock(reason).catch(() => {})
  }

  useEffect(() => listenForLocks(({ username, reason }) => {
    const who = current.current.user?.username
    if (who === username) lockHere(reason)
    else if (!who && checking.current) pendingLock.current = { username, reason }
  }), [lockHere])

  // Back to the foreground after missing the message: the server says whether the session is gone
  useEffect(() => {
    const onVisible = async () => {
      if (document.visibilityState !== 'visible') return
      const who = current.current.user?.username
      const shared = lockedElsewhere()
      if (!shared) return
      let open
      try {
        const response = await authService.getCurrentUser()
        open = (response?.data || response)?.authenticated === true
      } catch (error) {
        open = error?.status !== 401 && error?.status !== 403
      }
      if (!open && current.current.user?.username === who) lockHere(shared.reason)
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [lockHere, lockedElsewhere])

  const clearForcePasswordChange = () => setForcePasswordChange(false)

  // Drafts kept for the tab belong to one account: another one signing in drops them
  useEffect(() => { setDraftOwner(user?.username) }, [user?.username])
  // A request refused outside this context (apiClient) finds the account of the tab here
  useEffect(() => {
    setTabAccount(user ? { username: user.username, name: user.full_name, role: user.custom_role_name || user.role, method: authMethod } : null)
  }, [user, authMethod])

  const value = {
    user,
    isAuthenticated,
    loading,
    sessionChecked,
    permissions,
    role,
    authMethod,
    forcePasswordChange,
    mustEnroll2fa,
    login,
    logout,
    lock,
    checkSession,
    clearForcePasswordChange,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
