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
    // Answers queued by a test never reach the next one
    for (const call of [s.loginPassword, s.login2FA, s.ldapLogin, s.authenticateWebAuthn]) call.mockReset()
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

  it('stops trying when the user goes back from the second factor', async () => {
    s.loginPassword.mockResolvedValue({ requires_2fa: true, methods: ['totp'] })
    s.login2FA.mockRejectedValue(refused(2))
    renderLogin()
    await submitPassword()
    await screen.findByText('auth.twoFactorTitle')
    const code = document.querySelector('input[autocomplete="one-time-code"]') || screen.getAllByRole('textbox').pop()
    fireEvent.change(code, { target: { value: '123456' } })
    fireEvent.submit(code.closest('form'))
    await screen.findByRole('status')
    fireEvent.click(screen.getByText('common.back'))
    expect(screen.queryByRole('status')).toBeNull()
    await tick(4000)
    expect(s.login2FA).toHaveBeenCalledTimes(1)
    expect(s.showError).not.toHaveBeenCalled()
  })

  it.each([0, 502, 504])('keeps trying while the node restarts (%s), then signs in', async (status) => {
    const down = Object.assign(new Error('Network error'), { status })
    s.loginPassword.mockRejectedValueOnce(refused(2)).mockRejectedValueOnce(down).mockRejectedValueOnce(down)
      .mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    await tick(2500)
    await waitFor(() => expect(s.loginPassword).toHaveBeenCalledTimes(2))
    // No answer from a node that restarts is still the restore: the banner stays, no error shown
    expect(await screen.findByRole('status')).toHaveTextContent('auth.maintenanceRestoring')
    expect(s.showError).not.toHaveBeenCalled()
    await tick(25000)
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
    expect(s.loginPassword).toHaveBeenCalledTimes(4)
  })

  it('gives up after a minute without an answer, and shows the error', async () => {
    const down = Object.assign(new Error('Network error'), { status: 0 })
    s.loginPassword.mockRejectedValueOnce(refused(2)).mockRejectedValue(down)
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    await tick(90000)
    await waitFor(() => expect(s.showError).toHaveBeenCalledWith('Network error'))
    expect(screen.queryByRole('status')).toBeNull()
    const calls = s.loginPassword.mock.calls.length
    await tick(30000)
    expect(s.loginPassword).toHaveBeenCalledTimes(calls)
  })

  it('counts the tries without an answer afresh once the server answers again', async () => {
    const down = Object.assign(new Error('Network error'), { status: 0 })
    for (let n = 0; n < 2; n += 1) {
      s.loginPassword.mockRejectedValueOnce(refused(2))
      for (let lost = 0; lost < 11; lost += 1) s.loginPassword.mockRejectedValueOnce(down)
    }
    s.loginPassword.mockResolvedValue({ user: { username: 'alice' } })
    renderLogin()
    await submitPassword()
    await tick(125000)
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
    expect(s.showError).not.toHaveBeenCalled()
    expect(s.loginPassword).toHaveBeenCalledTimes(25)
  })

  it('takes no answer for a failure when no maintenance was seen', async () => {
    s.loginPassword.mockRejectedValue(Object.assign(new Error('Network error'), { status: 0 }))
    renderLogin()
    await submitPassword()
    await waitFor(() => expect(s.showError).toHaveBeenCalledWith('Network error'))
    expect(screen.queryByRole('status')).toBeNull()
    await tick(15000)
    expect(s.loginPassword).toHaveBeenCalledTimes(1)
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

  it('drops the planned attempt when the user signs in again by hand', async () => {
    let inFlight = 0, peak = 0
    s.loginPassword.mockRejectedValueOnce(refused(2)).mockImplementation(() => {
      inFlight += 1; peak = Math.max(peak, inFlight)
      return new Promise(resolve => setTimeout(() => { inFlight -= 1; resolve({ user: { username: 'alice' } }) }, 3000))
    })
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    fireEvent.click(screen.getByText('auth.login'))
    await tick(5000)
    await waitFor(() => expect(s.navigate).toHaveBeenCalledWith('/dashboard'))
    expect(peak).toBe(1)
    expect(s.loginPassword).toHaveBeenCalledTimes(2)
  })

  it('takes no answer for a failure once the user signs in by hand', async () => {
    s.loginPassword.mockRejectedValueOnce(refused(30)).mockRejectedValue(Object.assign(new Error('Network error'), { status: 0 }))
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    fireEvent.click(screen.getByText('auth.login'))
    await waitFor(() => expect(s.showError).toHaveBeenCalledWith('Network error'))
    expect(screen.queryByRole('status')).toBeNull()
    await tick(10000)
    expect(s.loginPassword).toHaveBeenCalledTimes(2)
  })

  it('tries a security key again from the button only, never by itself', async () => {
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true })
    s.loginPassword.mockRejectedValueOnce(new Error('Invalid credentials'))
    s.authenticateWebAuthn.mockRejectedValueOnce(refused(2))
      .mockRejectedValue(Object.assign(new Error('Network error'), { status: 0 }))
    renderLogin()
    await submitPassword()
    await waitFor(() => expect(s.showError).toHaveBeenCalledWith('Invalid credentials'))
    fireEvent.click(screen.getByText('auth.useSecurityKey'))
    const banner = await screen.findByRole('status')
    expect(banner).not.toHaveTextContent('auth.maintenanceRetryIn')
    await tick(5000)
    expect(s.authenticateWebAuthn).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByText('auth.retryNow'))
    await waitFor(() => expect(s.authenticateWebAuthn).toHaveBeenCalledTimes(2))
    // The key needs a touch: no answer ends the wait, it is not tried again by itself
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    await tick(15000)
    expect(s.authenticateWebAuthn).toHaveBeenCalledTimes(2)
  })

  it('makes no planned attempt while a security key sign-in waits', async () => {
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true })
    s.authenticateWebAuthn.mockImplementation(() => new Promise(() => {}))
    s.loginPassword.mockRejectedValueOnce(refused(2))
    renderLogin()
    await submitPassword()
    await screen.findByRole('status')
    fireEvent.click(screen.getByText('auth.useSecurityKey'))
    await waitFor(() => expect(s.authenticateWebAuthn).toHaveBeenCalledTimes(1))
    await tick(5000)
    expect(s.loginPassword).toHaveBeenCalledTimes(1)
  })
})
