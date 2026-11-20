/**
 * Sign-in page and lock screen, in the sign-in frame.
 *
 * AuthContext.checkSession() runs on mount (mTLS auto-login lands in the console
 * at once). Otherwise the page goes: init → form (username and password, or one of
 * the other doors: SSO, LDAP, client certificate, security key) → 2fa when asked.
 * A session locked after inactivity (lib/sessionLock) shows the same form for the
 * same account, read-only username, and returns to ?next= once signed in again.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { CaretRight, Lock, Key, Fingerprint, Eye, EyeSlash, Warning, Database } from '@phosphor-icons/react'
import { useAuth, useNotification } from '../contexts'
import { AuthFrame, AuthField } from '../components/auth/AuthFrame'
import { authMethodsService } from '../services/auth-methods.service'
import { authService } from '../services/auth.service'
import { safeNext } from '../navigation/safeNext'
import { readLock, clearLock, takeJustLocked } from '../lib/sessionLock'
import { roleLabel, roleInSentence } from '../lib/roleLabel'
import { focusPageTitle } from '../lib/focusPageTitle'
import {
  NO_ANSWER_RETRY_S, NO_ANSWER_TRIES, isMaintenanceRefusal, isNoAnswer, isRestoreMaintenance, maintenanceRetrySeconds,
} from './loginMaintenance'

const STORAGE_KEY = 'ucm_last_username'
const STORAGE_AUTH_METHOD_KEY = 'ucm_last_auth_method'
const SSO_RETRY_BASE_MS = 2000
const SSO_RETRY_MAX_MS = 30000
const NO_EVENT = { preventDefault() {} }
const PROTOCOLS = { oauth2: 'OAuth 2.0', saml: 'SAML 2.0', ldap: 'LDAP' }

const toProviderList = (ssoData) => (Array.isArray(ssoData?.data) ? ssoData.data : [])
const providerName = (p) => p.display_name || p.name
// The design's two offset busts (its `users` icon), drawn like its other strokes
function SsoIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20a6 6 0 0 1 12 0M16 4.5a3.5 3.5 0 0 1 0 7m2 2.5a6 6 0 0 1 3 6" />
    </svg>
  )
}

const initialsOf = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()

// The LDAP provider the saved username last signed in with, if still offered
const savedLdapProvider = (providers) => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_AUTH_METHOD_KEY) || '{}')
    if (saved.method !== 'ldap' || !saved.providerId) return null
    return providers.find(p => p.id === saved.providerId) || null
  } catch {
    return null
  }
}

export default function LoginPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // Where to go after signing in: a known internal page from ?next=, else the dashboard.
  const requested = safeNext(searchParams.get('next'))
  const landing = requested || '/dashboard'
  const [rateLimit, setRateLimit] = useState(null)
  // { restoring, seconds }: seconds counts down to the next attempt, null when none is planned
  const [maintenance, setMaintenance] = useState(null)
  const maintenanceRetry = useRef(null)
  // The maintenance waited out, kept across its planned attempts: { restoring, lost }
  const outage = useRef(null)
  const latestAttempt = useRef({})
  const { login, sessionChecked } = useAuth()
  const { showSuccess, showInfo } = useNotification()
  const passwordRef = useRef(null)
  const usernameRef = useRef(null)
  const codeRef = useRef(null)
  const titleRef = useRef(null)

  // The account of a session locked after inactivity: unlocked by the same account only
  const [locked, setLocked] = useState(readLock)
  const lockedRef = useRef(locked)
  lockedRef.current = locked

  // State machine: 'init' | 'form' | '2fa' | 'ldap'
  const [step, setStep] = useState('init')
  const [username, setUsername] = useState(() => locked?.username || '')
  // Read by the SSO retry, which outlives the render that started it
  const stepRef = useRef(step)
  stepRef.current = step
  const [password, setPassword] = useState('')
  const [reveal, setReveal] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [twoFactorMethods, setTwoFactorMethods] = useState(['totp'])
  // Which door asked for the second factor: 'password' or 'ldap'
  const twoFactorFrom = useRef('password')
  const [loading, setLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  // One message for the attempt refused, shown in the card; field errors beside their field
  const [formError, setFormError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [emailConfigured, setEmailConfigured] = useState(false)
  // The field to focus once the form is enabled again (after a refusal or a switch of account)
  const [focusNext, setFocusNext] = useState(null)
  // A polite announcement of the page itself (the lock that just happened)
  const [announce, setAnnounce] = useState('')
  const arrivedLocked = useRef(Boolean(locked) && takeJustLocked())
  const [globalMethods, setGlobalMethods] = useState(null)
  const [preferKey, setPreferKey] = useState(false)
  // The user has started on the form: a late provider load no longer switches it
  const touched = useRef(false)

  // SSO state
  const [ssoProviders, setSsoProviders] = useState([])
  const [ssoLoadFailed, setSsoLoadFailed] = useState(false)
  const [selectedLdapProvider, setSelectedLdapProvider] = useState(null)

  // Save helpers
  const saveUsername = (name) => {
    if (name) {
      try { localStorage.setItem(STORAGE_KEY, name) } catch {}
    }
  }
  const saveAuthMethod = (method, providerId = null) => {
    try { localStorage.setItem(STORAGE_AUTH_METHOD_KEY, JSON.stringify({ method, providerId })) } catch {}
  }
  const saveTwoFactorMethod = () => {
    if (twoFactorFrom.current === 'ldap') saveAuthMethod('ldap', selectedLdapProvider?.id)
    else saveAuthMethod('password')
  }

  const getSavedAuthMethod = () => {
    try { return JSON.parse(localStorage.getItem(STORAGE_AUTH_METHOD_KEY) || '{}').method || null } catch { return null }
  }

  // The design's greeting: the account's name and role, as far as the answer gives them
  const welcome = (userData, who) => {
    const u = userData?.user || {}
    const name = u.full_name || u.username || who || ''
    const role = roleInSentence(t, u.custom_role_name || u.role, i18n?.language)
    showSuccess(role ? t('auth.page.signedIn', { name, role }) : t('auth.page.signedInNoRole', { name }))
  }

  // Signed in: the lock is lifted; another account than the locked one starts on the dashboard
  const finish = (who) => {
    const lockedAs = lockedRef.current?.username
    clearLock()
    navigate(lockedAs && who && who !== lockedAs ? '/dashboard' : landing)
    focusPageTitle()
  }

  // ═══════════════════════════════════════════════════
  // INIT: After AuthContext finishes session check,
  // if we're still here (not auto-logged in), detect methods
  // ═══════════════════════════════════════════════════
  useEffect(() => {
    if (!sessionChecked) return

    // Load saved username (the locked account wins)
    let lastUsername = ''
    try { lastUsername = localStorage.getItem(STORAGE_KEY) || '' } catch {}
    if (lastUsername && !lockedRef.current) setUsername(lastUsername)
    setPreferKey(Boolean(lastUsername) && getSavedAuthMethod() === 'webauthn')

    // Check email config
    authService.isEmailConfigured()
      .then(data => setEmailConfigured(data?.data?.configured === true))
      .catch(() => {})

    // Load SSO providers + detect global auth methods in parallel.
    // Settled independently: a failed /auth/methods must not discard the
    // providers, and a failed /sso/available is retried by the effect below.
    Promise.allSettled([
      authService.getSsoProviders(),
      authMethodsService.detectMethods(null)
    ]).then(([ssoResult, methodsResult]) => {
      // SSO providers
      let providers = []
      if (ssoResult.status === 'fulfilled') {
        providers = toProviderList(ssoResult.value)
      } else {
        setSsoLoadFailed(true)
      }
      setSsoProviders(providers)

      // Global methods (no username - detects cert presence)
      const methods = methodsResult.status === 'fulfilled' ? methodsResult.value : null
      setGlobalMethods(methods)

      // Restore saved LDAP provider
      const ldapProvider = lastUsername ? savedLdapProvider(providers) : null
      if (ldapProvider) {
        setSelectedLdapProvider(ldapProvider)
        if (!lockedRef.current) {
          setStep('ldap')
          return
        }
      }

      // If mTLS cert present but not enrolled, show info
      if (methods?.mtls && methods.mtls_status === 'present_not_enrolled') {
        showInfo(t('auth.certNotEnrolled'))
      }

      setStep('form')
    }).catch(() => {
      setStep('form')
    })
  }, [sessionChecked]) // eslint-disable-line react-hooks/exhaustive-deps

  // Retry a failed SSO provider load. The page is often reached by an
  // in-app redirect right after the session expired, e.g. when a laptop wakes
  // up before the network is back; without a retry the SSO buttons stay
  // missing until a full reload. Back off, and retry at once when the
  // browser goes online again or the tab becomes visible.
  useEffect(() => {
    if (!ssoLoadFailed) return
    let cancelled = false
    let inFlight = false
    let attempt = 0
    let timer = null

    const retry = () => {
      if (cancelled || inFlight) return
      inFlight = true
      clearTimeout(timer)
      authService.getSsoProviders()
        .then((data) => {
          if (cancelled) return
          const providers = toProviderList(data)
          setSsoProviders(providers)
          setSsoLoadFailed(false)
          // Restore the saved LDAP provider as the first load would have,
          // unless the user has started on something else meanwhile
          let lastUsername = ''
          try { lastUsername = localStorage.getItem(STORAGE_KEY) || '' } catch {}
          const ldapProvider = lastUsername ? savedLdapProvider(providers) : null
          if (ldapProvider && stepRef.current === 'form' && !lockedRef.current && !touched.current) {
            setSelectedLdapProvider(ldapProvider)
            setStep('ldap')
          }
        })
        .catch(() => {
          if (cancelled) return
          attempt += 1
          timer = setTimeout(retry, Math.min(SSO_RETRY_BASE_MS * 2 ** attempt, SSO_RETRY_MAX_MS))
        })
        .finally(() => { inFlight = false })
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') retry()
    }

    timer = setTimeout(retry, SSO_RETRY_BASE_MS)
    window.addEventListener('online', retry)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      clearTimeout(timer)
      window.removeEventListener('online', retry)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [ssoLoadFailed])

  // SSO callback handling
  const [ssoCompleting, setSsoCompleting] = useState(false)
  useEffect(() => {
    const ssoComplete = window.location.pathname.includes('sso-complete')
    if (ssoComplete) {
      setLoading(true)
      setSsoCompleting(true)
      authService.verifySession()
        .then(async (data) => {
          const verifyData = data.data || data
          const who = verifyData?.user?.username
          await login(who || 'sso_user', null, verifyData)
          welcome(verifyData, who)
          finish(who)
        })
        .catch(() => {
          setFormError(t('auth.ssoError'))
          setLoading(false)
          setSsoCompleting(false)
          setStep('form')
        })
      return
    }

    const error = searchParams.get('error')
    if (error) {
      const errorMessages = {
        'provider_disabled': t('auth.ssoProviderDisabled'),
        'invalid_state': t('auth.ssoInvalidState'),
        'token_exchange_failed': t('auth.ssoTokenFailed'),
        'userinfo_failed': t('auth.ssoUserinfoFailed'),
        'no_username': t('auth.ssoNoUsername'),
        'user_creation_failed': t('auth.ssoUserCreationFailed'),
        'auto_create_disabled': t('auth.ssoAutoCreateDisabled'),
        'callback_error': t('auth.ssoCallbackError'),
        'account_disabled': t('auth.accountDisabled'),
        'saml_validation_failed': t('auth.samlValidationFailed'),
        'saml_login_expired': t('auth.samlLoginExpired'),
        'sso_username_conflict': t('auth.ssoUsernameConflict'),
        'sso_unmapped': t('auth.ssoUnmapped'),
        'sso_no_default_role': t('auth.ssoNoDefaultRole'),
        'sso_email_conflict': t('auth.ssoEmailConflict'),
        'saml_logout_rejected': t('auth.samlLogoutRejected'),
      }
      setFormError(errorMessages[error] || t('auth.ssoError'))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Nothing is focused when the page opens; the lock that just happened focuses the title and
  // is announced. Later steps start on their first field to fill.
  const shownStep = useRef('init')
  useEffect(() => {
    const opening = shownStep.current === 'init'
    shownStep.current = step
    if (step === 'init') return
    if (opening) {
      if (arrivedLocked.current) {
        titleRef.current?.focus()
        setAnnounce(t('auth.page.lockedAnnounce'))
      }
      return
    }
    if (step === '2fa') codeRef.current?.focus()
    else if (step === 'form' || step === 'ldap') {
      if (username && step === 'form') passwordRef.current?.focus()
      else usernameRef.current?.focus()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // A field is focused once enabled again: focusing it while disabled would leave the focus on body
  useEffect(() => {
    if (!focusNext || loading) return
    ;({ username: usernameRef, password: passwordRef, code: codeRef })[focusNext]?.current?.focus()
    setFocusNext(null)
  }, [focusNext, loading])

  // ═══════════════════════════════════════════════════
  // AUTH METHOD HANDLERS (standalone, no cascading)
  // ═══════════════════════════════════════════════════

  // Empty fields are named beside their field, the first one gets the focus
  const missing = (fields) => {
    const errors = {}
    for (const [name, value, message] of fields) if (!value) errors[name] = message
    setFieldErrors(errors)
    const first = fields.find(([name]) => errors[name])
    if (first) {
      setFormError('')
      ;({ username: usernameRef, password: passwordRef, code: codeRef })[first[0]]?.current?.focus()
    }
    return Boolean(first)
  }

  const attemptWebAuthn = useCallback(async () => {
    if (missing([['username', username.trim(), t('auth.page.usernameMissing')]])) return
    clearMaintenance()
    setFormError('')
    setStatusMessage(t('auth.touchSecurityKey'))
    setLoading(true)
    try {
      const userData = await authMethodsService.authenticateWebAuthn(username)
      saveUsername(username)
      saveAuthMethod('webauthn')
      await login(username, null, userData)
      welcome(userData, username)
      finish(username)
    } catch (error) {
      setStatusMessage('')
      setLoading(false)
      // A security key is touched again by the user: no attempt is made for them
      if (noteRefusal(error, 'webauthn', false)) return
      if (error.message?.includes('cancelled') || error.message?.includes('abort') || error.name === 'NotAllowedError') {
        showInfo(t('auth.securityKeyCancelled'))
      } else {
        setFormError(error.message || t('auth.invalidCredentials'))
      }
    }
  }, [username, login, navigate, showSuccess, showInfo, t]) // eslint-disable-line react-hooks/exhaustive-deps

  // The server's 429: its Retry-After counted down on screen, the sign-in held until it ends
  const noteRateLimit = (error) => {
    if (error?.status !== 429) { setRateLimit(null); return false }
    const wait = Number.isFinite(error.retryAfter) && error.retryAfter > 0 ? Math.ceil(error.retryAfter) : null
    setRateLimit({ wait, left: wait })
    return true
  }

  useEffect(() => {
    if (!rateLimit?.left) return undefined
    const timer = setTimeout(() => setRateLimit(r => (r?.left ? { ...r, left: r.left - 1 } : r)), 1000)
    return () => clearTimeout(timer)
  }, [rateLimit])
  const waiting = Boolean(rateLimit?.left)

  const clearMaintenance = () => {
    maintenanceRetry.current = null
    outage.current = null
    setMaintenance(null)
  }

  // A 429 or a maintenance's 503 shown in the card (true); `again` names the attempt repeated, by
  // itself after the Retry-After when `auto`, or from the notice's button
  const noteRefusal = (error, again, auto = true) => {
    if (isMaintenanceRefusal(error)) {
      setRateLimit(null)
      setFormError('')
      maintenanceRetry.current = again
      outage.current = { restoring: isRestoreMaintenance(error), lost: 0 }
      setMaintenance({ restoring: isRestoreMaintenance(error), seconds: auto ? maintenanceRetrySeconds(error) : null })
      return true
    }
    // A node that restarts at the end of the maintenance gives no answer: still waited out, a while
    const kept = outage.current
    if (kept && auto && isNoAnswer(error) && kept.lost < NO_ANSWER_TRIES) {
      maintenanceRetry.current = again
      outage.current = { ...kept, lost: kept.lost + 1 }
      setMaintenance({ restoring: kept.restoring, seconds: NO_ANSWER_RETRY_S })
      return true
    }
    clearMaintenance()
    const limited = noteRateLimit(error)
    if (limited) setFormError('')
    return limited
  }

  // Never a second request while one is in flight; each attempt drops the one planned
  const retryNow = () => {
    if (loading) return
    const again = maintenanceRetry.current
    const kept = outage.current
    setMaintenance(m => (m ? { ...m, seconds: null } : m))
    if (!again) return
    latestAttempt.current[again]()
    // The attempt dropped the wait as any attempt does: this one belongs to it
    outage.current = kept
  }

  // The countdown of a planned attempt; one attempt at zero, which plans the next if refused again
  useEffect(() => {
    if (maintenance?.seconds == null) return undefined
    if (maintenance.seconds <= 0) {
      retryNow()
      return undefined
    }
    const timer = setTimeout(() => setMaintenance(m => (m?.seconds != null ? { ...m, seconds: m.seconds - 1 } : m)), 1000)
    return () => clearTimeout(timer)
  }, [maintenance, loading]) // eslint-disable-line react-hooks/exhaustive-deps

  // A refused attempt other than a 429 or a maintenance: the credentials refused (401) in the
  // page's own words, any other answer as the server words it
  const refuse = (error, again, refused, statuses = [401]) => {
    if (noteRefusal(error, again)) return
    setFormError(statuses.includes(error?.status) || !error?.message ? refused : error.message)
  }

  const handlePasswordLogin = async (e) => {
    e.preventDefault()
    if (waiting) return  // the server's wait first, as the disabled button says
    if (missing([
      ['username', username.trim(), t('auth.page.usernameMissing')],
      ['password', password, t('auth.page.passwordMissing')],
    ])) return

    // A locked LDAP account unlocks through its directory
    if (lockedRef.current?.method === 'ldap' && selectedLdapProvider) {
      handleLDAPLogin(NO_EVENT)
      return
    }

    clearMaintenance()
    setFormError('')
    setLoading(true)
    setStatusMessage(t('auth.signingIn'))

    try {
      const userData = await authMethodsService.loginPassword(username, password)
      if (userData.requires_2fa) {
        twoFactorFrom.current = 'password'
        setRateLimit(null)
        setStep('2fa')
        setTwoFactorMethods(userData.methods || ['totp'])
        setTotpCode('')
        setLoading(false)
        setStatusMessage('')
        return
      }
      saveUsername(username)
      saveAuthMethod('password')
      await login(username, password, userData)
      // #141: if 2FA enrolment is enforced, the session is established but
      // restricted; the ForceEnroll2FA overlay takes over after navigation.
      if (!userData.requires_2fa_enrollment) welcome(userData, username)
      finish(username)
    } catch (error) {
      refuse(error, 'password', t('auth.invalidCredentials'))
      if (!maintenanceRetry.current) setPassword('')  // kept while a maintenance is waited out
      setFocusNext('password')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  const handle2FAVerify = async (e) => {
    e.preventDefault()
    if (waiting) return  // the server's wait first, as the disabled button says
    if (missing([['code', totpCode.length >= 6, t('auth.totpCodeRequired')]])) return

    clearMaintenance()
    setFormError('')
    setLoading(true)
    try {
      const userData = await authMethodsService.login2FA(totpCode)
      saveUsername(username)
      saveTwoFactorMethod()
      await login(username, password, userData)
      welcome(userData, username)
      finish(username)
    } catch (error) {
      // A malformed code (400) is refused like a wrong one
      refuse(error, 'totp', t('auth.invalidTotpCode'), [400, 401])
      if (!maintenanceRetry.current) setTotpCode('')
      setFocusNext('code')
    } finally {
      setLoading(false)
    }
  }

  const handle2FAWebAuthn = async () => {
    clearMaintenance()
    setFormError('')
    setLoading(true)
    try {
      const userData = await authMethodsService.login2FAWebAuthn()
      saveUsername(username)
      saveTwoFactorMethod()
      await login(username, password, userData)
      welcome(userData, username)
      finish(username)
    } catch (error) {
      if (noteRefusal(error, 'key2fa', false)) {
        // notice shown
      } else if (error.message?.includes('cancelled') || error.message?.includes('abort') || error.name === 'NotAllowedError') {
        showInfo(t('auth.twoFactorKeyCancelled'))
      } else {
        setFormError(t('auth.twoFactorKeyFailed'))
      }
    } finally {
      setLoading(false)
    }
  }

  const handleMTLSLogin = async () => {
    clearMaintenance()
    setFormError('')
    setLoading(true)
    try {
      const userData = await authMethodsService.loginMTLS()
      const who = userData?.user?.username || globalMethods?.mtls_user
      await login(who, null, userData)
      welcome(userData, who)
      finish(who)
    } catch (error) {
      refuse(error, 'mtls', t('auth.autoLoginFailed'))
    } finally {
      setLoading(false)
    }
  }

  // A retry runs the handler of the latest render, so it sends what the fields hold now
  latestAttempt.current = {
    password: () => handlePasswordLogin(NO_EVENT),
    totp: () => handle2FAVerify(NO_EVENT),
    ldap: () => handleLDAPLogin(NO_EVENT),
    webauthn: () => attemptWebAuthn(),
    key2fa: () => handle2FAWebAuthn(),
    mtls: () => handleMTLSLogin(),
  }

  const handleSSOLogin = (provider) => {
    if (provider.provider_type === 'ldap') {
      clearMaintenance()
      setRateLimit(null)
      setSelectedLdapProvider(provider)
      setFieldErrors({})
      setFormError('')
      setStep('ldap')
    } else {
      // The server keeps the page with this login and hands it back on /login/sso-complete.
      const next = requested ? `?next=${encodeURIComponent(requested)}` : ''
      window.location.href = `/api/v2/sso/login/${provider.provider_type}${next}`
    }
  }

  const handleLDAPLogin = async (e) => {
    e.preventDefault()
    if (waiting) return  // the server's wait first, as the disabled button says
    if (missing([
      ['username', username.trim(), t('auth.page.usernameMissing')],
      ['password', password, t('auth.page.passwordMissing')],
    ])) return

    clearMaintenance()
    setFormError('')
    setLoading(true)
    setStatusMessage(t('auth.authenticating'))

    try {
      const data = await authService.ldapLogin(username, password, selectedLdapProvider?.id)
      const responseData = data.data || data
      // The provider enforces 2FA: the enrolled code is asked next.
      if (responseData.requires_2fa) {
        twoFactorFrom.current = 'ldap'
        setRateLimit(null)
        setStep('2fa')
        setTwoFactorMethods(responseData.methods || ['totp'])
        setTotpCode('')
        return
      }

      saveUsername(username)
      saveAuthMethod('ldap', selectedLdapProvider?.id)
      await login(username, null, responseData)
      welcome(responseData, username)
      finish(username)
    } catch (error) {
      refuse(error, 'ldap', t('auth.invalidCredentials'))
      if (!maintenanceRetry.current) setPassword('')
      setFocusNext('password')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  const handleBack = () => {
    clearMaintenance()
    setRateLimit(null)
    setFormError('')
    setFieldErrors({})
    setStep('form')
    setPassword('')
    setTotpCode('')
    setStatusMessage('')
    if (!lockedRef.current) {
      setSelectedLdapProvider(null)
      try { localStorage.removeItem(STORAGE_AUTH_METHOD_KEY) } catch {}
    }
  }

  // Back from the second factor to the door that asked for it
  const handleBackFrom2fa = () => {
    clearMaintenance()
    setRateLimit(null)
    setFormError('')
    setFieldErrors({})
    setTotpCode('')
    setStep(twoFactorFrom.current === 'ldap' && selectedLdapProvider && !lockedRef.current ? 'ldap' : 'form')
  }

  // The lock screen gives way to the sign-in form; the page asked for stays in ?next=
  const handleSwitchAccount = () => {
    clearLock()
    setLocked(null)
    setUsername('')
    handleBack()
    setSelectedLdapProvider(null)
    setFocusNext('username')
  }

  // ═══════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════

  // Show nothing while AuthContext is checking session (App.jsx shows PageLoader)
  if (!sessionChecked || step === 'init') {
    return null
  }

  const keySupported = authMethodsService.isWebAuthnSupported()
  const redirectProviders = ssoProviders.filter(p => p.provider_type !== 'ldap')
  const ldapProviders = ssoProviders.filter(p => p.provider_type === 'ldap')
  const mtlsReady = globalMethods?.mtls && globalMethods.mtls_status === 'enrolled'
  const keyOffered = keySupported && globalMethods?.webauthn !== false
  const lockedVia = locked?.method || ''
  // An SSO account has no password here: its lock screen offers the provider only
  const ssoOnly = Boolean(locked) && lockedVia === 'sso' && redirectProviders.length > 0

  const alt = (key, Icon, label, detail, onClick) => (
    <button key={key} type="button" className="auth-btn auth-alt" onClick={onClick} disabled={loading}>
      <Icon size={17} aria-hidden="true" />
      <span>{label}<small>{detail}</small></span>
    </button>
  )
  const keyButton = alt('key', Fingerprint, t('auth.page.keyButton'),
    loading && statusMessage === t('auth.touchSecurityKey') ? statusMessage : t('auth.page.keyDetail'), () => attemptWebAuthn())
  const mtlsButton = alt('mtls', Key, t('auth.page.mtlsButton'), t('auth.page.mtlsDetail', { username: globalMethods?.mtls_user || '' }), handleMTLSLogin)
  const ssoButtons = redirectProviders.map(p => alt(`sso-${p.id}`, SsoIcon,
    locked ? t('auth.page.resumeSso') : t('auth.page.ssoButton'),
    <><span>{providerName(p)}</span> · {PROTOCOLS[p.provider_type] || p.provider_type}</>,
    () => handleSSOLogin(p)))
  const ldapButtons = ldapProviders.map(p => alt(`ldap-${p.id}`, Database, t('auth.page.ldapButton'),
    <><span>{providerName(p)}</span> · LDAP</>, () => handleSSOLogin(p)))

  let alternatives
  if (locked) {
    alternatives = [
      ...(lockedVia === 'sso' ? ssoButtons : []),
      ...((lockedVia === 'mtls' || lockedVia === 'certificate') && mtlsReady ? [mtlsButton] : []),
      ...(lockedVia === 'webauthn' && keyOffered ? [keyButton] : []),
    ]
  } else {
    alternatives = preferKey && keyOffered
      ? [keyButton, ...ssoButtons, ...ldapButtons, ...(mtlsReady ? [mtlsButton] : [])]
      : [...ssoButtons, ...ldapButtons, ...(mtlsReady ? [mtlsButton] : []), ...(keyOffered ? [keyButton] : [])]
  }

  const errorBlock = (rateLimit || formError) && (
    <div className="auth-error" role="alert">
      <Warning size={14} aria-hidden="true" />
      <span>
        {!rateLimit ? formError
          : rateLimit.wait == null ? t('auth.page.tooManyNoDelay')
            : rateLimit.left ? t('auth.page.tooManyWait', { seconds: rateLimit.wait }) : t('auth.page.canRetry')}
      </span>
    </div>
  )
  const waitLine = waiting && <p className="auth-wait">{t('auth.page.retryIn', { seconds: rateLimit.left })}</p>

  const maintenanceBlock = maintenance && (
    <div className="auth-notice" role="status">
      <span>{maintenance.restoring ? t('auth.maintenanceRestoring') : t('auth.maintenanceActive')}</span>
      {maintenance.seconds != null && <span>{t('auth.maintenanceRetryIn', { seconds: maintenance.seconds })}</span>}
      <button type="button" className="auth-btn" onClick={retryNow} disabled={loading}>{t('auth.retryNow')}</button>
    </div>
  )

  const passwordField = (
    <AuthField id="login-pass" label={t('auth.page.password')} error={fieldErrors.password}>
      <div className="auth-password">
        <input
          ref={passwordRef}
          id="login-pass"
          name="password"
          type={reveal ? 'text' : 'password'}
          autoComplete="current-password"
          value={password}
          onChange={(e) => { touched.current = true; setPassword(e.target.value); if (fieldErrors.password) setFieldErrors(f => ({ ...f, password: undefined })) }}
          disabled={loading}
          aria-invalid={fieldErrors.password ? 'true' : undefined}
          aria-describedby={fieldErrors.password ? 'login-pass-error' : undefined}
        />
        {/* One label, the state in aria-pressed, as in the design */}
        <button
          type="button"
          className="auth-icon-btn"
          aria-pressed={reveal}
          aria-label={t('auth.page.showPassword')}
          onClick={() => setReveal(r => !r)}
        >
          {reveal ? <EyeSlash size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
        </button>
      </div>
    </AuthField>
  )

  const usernameField = (
    <AuthField id="login-user" label={t('auth.page.username')} error={fieldErrors.username}>
      <input
        ref={usernameRef}
        id="login-user"
        name="username"
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        value={username}
        readOnly={Boolean(locked)}
        onChange={(e) => { if (locked) return; touched.current = true; setUsername(e.target.value); if (fieldErrors.username) setFieldErrors(f => ({ ...f, username: undefined })) }}
        disabled={loading && !locked}
        aria-invalid={fieldErrors.username ? 'true' : undefined}
        aria-describedby={fieldErrors.username ? 'login-user-error' : undefined}
      />
    </AuthField>
  )

  const signInForm = (onSubmit, submitLabel, SubmitIcon) => (
    <form className="auth-form" onSubmit={onSubmit} noValidate aria-busy={loading || undefined}>
      {usernameField}
      {passwordField}
      {errorBlock}
      {waitLine}
      <button type="submit" className="auth-btn is-primary auth-submit" disabled={loading || waiting}>
        <SubmitIcon size={17} aria-hidden="true" />{submitLabel}
      </button>
    </form>
  )

  const lockedCard = locked && (
    <p className="auth-user">
      <span className="auth-avatar" aria-hidden="true">{initialsOf(locked.name || locked.username)}</span>
      <span>
        <strong>{locked.name || locked.username}</strong>
        <span>{locked.role ? `${roleLabel(t, locked.role)} · ` : ''}<span className="auth-mono">{locked.username}</span></span>
      </span>
    </p>
  )

  const title = locked ? t('auth.page.lockedTitle') : step === '2fa' ? t('auth.twoFactorTitle') : t('auth.page.signInTitle')
  let lead = locked ? t('auth.page.lockedLead') : t('auth.page.lead')
  let body

  if (ssoCompleting) {
    body = <p className="auth-wait" role="status">{t('auth.signingIn')}</p>
  } else if (step === '2fa') {
    lead = twoFactorMethods.includes('totp') ? t('auth.twoFactorDescription') : t('auth.twoFactorKeyDescription')
    body = (
      <>
        {lockedCard}
        {maintenanceBlock}
        {twoFactorMethods.includes('totp') && (
          <form className="auth-form" onSubmit={handle2FAVerify} noValidate aria-busy={loading || undefined}>
            <AuthField id="login-code" label={t('auth.totpCode')} error={fieldErrors.code}>
              <input
                ref={codeRef}
                id="login-code"
                name="code"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                autoComplete="one-time-code"
                placeholder="000000"
                value={totpCode}
                onChange={(e) => { setTotpCode(e.target.value.replace(/\D/g, '')); if (fieldErrors.code) setFieldErrors({}) }}
                disabled={loading}
                aria-invalid={fieldErrors.code ? 'true' : undefined}
                aria-describedby={fieldErrors.code ? 'login-code-error' : undefined}
              />
            </AuthField>
            {errorBlock}
            {waitLine}
            <button type="submit" className="auth-btn is-primary auth-submit" disabled={loading || waiting}>
              <CaretRight size={17} aria-hidden="true" />{t('auth.verify')}
            </button>
          </form>
        )}
        {!twoFactorMethods.includes('totp') && errorBlock}
        {twoFactorMethods.includes('webauthn') && keySupported && (
          <>
            {twoFactorMethods.includes('totp') && <p className="auth-sep"><span>{t('auth.page.or')}</span></p>}
            <button type="button" className={`auth-btn ${twoFactorMethods.includes('totp') ? 'auth-alt' : 'is-primary auth-submit'}`}
              onClick={handle2FAWebAuthn} disabled={loading}>
              <Fingerprint size={17} aria-hidden="true" />
              <span>{t('auth.twoFactorUseSecurityKey')}</span>
            </button>
          </>
        )}
        <button type="button" className="auth-link" onClick={handleBackFrom2fa} disabled={loading}>{t('common.back')}</button>
      </>
    )
  } else if (step === 'ldap' && selectedLdapProvider) {
    body = (
      <>
        <p className="auth-user">
          <span className="auth-avatar" aria-hidden="true"><Database size={14} /></span>
          <span>
            <strong>{providerName(selectedLdapProvider)}</strong>
            <span>{t('auth.signingInWith')} LDAP</span>
          </span>
        </p>
        {maintenanceBlock}
        {signInForm(handleLDAPLogin, t('auth.page.submit'), CaretRight)}
        <button type="button" className="auth-link" onClick={handleBack} disabled={loading}>{t('common.back')}</button>
      </>
    )
  } else {
    body = (
      <>
        {lockedCard}
        {maintenanceBlock}
        {ssoOnly ? errorBlock : signInForm(handlePasswordLogin, locked ? t('auth.page.unlock') : t('auth.page.submit'), locked ? Lock : CaretRight)}
        {alternatives.length > 0 && !ssoOnly && <p className="auth-sep"><span>{t('auth.page.or')}</span></p>}
        {alternatives}
        {loading && statusMessage && statusMessage !== t('auth.touchSecurityKey') && (
          <p className="auth-wait" aria-live="polite">{statusMessage}</p>
        )}
        {(locked || (emailConfigured && !locked)) && (
          <div className="auth-links">
            {locked
              ? <button type="button" className="auth-link" onClick={handleSwitchAccount}>{t('auth.page.switchAccount')}</button>
              : <Link to="/forgot-password" className="auth-link">{t('auth.forgotPassword')}</Link>}
          </div>
        )}
      </>
    )
  }

  return (
    <AuthFrame ref={titleRef} title={title} lead={lead}>
      {body}
      <p className="sr-only" aria-live="polite">{announce}</p>
    </AuthFrame>
  )
}
