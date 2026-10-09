/**
 * LoginPage SSO provider loading.
 *
 * The page loads the SSO providers once, when it mounts. It is often reached
 * by an in-app redirect right after the session expired, e.g. when a laptop
 * wakes up before the network is back. A failed request used to leave the
 * page without SSO buttons until a full reload, and a failed /auth/methods
 * discarded providers that had loaded fine.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const services = vi.hoisted(() => ({
  getSsoProviders: vi.fn(),
  detectMethods: vi.fn(),
  isEmailConfigured: vi.fn(),
}))

const PROVIDERS = {
  data: [{ id: 1, name: 'keycloak', display_name: 'Company SSO', provider_type: 'oauth2' }],
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../i18n', () => ({
  languages: [{ code: 'en', name: 'English', flag: 'EN' }],
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ login: vi.fn(), sessionChecked: true }),
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }),
}))

vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'default', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))

vi.mock('../../services/auth.service', () => ({
  authService: {
    getSsoProviders: services.getSsoProviders,
    isEmailConfigured: services.isEmailConfigured,
  },
}))

vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: { detectMethods: services.detectMethods },
}))

import LoginPage from '../LoginPage'

function renderLogin() {
  return render(<MemoryRouter initialEntries={['/login']}><LoginPage /></MemoryRouter>)
}

const networkError = () => Object.assign(new Error('Network error'), { status: 0 })

describe('LoginPage — SSO provider loading', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    services.isEmailConfigured.mockResolvedValue({ configured: false })
    services.detectMethods.mockResolvedValue({ password: true, mtls: false })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the SSO button when providers load', async () => {
    services.getSsoProviders.mockResolvedValue(PROVIDERS)
    renderLogin()
    expect(await screen.findByText('Company SSO')).toBeInTheDocument()
  })

  it('keeps the SSO button when /auth/methods fails', async () => {
    services.getSsoProviders.mockResolvedValue(PROVIDERS)
    services.detectMethods.mockRejectedValue(networkError())
    renderLogin()
    expect(await screen.findByText('Company SSO')).toBeInTheDocument()
  })

  it('reloads the providers when the browser comes back online', async () => {
    services.getSsoProviders
      .mockRejectedValueOnce(networkError())
      .mockResolvedValue(PROVIDERS)
    renderLogin()

    // Login form is shown without SSO buttons after the failed load.
    expect(await screen.findByText('auth.signInToContinue')).toBeInTheDocument()
    expect(screen.queryByText('Company SSO')).not.toBeInTheDocument()

    await act(async () => { window.dispatchEvent(new Event('online')) })

    expect(await screen.findByText('Company SSO')).toBeInTheDocument()
    expect(services.getSsoProviders).toHaveBeenCalledTimes(2)
  })

  it('retries a failed load with backoff', async () => {
    vi.useFakeTimers()
    services.getSsoProviders
      .mockRejectedValueOnce(networkError())
      .mockRejectedValueOnce(networkError())
      .mockResolvedValue(PROVIDERS)
    renderLogin()

    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(services.getSsoProviders).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Company SSO')).not.toBeInTheDocument()

    // First retry after 2 s fails, second one after another 4 s succeeds.
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(services.getSsoProviders).toHaveBeenCalledTimes(2)
    await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
    expect(services.getSsoProviders).toHaveBeenCalledTimes(3)
    expect(screen.getByText('Company SSO')).toBeInTheDocument()

    // No further requests once the providers are loaded.
    await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
    expect(services.getSsoProviders).toHaveBeenCalledTimes(3)
  })
})
