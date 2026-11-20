/**
 * Sign-in and lock screen as the design has them: the forgotten-password link read from the
 * server's answer, the role named on the locked account, the focus after a refusal, the
 * messages chosen by the response's status, and the wait of a 429 counted down.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { saveLock, markJustLocked } from '../../lib/sessionLock'

const s = vi.hoisted(() => ({
  loginPassword: vi.fn(), login2FA: vi.fn(), login: vi.fn(), getSsoProviders: vi.fn(), detectMethods: vi.fn(),
  isEmailConfigured: vi.fn(), ldapLogin: vi.fn(), showSuccess: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, o) => (o && Object.keys(o).length ? `${key}|${Object.values(o).join('|')}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))
vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ login: s.login, sessionChecked: true }),
  useNotification: () => ({ showError: vi.fn(), showSuccess: s.showSuccess, showInfo: vi.fn() }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../services/auth.service', () => ({
  authService: { getSsoProviders: s.getSsoProviders, isEmailConfigured: s.isEmailConfigured, ldapLogin: s.ldapLogin },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    detectMethods: s.detectMethods, loginPassword: s.loginPassword, login2FA: s.login2FA,
    isWebAuthnSupported: () => false,
  },
}))

import LoginPage from '../LoginPage'

const renderLogin = (entry = '/login') => render(
  <MemoryRouter initialEntries={[entry]}>
    <Routes><Route path="/login" element={<LoginPage />} /><Route path="*" element={<p>console</p>} /></Routes>
  </MemoryRouter>
)
const refusal = (status, message, extra = {}) => Object.assign(new Error(message), { status, ...extra })

async function submit(username = 'alice', password = 'bad') {
  fireEvent.change(await screen.findByLabelText('auth.page.username'), { target: { value: username } })
  fireEvent.change(screen.getByLabelText('auth.page.password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'auth.page.submit' }))
}

describe('LoginPage, as designed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    s.detectMethods.mockResolvedValue({ password: true, webauthn: false, mtls: false })
    s.getSsoProviders.mockResolvedValue({ data: [] })
    s.isEmailConfigured.mockResolvedValue({ data: { configured: false } })
    s.login.mockResolvedValue(undefined)
  })
  afterEach(() => { vi.useRealTimers() })

  it('offers the forgotten-password link when the server answers that email is configured', async () => {
    s.isEmailConfigured.mockResolvedValue({ success: true, data: { configured: true } })
    renderLogin()
    expect(await screen.findByRole('link', { name: 'auth.forgotPassword' })).toHaveAttribute('href', '/forgot-password')
  })

  it('offers no forgotten-password link when email is not configured', async () => {
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    await waitFor(() => expect(s.isEmailConfigured).toHaveBeenCalled())
    expect(screen.queryByRole('link', { name: 'auth.forgotPassword' })).toBeNull()
  })

  it('names the role of the locked account, not its code', async () => {
    saveLock({ username: 'administrateur', name: 'Administrateur fictif', role: 'admin', method: 'password' })
    renderLogin('/login?next=%2Fcertificates')
    expect(await screen.findByText('Administrateur fictif')).toBeInTheDocument()
    const card = screen.getByText('Administrateur fictif').closest('.auth-user')
    expect(card.querySelector('strong + span')).toHaveTextContent(/^users\.admin · administrateur$/)
  })

  it('keeps a custom role as it is named', async () => {
    saveLock({ username: 'c.durand', name: 'Claire Durand', role: 'PKI desk', method: 'password' })
    renderLogin()
    expect((await screen.findByText('Claire Durand')).closest('.auth-user')).toHaveTextContent('PKI desk · c.durand')
  })

  it('focuses nothing when the page opens', async () => {
    localStorage.setItem('ucm_last_username', 'alice')
    renderLogin()
    expect(await screen.findByLabelText('auth.page.username')).toHaveValue('alice')
    await act(async () => {})
    expect(document.activeElement).toBe(document.body)
  })

  it('after a refusal, empties the password and focuses it once it is enabled again', async () => {
    s.loginPassword.mockRejectedValue(refusal(401, 'Invalid credentials'))
    renderLogin()
    await submit()
    expect(await screen.findByRole('alert')).toHaveTextContent('auth.invalidCredentials')
    const pass = screen.getByLabelText('auth.page.password')
    expect(pass).toHaveValue('')
    await waitFor(() => expect(document.activeElement).toBe(pass))
    expect(pass).not.toBeDisabled()
  })

  it('says a refused attempt in its own words, not the server English', async () => {
    s.loginPassword.mockRejectedValue(refusal(401, 'Invalid credentials'))
    renderLogin()
    await submit()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('auth.invalidCredentials')
    expect(alert).not.toHaveTextContent('Invalid credentials')
  })

  it('counts down the wait of a 429 and keeps the button off until it ends', async () => {
    s.loginPassword.mockRejectedValue(refusal(429, 'Too many requests', { retryAfter: 3 }))
    renderLogin()
    await submit()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('auth.page.tooManyWait|3')
    expect(screen.getByText('auth.page.retryIn|3')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'auth.page.submit' })
    expect(button).toBeDisabled()
    await waitFor(() => expect(screen.getByText('auth.page.retryIn|2')).toBeInTheDocument(), { timeout: 2000 })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('auth.page.canRetry'), { timeout: 4000 })
    expect(screen.queryByText(/auth\.page\.retryIn/)).toBeNull()
    expect(screen.getByRole('button', { name: 'auth.page.submit' })).not.toBeDisabled()
  }, 8000)

  it('a 429 without a delay asks to wait and leaves the button on', async () => {
    s.loginPassword.mockRejectedValue(refusal(429, 'Too many requests'))
    renderLogin()
    await submit()
    expect(await screen.findByRole('alert')).toHaveTextContent('auth.page.tooManyNoDelay')
    expect(screen.queryByText(/auth\.page\.retryIn/)).toBeNull()
    expect(screen.getByRole('button', { name: 'auth.page.submit' })).not.toBeDisabled()
  })

  it('says a refused second-factor code in its own words and focuses the code again', async () => {
    s.loginPassword.mockResolvedValue({ requires_2fa: true, methods: ['totp'] })
    s.login2FA.mockRejectedValue(refusal(401, 'Invalid verification code'))
    renderLogin()
    await submit('alice', 'right')
    const code = await screen.findByLabelText('auth.totpCode')
    fireEvent.change(code, { target: { value: '123456' } })
    // A browser drops the focus of the field disabled while the code is checked; jsdom does not
    screen.getByRole('button', { name: 'auth.verify' }).focus()
    fireEvent.click(screen.getByRole('button', { name: 'auth.verify' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('auth.invalidTotpCode')
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('auth.totpCode')))
    expect(screen.getByLabelText('auth.totpCode')).toHaveValue('')
  })

  it('keeps one label on the reveal button, its state in aria-pressed, no tooltip', async () => {
    renderLogin()
    const reveal = await screen.findByRole('button', { name: 'auth.page.showPassword' })
    expect(reveal).not.toHaveAttribute('title')
    fireEvent.click(reveal)
    expect(screen.getByRole('button', { name: 'auth.page.showPassword' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('arriving from an inactivity lock, focuses the title and says the screen locked', async () => {
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
    markJustLocked()
    renderLogin('/login?next=%2Fcertificates')
    const title = await screen.findByRole('heading', { name: 'auth.page.lockedTitle' })
    await waitFor(() => expect(document.activeElement).toBe(title))
    expect(screen.getByText('auth.page.lockedAnnounce')).toBeInTheDocument()
  })

  it('a lock screen opened by its address focuses nothing and says nothing', async () => {
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
    renderLogin('/login?next=%2Fcertificates')
    await screen.findByRole('heading', { name: 'auth.page.lockedTitle' })
    await act(async () => {})
    expect(document.activeElement).toBe(document.body)
    expect(screen.queryByText('auth.page.lockedAnnounce')).toBeNull()
  })

  it('"another account" leaves the lock screen on the username field', async () => {
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
    renderLogin()
    fireEvent.click(await screen.findByRole('button', { name: 'auth.page.switchAccount' }))
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('auth.page.username')))
    expect(screen.getByLabelText('auth.page.username')).toHaveValue('')
  })

  it('welcomes the account by name and role once signed in', async () => {
    s.loginPassword.mockResolvedValue({ user: { username: 'alice', full_name: 'Alice Martin', role: 'operator' } })
    renderLogin()
    await submit('alice', 'right')
    await waitFor(() => expect(s.showSuccess).toHaveBeenCalledWith('auth.page.signedIn|Alice Martin|common.operator'))
  })

  it('names the screen in the tab title', async () => {
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    expect(document.title).toBe('auth.page.signInTitle · UCM')
  })
})
