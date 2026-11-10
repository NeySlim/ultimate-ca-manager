/** An OAuth2/SAML sign-in returns to the page asked for, only when safeNext accepts it. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const services = vi.hoisted(() => ({ getSsoProviders: vi.fn(), verifySession: vi.fn(), login: vi.fn() }))

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
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'default', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))
vi.mock('../../services/auth.service', () => ({
  authService: {
    getSsoProviders: services.getSsoProviders,
    verifySession: services.verifySession,
    isEmailConfigured: vi.fn().mockResolvedValue({ configured: false }),
  },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: { detectMethods: vi.fn().mockResolvedValue({ password: true }), isWebAuthnSupported: () => false },
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

const realLocation = window.location

function stubLocation(pathname) {
  delete window.location
  window.location = { pathname, search: '', href: '' }
}

describe('LoginPage SSO return path', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    services.getSsoProviders.mockResolvedValue({
      data: [{ id: 1, name: 'kc', display_name: 'Company SSO', provider_type: 'oauth2' }],
    })
    services.login.mockResolvedValue(undefined)
    services.verifySession.mockResolvedValue({ data: { user: { username: 'alice' } } })
  })

  afterEach(() => {
    window.location = realLocation
  })

  it('starts the SSO login with the page asked for', async () => {
    stubLocation('/login')
    renderAt('/login?next=%2Fcertificates%3Fstatus%3Dexpiring')
    fireEvent.click(await screen.findByText('Company SSO'))
    expect(window.location.href).toBe('/api/v2/sso/login/oauth2?next=%2Fcertificates%3Fstatus%3Dexpiring')
  })

  it.each(['//evil.example', 'https://evil.example/', '/no-such-page', '/\\evil.example', '/login'])(
    'starts the SSO login without %s', async (next) => {
      stubLocation('/login')
      renderAt(`/login?next=${encodeURIComponent(next)}`)
      fireEvent.click(await screen.findByText('Company SSO'))
      expect(window.location.href).toBe('/api/v2/sso/login/oauth2')
    })

  it('starts the SSO login without a page when none was asked for', async () => {
    stubLocation('/login')
    renderAt('/login')
    fireEvent.click(await screen.findByText('Company SSO'))
    expect(window.location.href).toBe('/api/v2/sso/login/oauth2')
  })

  it('returns to the page the server hands back', async () => {
    stubLocation('/login/sso-complete')
    renderAt('/login/sso-complete?next=%2Fcas%3Ftab%3Dtree')
    expect(await screen.findByTestId('where')).toHaveTextContent('/cas?tab=tree')
    await waitFor(() => expect(services.login).toHaveBeenCalled())
  })

  it.each(['//evil.example', 'https://evil.example/', '/no-such-page', '/%2f%2fevil.example'])(
    'refuses a forged %s in the return URL', async (next) => {
      stubLocation('/login/sso-complete')
      renderAt(`/login/sso-complete?next=${encodeURIComponent(next)}`)
      expect(await screen.findByTestId('where')).toHaveTextContent(/^\/dashboard$/)
    })
})
