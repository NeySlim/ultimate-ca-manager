/** Parcours 18 and 20: return to the page asked for, and the server's 429 shown as sent. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const services = vi.hoisted(() => ({ detectMethods: vi.fn(), loginPassword: vi.fn(), login: vi.fn(), showError: vi.fn() }))

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
  useAuth: () => ({ login: services.login, sessionChecked: true }),
  useNotification: () => ({ showError: services.showError, showSuccess: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'default', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))
vi.mock('../../services/auth.service', () => ({
  authService: {
    getSsoProviders: vi.fn().mockResolvedValue({ data: [] }),
    isEmailConfigured: vi.fn().mockResolvedValue({ configured: false }),
  },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    detectMethods: services.detectMethods,
    loginPassword: services.loginPassword,
    isWebAuthnSupported: () => false,
  },
}))

import LoginPage from '../LoginPage'

function Where() {
  const l = useLocation()
  return <output data-testid="where">{l.pathname + l.search}</output>
}

async function signIn(entry) {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes><Route path="/login" element={<LoginPage />} /><Route path="*" element={<Where />} /></Routes>
    </MemoryRouter>
  )
  fireEvent.change(await screen.findByPlaceholderText('auth.enterUsername'), { target: { value: 'alice' } })
  fireEvent.click(screen.getByText('auth.continue'))
  fireEvent.change(await screen.findByPlaceholderText('auth.enterPassword'), { target: { value: 'pw' } })
  fireEvent.click(screen.getByText('auth.login'))
}

describe('LoginPage return path', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    try { localStorage.clear() } catch { /* ignore */ }
    services.detectMethods.mockResolvedValue({ password: true })
    services.login.mockResolvedValue(undefined)
  })

  it('returns to a known internal page', async () => {
    services.loginPassword.mockResolvedValue({ user: { username: 'alice' } })
    await signIn('/login?next=%2Facme%3Ftab%3Dorders')
    expect(await screen.findByTestId('where')).toHaveTextContent('/acme?tab=orders')
  })

  it.each(['//evil.example', 'https://evil.example/', '/no-such-page', '/\\evil.example'])('sends %s to the dashboard', async (next) => {
    services.loginPassword.mockResolvedValue({ user: { username: 'alice' } })
    await signIn(`/login?next=${encodeURIComponent(next)}`)
    expect(await screen.findByTestId('where')).toHaveTextContent('/dashboard')
  })

  it('shows the server 429 without a countdown, with the wait when it is given', async () => {
    const err = Object.assign(new Error('Too many failed attempts. Try again later.'), { status: 429, retryAfter: 30 })
    services.loginPassword.mockRejectedValue(err)
    await signIn('/login')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('auth.tooManyAttempts')
    expect(alert).toHaveTextContent('auth.retryAfterSeconds|30')
    expect(services.showError).not.toHaveBeenCalled()
  })

  it('says only "later" when the server gives no wait, and keeps toasts for other errors', async () => {
    services.loginPassword.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 429 }))
    await signIn('/login')
    expect(await screen.findByRole('alert')).toHaveTextContent('auth.retryLater')
  })
})
