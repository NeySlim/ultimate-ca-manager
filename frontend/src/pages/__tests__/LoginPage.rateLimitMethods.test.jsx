/** The server's 429 banner on LDAP and WebAuthn 2FA, and its removal by any other failure. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const s = vi.hoisted(() => ({
  detectMethods: vi.fn(), loginPassword: vi.fn(), authenticateWebAuthn: vi.fn(), login2FAWebAuthn: vi.fn(), ldapLogin: vi.fn(),
  getSsoProviders: vi.fn(), login: vi.fn(), showError: vi.fn(), showInfo: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, o) => (o && o.seconds != null ? `${key}|${o.seconds}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ login: s.login, sessionChecked: true }),
  useNotification: () => ({ showError: s.showError, showSuccess: vi.fn(), showInfo: s.showInfo }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'default', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))
vi.mock('../../services/auth.service', () => ({
  authService: {
    getSsoProviders: s.getSsoProviders, ldapLogin: s.ldapLogin,
    isEmailConfigured: vi.fn().mockResolvedValue({ configured: false }),
  },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    detectMethods: s.detectMethods, loginPassword: s.loginPassword,
    login2FAWebAuthn: s.login2FAWebAuthn, authenticateWebAuthn: s.authenticateWebAuthn, isWebAuthnSupported: () => true,
  },
}))

import LoginPage from '../LoginPage'

const tooMany = () => Object.assign(new Error('Too many failed attempts.'), { status: 429, retryAfter: 30 })

function renderLogin() {
  render(<MemoryRouter initialEntries={['/login']}><LoginPage /></MemoryRouter>)
}
async function typeUsername() {
  fireEvent.change(await screen.findByPlaceholderText('auth.enterUsername'), { target: { value: 'alice' } })
}
async function submitPassword() {
  fireEvent.click(screen.getByText('auth.continue'))
  fireEvent.change(await screen.findByPlaceholderText('auth.enterPassword'), { target: { value: 'pw' } })
  fireEvent.click(screen.getByText('auth.login'))
}
async function submitLdap() {
  fireEvent.click(await screen.findByText('Corporate LDAP'))
  fireEvent.change(await screen.findByPlaceholderText('auth.ldapUsername'), { target: { value: 'alice' } })
  fireEvent.change(screen.getByPlaceholderText('auth.enterPassword'), { target: { value: 'pw' } })
  fireEvent.submit(screen.getByPlaceholderText('auth.enterPassword').closest('form'))
}

describe('LoginPage 429 banner across methods', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    try { localStorage.clear() } catch { /* ignore */ }
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true })
    s.getSsoProviders.mockResolvedValue({ data: [{ id: 2, name: 'corp', display_name: 'Corporate LDAP', provider_type: 'ldap' }] })
  })

  it('shows the server 429 of an LDAP login as a banner, not a toast', async () => {
    s.ldapLogin.mockRejectedValue(tooMany())
    renderLogin()
    await submitLdap()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('auth.tooManyAttempts')
    expect(alert).toHaveTextContent('auth.retryAfterSeconds|30')
    expect(s.showError).not.toHaveBeenCalled()
  })

  it('removes a password 429 banner when an LDAP attempt fails otherwise', async () => {
    s.loginPassword.mockRejectedValueOnce(tooMany())
    s.ldapLogin.mockRejectedValue(new Error('Invalid LDAP credentials'))
    renderLogin()
    await typeUsername()
    await submitPassword()
    await screen.findByRole('alert')
    fireEvent.click(screen.getByText('common.back'))
    await submitLdap()
    await waitFor(() => expect(s.showError).toHaveBeenCalledWith('Invalid LDAP credentials'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  async function reachKeyStep() {
    s.loginPassword.mockResolvedValue({ requires_2fa: true, methods: ['webauthn'] })
    renderLogin()
    await typeUsername()
    await submitPassword()
    await screen.findByText('auth.twoFactorTitle')
  }

  it('shows the server 429 of the security key check as a banner', async () => {
    s.login2FAWebAuthn.mockRejectedValue(tooMany())
    await reachKeyStep()
    fireEvent.click(screen.getByText('auth.twoFactorUseSecurityKey'))
    expect(await screen.findByRole('alert')).toHaveTextContent('auth.tooManyAttempts')
    expect(s.showError).not.toHaveBeenCalled()
  })

  it('keeps the cancelled case as an info toast and clears a previous banner', async () => {
    s.login2FAWebAuthn.mockRejectedValueOnce(tooMany()).mockRejectedValue(Object.assign(new Error('x'), { name: 'NotAllowedError' }))
    await reachKeyStep()
    fireEvent.click(screen.getByText('auth.twoFactorUseSecurityKey'))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByText('auth.twoFactorUseSecurityKey'))
    await waitFor(() => expect(s.showInfo).toHaveBeenCalledWith('auth.twoFactorKeyCancelled'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the server 429 of a passkey sign-in, and a later ordinary failure removes it', async () => {
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, webauthn_credentials: 1 })
    s.authenticateWebAuthn.mockRejectedValueOnce(tooMany()).mockRejectedValue(new Error('no'))
    renderLogin()
    await typeUsername()
    fireEvent.click(screen.getByText('auth.continue'))
    fireEvent.click(await screen.findByText('auth.useSecurityKey'))
    expect(await screen.findByRole('alert')).toHaveTextContent('auth.tooManyAttempts')
    fireEvent.click(await screen.findByText('auth.useSecurityKey'))
    await waitFor(() => expect(s.authenticateWebAuthn).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('drops a password 429 banner when the next attempt reaches the second factor', async () => {
    s.loginPassword.mockRejectedValueOnce(tooMany()).mockResolvedValue({ requires_2fa: true, methods: ['totp'] })
    renderLogin()
    await typeUsername()
    await submitPassword()
    await screen.findByRole('alert')
    fireEvent.change(screen.getByPlaceholderText('auth.enterPassword'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('auth.login'))
    await screen.findByText('auth.twoFactorTitle')
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
