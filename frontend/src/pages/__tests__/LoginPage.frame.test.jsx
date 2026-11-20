/** The sign-in form of the frame: fields, reveal, inline errors and every other door. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const s = vi.hoisted(() => ({
  loginPassword: vi.fn(), loginMTLS: vi.fn(), authenticateWebAuthn: vi.fn(), login: vi.fn(), getSsoProviders: vi.fn(),
  detectMethods: vi.fn(), isEmailConfigured: vi.fn(), supported: true,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, o) => (o?.username != null ? `${key}|${o.username}` : key), i18n: { language: 'en', changeLanguage: vi.fn() } }),
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
  authService: { getSsoProviders: s.getSsoProviders, isEmailConfigured: s.isEmailConfigured },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    detectMethods: s.detectMethods, loginPassword: s.loginPassword, loginMTLS: s.loginMTLS,
    authenticateWebAuthn: s.authenticateWebAuthn, isWebAuthnSupported: () => s.supported,
  },
}))

import LoginPage from '../LoginPage'

function Where() {
  const l = useLocation()
  return <output data-testid="where">{l.pathname + l.search}</output>
}
const renderLogin = (entry = '/login') => render(
  <MemoryRouter initialEntries={[entry]}>
    <Routes><Route path="/login" element={<LoginPage />} /><Route path="*" element={<Where />} /></Routes>
  </MemoryRouter>
)

describe('LoginPage form', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    s.supported = true
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, mtls: false, mtls_status: 'not_present' })
    s.getSsoProviders.mockResolvedValue({ data: [] })
    s.isEmailConfigured.mockResolvedValue({ configured: false })
    s.login.mockResolvedValue(undefined)
  })

  it('asks for both fields at once, under the sign-in title', async () => {
    renderLogin()
    expect(await screen.findByRole('heading', { name: 'auth.page.signInTitle' })).toBeInTheDocument()
    expect(screen.getByText('auth.page.lead')).toBeInTheDocument()
    expect(screen.getByLabelText('auth.page.username')).toHaveAttribute('autocomplete', 'username')
    expect(screen.getByLabelText('auth.page.password')).toHaveAttribute('autocomplete', 'current-password')
    expect(document.activeElement).toBe(screen.getByLabelText('auth.page.username'))
  })

  it('names each empty field beside it and focuses the first', async () => {
    renderLogin()
    fireEvent.click(await screen.findByRole('button', { name: 'auth.page.submit' }))
    const user = screen.getByLabelText('auth.page.username')
    expect(user).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('auth.page.usernameMissing')).toBeInTheDocument()
    expect(screen.getByText('auth.page.passwordMissing')).toBeInTheDocument()
    expect(document.activeElement).toBe(user)
    expect(s.loginPassword).not.toHaveBeenCalled()
  })

  it('fills in the last username and starts on the password', async () => {
    localStorage.setItem('ucm_last_username', 'alice')
    renderLogin()
    expect(await screen.findByLabelText('auth.page.username')).toHaveValue('alice')
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('auth.page.password')))
  })

  it('shows and hides the password', async () => {
    renderLogin()
    const pass = await screen.findByLabelText('auth.page.password')
    const reveal = screen.getByRole('button', { name: 'auth.page.showPassword' })
    expect(pass).toHaveAttribute('type', 'password')
    fireEvent.click(reveal)
    expect(pass).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'auth.page.hidePassword' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows a refused sign-in in the card, as the server says it, and empties the password', async () => {
    s.loginPassword.mockRejectedValue(new Error('Invalid username or password'))
    renderLogin()
    fireEvent.change(await screen.findByLabelText('auth.page.username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('auth.page.password'), { target: { value: 'bad' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.submit' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password')
    expect(screen.getByLabelText('auth.page.password')).toHaveValue('')
  })

  it('offers every other door after "or": SSO, LDAP, client certificate, security key', async () => {
    s.getSsoProviders.mockResolvedValue({ data: [
      { id: 1, name: 'kc', display_name: 'Company SSO', provider_type: 'oauth2' },
      { id: 2, name: 'idp', display_name: 'Partner', provider_type: 'saml' },
      { id: 3, name: 'ad', display_name: 'Corporate LDAP', provider_type: 'ldap' },
    ] })
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, mtls: true, mtls_status: 'enrolled', mtls_user: 'alice' })
    s.isEmailConfigured.mockResolvedValue({ configured: true })
    renderLogin()
    expect(await screen.findByText('auth.page.or')).toBeInTheDocument()
    expect(screen.getAllByText('auth.page.ssoButton')).toHaveLength(2)
    expect(screen.getByText('Company SSO').closest('small')).toHaveTextContent('Company SSO · OAuth 2.0')
    expect(screen.getByText('Partner').closest('small')).toHaveTextContent('Partner · SAML 2.0')
    expect(screen.getByText('auth.page.ldapButton')).toBeInTheDocument()
    expect(screen.getByText('auth.page.mtlsDetail|alice')).toBeInTheDocument()
    expect(screen.getByText('auth.page.keyButton')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'auth.forgotPassword' })).toHaveAttribute('href', '/forgot-password')
  })

  it('signs in with the enrolled client certificate', async () => {
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, mtls: true, mtls_status: 'enrolled', mtls_user: 'alice' })
    s.loginMTLS.mockResolvedValue({ user: { username: 'alice' } })
    renderLogin('/login?next=%2Fcas')
    fireEvent.click(await screen.findByText('auth.page.mtlsButton'))
    await waitFor(() => expect(s.login).toHaveBeenCalledWith('alice', null, { user: { username: 'alice' } }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/cas')
  })

  it('offers no client certificate that is absent or not enrolled, and no key the browser lacks', async () => {
    s.supported = false
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, mtls: true, mtls_status: 'present_not_enrolled' })
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    expect(screen.queryByText('auth.page.mtlsButton')).toBeNull()
    expect(screen.queryByText('auth.page.keyButton')).toBeNull()
    expect(screen.queryByText('auth.page.or')).toBeNull()
  })

  it('asks for the username before a security key', async () => {
    renderLogin()
    fireEvent.click(await screen.findByText('auth.page.keyButton'))
    expect(screen.getByText('auth.page.usernameMissing')).toBeInTheDocument()
    expect(s.authenticateWebAuthn).not.toHaveBeenCalled()
  })

  it('puts the security key first after a key sign-in on this device', async () => {
    localStorage.setItem('ucm_last_username', 'alice')
    localStorage.setItem('ucm_last_auth_method', JSON.stringify({ method: 'webauthn' }))
    s.getSsoProviders.mockResolvedValue({ data: [{ id: 1, name: 'kc', display_name: 'Company SSO', provider_type: 'oauth2' }] })
    renderLogin()
    await screen.findByText('auth.page.keyButton')
    const doors = [...document.querySelectorAll('.auth-alt')].map(b => b.textContent)
    expect(doors[0]).toContain('auth.page.keyButton')
  })
})
