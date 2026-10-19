/**
 * LoginPage 2FA step: a security key offered next to (or instead of) TOTP,
 * following the second factors the password login reports.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const services = vi.hoisted(() => ({
  detectMethods: vi.fn(),
  loginPassword: vi.fn(),
  login2FAWebAuthn: vi.fn(),
  login: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
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
    login2FAWebAuthn: services.login2FAWebAuthn,
    isWebAuthnSupported: () => true,
  },
}))

import LoginPage from '../LoginPage'

async function reachSecondFactor(methods) {
  services.loginPassword.mockResolvedValue({ requires_2fa: true, methods })
  render(<MemoryRouter initialEntries={['/login']}><LoginPage /></MemoryRouter>)
  fireEvent.change(await screen.findByPlaceholderText('auth.enterUsername'), { target: { value: 'alice' } })
  fireEvent.click(screen.getByText('auth.continue'))
  fireEvent.change(await screen.findByPlaceholderText('auth.enterPassword'), { target: { value: 'pw' } })
  fireEvent.click(screen.getByText('auth.login'))
  await screen.findByText('auth.twoFactorTitle')
}

describe('LoginPage: security key at the 2FA step', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    try { localStorage.clear() } catch { /* ignore */ }
    services.detectMethods.mockResolvedValue({ password: true, webauthn: true })
  })

  it('offers the key next to the TOTP code', async () => {
    await reachSecondFactor(['totp', 'webauthn'])
    expect(screen.getByPlaceholderText('000000')).toBeInTheDocument()
    expect(screen.getByText('auth.twoFactorUseSecurityKey')).toBeInTheDocument()
  })

  it('shows only the key when TOTP is not enrolled', async () => {
    await reachSecondFactor(['webauthn'])
    expect(screen.queryByPlaceholderText('000000')).not.toBeInTheDocument()
    expect(screen.getByText('auth.twoFactorKeyDescription')).toBeInTheDocument()
  })

  it('shows no key button without a registered key', async () => {
    await reachSecondFactor(['totp'])
    expect(screen.queryByText('auth.twoFactorUseSecurityKey')).not.toBeInTheDocument()
  })

  it('completes the login with the key', async () => {
    const userData = { user: { username: 'alice' } }
    services.login2FAWebAuthn.mockResolvedValue(userData)
    await reachSecondFactor(['totp', 'webauthn'])
    fireEvent.click(screen.getByText('auth.twoFactorUseSecurityKey'))
    await waitFor(() => expect(services.login).toHaveBeenCalledWith('alice', 'pw', userData))
  })

  it('reports a refused key', async () => {
    services.login2FAWebAuthn.mockRejectedValue(Object.assign(new Error('Security key verification failed'), { status: 401 }))
    await reachSecondFactor(['webauthn'])
    fireEvent.click(screen.getByText('auth.twoFactorUseSecurityKey'))
    await waitFor(() => expect(services.showError).toHaveBeenCalledWith('auth.twoFactorKeyFailed'))
    expect(services.login).not.toHaveBeenCalled()
  })
})
