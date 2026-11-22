/**
 * The lock screen of a session the server holds locked: the account's own unlock methods shown
 * together (password field only when the account has a password, a button per certificate or
 * passkey), each sent to its unlock route; a session gone meanwhile falls back to signing in again.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { saveLock } from '../../lib/sessionLock'

const s = vi.hoisted(() => ({
  login: vi.fn(), getSsoProviders: vi.fn(), detectMethods: vi.fn(), isEmailConfigured: vi.fn(),
  verifySession: vi.fn(), whenLocked: vi.fn(), logout: vi.fn(), loginPassword: vi.fn(),
  unlockPassword: vi.fn(), unlock2FA: vi.fn(), unlockCertificate: vi.fn(), unlockPasskey: vi.fn(),
  checked: true,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
}))
vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ login: s.login, sessionChecked: s.checked }),
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../services/auth.service', () => ({
  authService: {
    getSsoProviders: s.getSsoProviders, isEmailConfigured: s.isEmailConfigured, ldapLogin: vi.fn(),
    verifySession: s.verifySession, whenLocked: s.whenLocked, logout: s.logout,
  },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    detectMethods: s.detectMethods, loginPassword: s.loginPassword, isWebAuthnSupported: () => true,
    unlockPassword: s.unlockPassword, unlock2FA: s.unlock2FA, unlockCertificate: s.unlockCertificate,
    unlockPasskey: s.unlockPasskey,
  },
}))

import LoginPage from '../LoginPage'

const page = () => (
  <MemoryRouter initialEntries={['/login?next=%2Fcertificates']}>
    <Routes><Route path="/login" element={<LoginPage />} /><Route path="*" element={<p>console</p>} /></Routes>
  </MemoryRouter>
)
const renderLock = () => render(page())

const held = (methods, extra = {}) => s.verifySession.mockResolvedValue({
  data: { authenticated: false, locked: { username: 'alice', reason: 'manual', methods, ...extra } },
})
const session = { user: { username: 'alice', full_name: 'Alice Martin', role: 'operator' }, auth_method: 'password' }

describe('LoginPage on a session the server holds locked', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    s.checked = true
    localStorage.clear()
    sessionStorage.clear()
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, mtls: false })
    s.getSsoProviders.mockResolvedValue({ data: [{ id: 4, name: 'kc', display_name: 'Company SSO', provider_type: 'oauth2' }] })
    s.isEmailConfigured.mockResolvedValue({ data: { configured: false } })
    s.whenLocked.mockResolvedValue(undefined)
    s.logout.mockResolvedValue({})
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'certificate', reason: 'manual' })
  })

  it('shows the password and every other method of the account at once, nothing else', async () => {
    held(['password', 'certificate', 'passkey'])
    renderLock()
    expect(await screen.findByRole('button', { name: /auth.page.unlockCertificate/ })).toBeInTheDocument()
    expect(screen.getByLabelText('auth.page.password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /auth.page.unlockPasskey/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'auth.page.unlock' })).toBeInTheDocument()
    expect(screen.getByText('auth.page.lockedLeadManualHeld')).toBeInTheDocument()
    // No sign-in door of the plain page: SSO, security key login, client certificate login
    expect(screen.queryByRole('button', { name: /auth.page.resumeSso|auth.page.ssoButton/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /auth.page.keyButton|auth.page.mtlsButton/ })).toBeNull()
    expect(s.whenLocked).toHaveBeenCalled()
  })

  it('shows no password field to an account without one', async () => {
    held(['passkey'])
    renderLock()
    expect(await screen.findByRole('button', { name: /auth.page.unlockPasskey/ })).toBeInTheDocument()
    expect(screen.queryByLabelText('auth.page.password')).toBeNull()
    expect(screen.queryByRole('button', { name: /auth.page.unlockCertificate/ })).toBeNull()
    expect(screen.queryByText('auth.page.noUnlockMethod')).toBeNull()
  })

  it('says so when the account has no method to unlock here, and offers the sign-out', async () => {
    held([])
    renderLock()
    expect(await screen.findByText('auth.page.noUnlockMethod')).toBeInTheDocument()
    expect(screen.queryByLabelText('auth.page.password')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.switchAccount' }))
    expect(s.logout).toHaveBeenCalled()
    expect(await screen.findByLabelText('auth.page.password')).toBeInTheDocument()
  })

  it('unlocks with the password through the unlock route and returns to the page', async () => {
    held(['password'])
    s.unlockPassword.mockResolvedValue(session)
    renderLock()
    fireEvent.change(await screen.findByLabelText('auth.page.password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.unlock' }))
    await waitFor(() => expect(s.login).toHaveBeenCalledWith('alice', null, session))
    expect(s.unlockPassword).toHaveBeenCalledWith('pw')
    expect(s.loginPassword).not.toHaveBeenCalled()
    expect(await screen.findByText('console')).toBeInTheDocument()
  })

  it('asks the second factor of a password unlock through the unlock route', async () => {
    held(['password'])
    s.unlockPassword.mockResolvedValue({ requires_2fa: true, methods: ['totp'] })
    s.unlock2FA.mockResolvedValue(session)
    renderLock()
    fireEvent.change(await screen.findByLabelText('auth.page.password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.unlock' }))
    fireEvent.change(await screen.findByLabelText('auth.totpCode'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.verify' }))
    await waitFor(() => expect(s.unlock2FA).toHaveBeenCalledWith('123456'))
    await waitFor(() => expect(s.login).toHaveBeenCalledWith('alice', expect.anything(), session))
  })

  it('unlocks with the certificate, and says when it does not open this account', async () => {
    held(['password', 'certificate'])
    s.unlockCertificate.mockRejectedValueOnce(Object.assign(new Error('no'), { status: 401, data: { type: 'about:blank' } }))
    s.unlockCertificate.mockResolvedValueOnce(session)
    renderLock()
    fireEvent.click(await screen.findByRole('button', { name: /auth.page.unlockCertificate/ }))
    await waitFor(() => expect(document.getElementById('login-error')).toHaveTextContent('auth.page.unlockCertificateRefused'))
    fireEvent.click(screen.getByRole('button', { name: /auth.page.unlockCertificate/ }))
    await waitFor(() => expect(s.login).toHaveBeenCalledWith('alice', null, session))
  })

  it('unlocks with a passkey', async () => {
    held(['passkey'])
    s.unlockPasskey.mockResolvedValue(session)
    renderLock()
    fireEvent.click(await screen.findByRole('button', { name: /auth.page.unlockPasskey/ }))
    await waitFor(() => expect(s.login).toHaveBeenCalledWith('alice', null, session))
  })

  it('falls back to signing in again when the session is gone', async () => {
    s.verifySession.mockResolvedValue({ data: { authenticated: false } })
    s.loginPassword.mockResolvedValue(session)
    renderLock()
    fireEvent.change(await screen.findByLabelText('auth.page.password'), { target: { value: 'pw' } })
    expect(screen.getByText('auth.page.lockedLeadManual')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.unlock' }))
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledWith('alice', 'pw'))
    expect(s.unlockPassword).not.toHaveBeenCalled()
  })

  it('takes the lock another tab is still sending: the session found open is asked again', async () => {
    s.verifySession
      .mockResolvedValueOnce({ data: { authenticated: true, user: { username: 'alice' } } })
      .mockResolvedValue({ data: { authenticated: false, locked: { username: 'alice', reason: 'manual', methods: ['certificate'] } } })
    renderLock()
    expect(await screen.findByRole('button', { name: /auth.page.unlockCertificate/ }, { timeout: 3000 })).toBeInTheDocument()
    expect(s.verifySession).toHaveBeenCalledTimes(2)
  })

  it('shows the lock screen of an account the session check found locked after the page opened', async () => {
    sessionStorage.clear()
    held(['password'])
    s.checked = false
    const { rerender } = render(page())
    // The session check (AuthContext) saves the server's lock while the page waits for it
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', reason: 'idle' })
    s.checked = true
    rerender(page())
    expect(await screen.findByText('Alice Martin')).toBeInTheDocument()
    expect(screen.getByText('auth.page.lockedLeadHeld')).toBeInTheDocument()
  })
})
