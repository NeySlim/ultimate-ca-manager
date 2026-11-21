/**
 * Lock screen: the same account signs in again, read-only username, and returns
 * to the page kept in ?next= (checked by safeNext); another account starts afresh.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { saveLock, readLock } from '../../lib/sessionLock'

const s = vi.hoisted(() => ({
  loginPassword: vi.fn(), authenticateWebAuthn: vi.fn(), login: vi.fn(), getSsoProviders: vi.fn(),
  verifySession: vi.fn(), ldapLogin: vi.fn(), detectMethods: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ login: s.login, sessionChecked: true }),
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../services/auth.service', () => ({
  authService: {
    getSsoProviders: s.getSsoProviders, verifySession: s.verifySession, ldapLogin: s.ldapLogin,
    isEmailConfigured: vi.fn().mockResolvedValue({ data: { configured: true } }),
  },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    detectMethods: s.detectMethods, loginPassword: s.loginPassword,
    authenticateWebAuthn: s.authenticateWebAuthn, isWebAuthnSupported: () => true,
  },
}))

import LoginPage from '../LoginPage'

function Where() {
  const l = useLocation()
  return <output data-testid="where">{l.pathname + l.search}</output>
}

function renderAt(entry) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/login/sso-complete" element={<LoginPage />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>
  )
}

const NEXT = '/certificates?status=expiring'
const realLocation = window.location

describe('LoginPage lock screen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    localStorage.clear()
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true })
    s.getSsoProviders.mockResolvedValue({ data: [{ id: 1, name: 'kc', display_name: 'Company SSO', provider_type: 'oauth2' }] })
    s.login.mockResolvedValue(undefined)
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
  })
  afterEach(() => { window.location = realLocation })

  it('shows the locked account and unlocks it with its password, back to the page kept', async () => {
    s.loginPassword.mockResolvedValue({ user: { username: 'alice' } })
    renderAt(`/login?next=${encodeURIComponent(NEXT)}`)
    expect(await screen.findByRole('heading', { name: 'auth.page.lockedTitle' })).toBeInTheDocument()
    expect(screen.getByText('auth.page.lockedLead')).toBeInTheDocument()
    expect(screen.getByText('Alice Martin')).toBeInTheDocument()
    const user = screen.getByLabelText('auth.page.username')
    expect(user).toHaveValue('alice')
    expect(user).toHaveAttribute('readonly')
    // An SSO door would open another account: not offered to a password account
    expect(screen.queryByText(/^Company SSO · /)).toBeNull()
    expect(screen.queryByText('auth.forgotPassword')).toBeNull()
    fireEvent.change(user, { target: { value: 'mallory' } })
    fireEvent.change(screen.getByLabelText('auth.page.password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.unlock' }))
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledWith('alice', 'pw'))
    expect(await screen.findByTestId('where')).toHaveTextContent(NEXT)
    expect(readLock()).toBeNull()
  })

  it('names an empty password beside its field, and sends nothing', async () => {
    renderAt('/login')
    fireEvent.click(await screen.findByRole('button', { name: 'auth.page.unlock' }))
    const pass = screen.getByLabelText('auth.page.password')
    expect(pass).toHaveAttribute('aria-invalid', 'true')
    expect(document.getElementById(pass.getAttribute('aria-describedby'))).toHaveTextContent('auth.page.passwordMissing')
    expect(document.activeElement).toBe(pass)
    expect(s.loginPassword).not.toHaveBeenCalled()
  })

  it('refuses an outside page kept in next', async () => {
    s.loginPassword.mockResolvedValue({ user: { username: 'alice' } })
    renderAt(`/login?next=${encodeURIComponent('https://evil.example/')}`)
    fireEvent.change(await screen.findByLabelText('auth.page.password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.unlock' }))
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/dashboard$/)
  })

  it('gives way to the sign-in form for another account, keeping the page asked for', async () => {
    s.loginPassword.mockResolvedValue({ user: { username: 'bob' } })
    renderAt(`/login?next=${encodeURIComponent(NEXT)}`)
    fireEvent.click(await screen.findByText('auth.page.switchAccount'))
    expect(screen.getByRole('heading', { name: 'auth.page.signInTitle' })).toBeInTheDocument()
    expect(readLock()).toBeNull()
    const user = screen.getByLabelText('auth.page.username')
    expect(user).not.toHaveAttribute('readonly')
    expect(user).toHaveValue('')
    expect(screen.getByText(/^Company SSO · /)).toBeInTheDocument()
    fireEvent.change(user, { target: { value: 'bob' } })
    fireEvent.change(screen.getByLabelText('auth.page.password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.submit' }))
    expect(await screen.findByTestId('where')).toHaveTextContent(NEXT)
  })

  it('offers an SSO account its provider only, carrying the page kept', async () => {
    saveLock({ username: 'carol', role: 'viewer', method: 'sso' })
    delete window.location
    window.location = { pathname: '/login', search: '', href: '' }
    renderAt(`/login?next=${encodeURIComponent(NEXT)}`)
    const resume = await screen.findByText('auth.page.resumeSso')
    expect(screen.queryByLabelText('auth.page.password')).toBeNull()
    fireEvent.click(resume)
    expect(window.location.href).toBe(`/api/v2/sso/login/oauth2?next=${encodeURIComponent(NEXT)}`)
  })

  it('sends another account than the locked one to the dashboard after SSO', async () => {
    saveLock({ username: 'carol', method: 'sso' })
    delete window.location
    window.location = { pathname: '/login/sso-complete', search: '', href: '' }
    s.verifySession.mockResolvedValue({ data: { user: { username: 'dave' } } })
    renderAt(`/login/sso-complete?next=${encodeURIComponent(NEXT)}`)
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/dashboard$/)
    expect(readLock()).toBeNull()
  })

  it('returns the locked account to its page after SSO', async () => {
    saveLock({ username: 'carol', method: 'sso' })
    delete window.location
    window.location = { pathname: '/login/sso-complete', search: '', href: '' }
    s.verifySession.mockResolvedValue({ data: { user: { username: 'carol' } } })
    renderAt(`/login/sso-complete?next=${encodeURIComponent(NEXT)}`)
    expect(await screen.findByTestId('where')).toHaveTextContent(NEXT)
  })

  it('offers the security key to an account locked after a key sign-in', async () => {
    saveLock({ username: 'erin', method: 'webauthn' })
    s.authenticateWebAuthn.mockResolvedValue({ user: { username: 'erin' } })
    renderAt(`/login?next=${encodeURIComponent(NEXT)}`)
    fireEvent.click(await screen.findByText('auth.page.keyButton'))
    await waitFor(() => expect(s.authenticateWebAuthn).toHaveBeenCalledWith('erin'))
    expect(await screen.findByTestId('where')).toHaveTextContent(NEXT)
  })
})
