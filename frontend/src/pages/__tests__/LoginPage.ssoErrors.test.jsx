/**
 * LoginPage: an SSO refusal handed back in ?error= is said in the card, in clear.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const services = vi.hoisted(() => ({
  getSsoProviders: vi.fn(),
  detectMethods: vi.fn(),
  isEmailConfigured: vi.fn(),
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

vi.mock('../../i18n', () => ({
  languages: [{ code: 'en', name: 'English', flag: 'EN' }],
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ login: vi.fn(), sessionChecked: true }),
  useNotification: () => ({ showError: services.showError, showSuccess: vi.fn(), showInfo: vi.fn() }),
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
  authMethodsService: { detectMethods: services.detectMethods, isWebAuthnSupported: () => false },
}))

import LoginPage from '../LoginPage'

describe('LoginPage SSO errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    services.isEmailConfigured.mockResolvedValue({ configured: false })
    services.detectMethods.mockResolvedValue({ password: true, mtls: false })
    services.getSsoProviders.mockResolvedValue({ data: [] })
  })

  it.each([
    ['sso_username_conflict', 'auth.ssoUsernameConflict'],
    ['sso_unmapped', 'auth.ssoUnmapped'],
    ['sso_no_default_role', 'auth.ssoNoDefaultRole'],
    ['sso_email_conflict', 'auth.ssoEmailConflict'],
    ['saml_logout_rejected', 'auth.samlLogoutRejected'],
  ])('explains the %s refusal', async (code, key) => {
    render(<MemoryRouter initialEntries={[`/login?error=${code}`]}><LoginPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(key))
  })

  it('asks to start an expired or foreign SAML login again', async () => {
    render(<MemoryRouter initialEntries={['/login?error=saml_login_expired']}><LoginPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('auth.samlLoginExpired'))
  })
})
