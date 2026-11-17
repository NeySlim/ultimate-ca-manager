/** A sign-in refused by a maintenance (503, code `maintenance`): said in clear, tried again by
 * itself after a bounded Retry-After, or at once from the banner's button. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const s = vi.hoisted(() => ({
  detectMethods: vi.fn(), loginPassword: vi.fn(), authenticateWebAuthn: vi.fn(), login2FA: vi.fn(),
  ldapLogin: vi.fn(), getSsoProviders: vi.fn(), login: vi.fn(), showError: vi.fn(), showInfo: vi.fn(),
  navigate: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, o) => (o && o.seconds != null ? `${key}|${o.seconds}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => s.navigate,
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
    detectMethods: s.detectMethods, loginPassword: s.loginPassword, login2FA: s.login2FA,
    authenticateWebAuthn: s.authenticateWebAuthn, isWebAuthnSupported: () => true,
  },
}))

import LoginPage from '../LoginPage'
import { isMaintenanceRefusal, maintenanceRetrySeconds } from '../loginMaintenance'

const refused = (retryAfter = 3, reason = 'restore') => Object.assign(
  new Error('This UCM cluster is in maintenance (a backup restore): writes are refused until it ends. Retry later.'),
  { status: 503, retryAfter, data: { code: 'maintenance', maintenance: { reason, phase: 'restarting' } } })

function renderLogin() {
  render(<MemoryRouter initialEntries={['/login']}><LoginPage /></MemoryRouter>)
}
async function submitPassword() {
  fireEvent.change(await screen.findByPlaceholderText('auth.enterUsername'), { target: { value: 'alice' } })
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
// One act per second: each step of the countdown renders before the next timer is set
const tick = async (ms) => {
  for (let left = ms; left > 0; left -= 500) {
    await act(async () => { await vi.advanceTimersByTimeAsync(Math.min(500, left)) })
  }
}

describe('the maintenance refusal', () => {
  it('is known by its problem code, not its text', () => {
    expect(isMaintenanceRefusal(refused())).toBe(true)
    expect(isMaintenanceRefusal(Object.assign(new Error('Retry later.'), { status: 503, data: {} }))).toBe(false)
    expect(isMaintenanceRefusal({ status: 409, data: { code: 'maintenance' } })).toBe(false)
  })

  it('waits what Retry-After asks, within bounds', () => {
    expect(maintenanceRetrySeconds(refused(30))).toBe(30)
    expect(maintenanceRetrySeconds(refused(7))).toBe(7)
    expect(maintenanceRetrySeconds(refused(0))).toBe(2)
    expect(maintenanceRetrySeconds(refused(3600))).toBe(30)
    expect(maintenanceRetrySeconds({ ...refused(), retryAfter: undefined })).toBe(10)
  })
})

describe('LoginPage during a maintenance', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try { localStorage.clear() } catch { /* ignore */ }
    s.detectMethods.mockResolvedValue({ password: true })
    s.getSsoProviders.mockResolvedValue({ data: [{ id: 2, name: 'corp', display_name: 'Corporate LDAP', provider_type: 'ldap' }] })
    s.login.mockResolvedValue(undefined)
  })
  afterEach(() => { vi.useRealTimers() })

  it('says a restore holds the server and signs in by itself once it is over', async () => {
    s.loginPassword.mockRejectedValueOnce(refused(3)).mockRejectedValueOnce(refused(3)).mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent('auth.maintenanceRestoring')
    expect(banner).toHaveTextContent('auth.maintenanceRetryIn|3')
    expect(s.showError).not.toHaveBeenCalled()
    // Kept for the next attempt
    expect(screen.getByPlaceholderText('auth.enterPassword')).toHaveValue('pw')
    await tick(1000)
    expect(banner).toHaveTextContent('auth.maintenanceRetryIn|2')
    await tick(2500)
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledTimes(2))
    expect(s.loginPassword).toHaveBeenLastCalledWith('alice', 'pw')
    await tick(3500)
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledTimes(3))
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
    expect(s.login).toHaveBeenCalledWith('alice', 'pw', { user: { username: 'alice' } })
  })

  it('tries again at once from the button', async () => {
    s.loginPassword.mockRejectedValueOnce(refused(30, 'manual')).mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent('auth.maintenanceActive')
    fireEvent.click(screen.getByText('auth.retryNow'))
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
  })

  it('stops trying once another failure comes, and shows that one', async () => {
    s.loginPassword.mockRejectedValueOnce(refused(2)).mockRejectedValue(new Error('Invalid credentials'))
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    await tick(2500)
    await waitFor(() => expect(s.showError).toHaveBeenCalledWith('Invalid credentials'))
    expect(screen.queryByRole('status')).toBeNull()
    await tick(5000)
    expect(s.loginPassword).toHaveBeenCalledTimes(2)
  })

  it('stops trying when the user goes back', async () => {
    s.loginPassword.mockRejectedValue(refused(2))
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    fireEvent.click(screen.getByText('common.back'))
    expect(screen.queryByRole('status')).toBeNull()
    await tick(5000)
    expect(s.loginPassword).toHaveBeenCalledTimes(1)
  })

  it('does the same for an LDAP sign-in', async () => {
    s.ldapLogin.mockRejectedValueOnce(refused(2)).mockResolvedValue({ data: { user: { username: 'alice' } } })
    renderLogin()
    await submitLdap()
    expect(await screen.findByRole('status')).toHaveTextContent('auth.maintenanceRestoring')
    await tick(2500)
    await waitFor(() => expect(s.ldapLogin).toHaveBeenCalledTimes(2))
    expect(s.ldapLogin).toHaveBeenLastCalledWith('alice', 'pw', 2)
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
  })

  it('does the same for a second factor code', async () => {
    s.loginPassword.mockResolvedValue({ requires_2fa: true, methods: ['totp'] })
    s.login2FA.mockRejectedValueOnce(refused(2)).mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    await screen.findByText('auth.twoFactorTitle')
    const code = document.querySelector('input[autocomplete="one-time-code"]') || screen.getAllByRole('textbox').pop()
    fireEvent.change(code, { target: { value: '123456' } })
    fireEvent.submit(code.closest('form'))
    await screen.findByRole('status')
    await tick(2500)
    await waitFor(() => expect(s.login2FA).toHaveBeenCalledTimes(2))
    expect(s.login2FA).toHaveBeenLastCalledWith('123456')
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
  })

  it('sends the password in the field when it tries again, not the refused one', async () => {
    s.loginPassword.mockRejectedValueOnce(refused(2)).mockRejectedValueOnce(refused(2)).mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    fireEvent.change(screen.getByPlaceholderText('auth.enterPassword'), { target: { value: 'corrected' } })
    await tick(2500)
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledTimes(2))
    expect(s.loginPassword).toHaveBeenLastCalledWith('alice', 'corrected')
    fireEvent.click(screen.getByText('auth.retryNow'))
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledTimes(3))
    expect(s.loginPassword).toHaveBeenLastCalledWith('alice', 'corrected')
  })

  it('sends the code in the field when it tries again', async () => {
    s.loginPassword.mockResolvedValue({ requires_2fa: true, methods: ['totp'] })
    s.login2FA.mockRejectedValueOnce(refused(2)).mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    await screen.findByText('auth.twoFactorTitle')
    const code = document.querySelector('input[autocomplete="one-time-code"]') || screen.getAllByRole('textbox').pop()
    fireEvent.change(code, { target: { value: '123456' } })
    fireEvent.submit(code.closest('form'))
    await screen.findByRole('status')
    fireEvent.change(code, { target: { value: '654321' } })
    await tick(2500)
    await waitFor(() => expect(s.login2FA).toHaveBeenCalledTimes(2))
    expect(s.login2FA).toHaveBeenLastCalledWith('654321')
  })

  it('sends the LDAP password in the field when it tries again', async () => {
    s.ldapLogin.mockRejectedValueOnce(refused(2)).mockResolvedValue({ data: { user: { username: 'alice' } } })
    renderLogin()
    await submitLdap()
    await screen.findByRole('status')
    fireEvent.change(screen.getByPlaceholderText('auth.enterPassword'), { target: { value: 'corrected' } })
    await tick(2500)
    await waitFor(() => expect(s.ldapLogin).toHaveBeenCalledTimes(2))
    expect(s.ldapLogin).toHaveBeenLastCalledWith('alice', 'corrected', 2)
  })

})
