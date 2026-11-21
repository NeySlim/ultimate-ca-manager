/**
 * Sign-in page drawn from the mockup's authPage() and loginSubmit(): its nodes and classes, the
 * #login-error live region always there, the field errors of authFieldError(), the reveal
 * button, the doors as `.btn.auth-alt`, the maintenance notice, and signOut()'s greeting.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { markSignedOut, saveLock } from '../../lib/sessionLock'

const s = vi.hoisted(() => ({
  loginPassword: vi.fn(), login: vi.fn(), getSsoProviders: vi.fn(), detectMethods: vi.fn(),
  isEmailConfigured: vi.fn(), showSuccess: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
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
  authService: { getSsoProviders: s.getSsoProviders, isEmailConfigured: s.isEmailConfigured, ldapLogin: vi.fn() },
}))
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: { detectMethods: s.detectMethods, loginPassword: s.loginPassword, isWebAuthnSupported: () => true },
}))

import LoginPage from '../LoginPage'
import { PATHS } from '../../components/atelier/icons'

const renderLogin = () => render(
  <MemoryRouter initialEntries={['/login']}>
    <Routes><Route path="/login" element={<LoginPage />} /><Route path="*" element={<p>console</p>} /></Routes>
  </MemoryRouter>
)
// The icon a button draws, named by the mockup's paths
const drawn = (html) => { const g = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); g.innerHTML = html; return g.innerHTML }
const iconOf = (el) => Object.keys(PATHS).find(k => drawn(PATHS[k]) === el.querySelector('svg.icon').innerHTML)

describe('LoginPage, node for node with the mockup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    s.detectMethods.mockResolvedValue({ password: true, webauthn: true, mtls: false })
    s.getSsoProviders.mockResolvedValue({ data: [{ id: 4, name: 'kc', display_name: 'Company SSO', provider_type: 'oauth2' }] })
    s.isEmailConfigured.mockResolvedValue({ data: { configured: false } })
  })

  it('draws the form of authPage(): fields, empty #login-error, primary submit, "or", the doors', async () => {
    renderLogin()
    const form = (await screen.findByLabelText('auth.page.username')).closest('form')
    expect(form).toHaveAttribute('id', 'login-form')
    expect(form).toHaveClass('auth-form')
    expect([...form.children].map(el => el.className)).toEqual(['field', 'field', 'form-error', 'btn primary auth-submit'])
    expect(form.querySelector('#login-error')).toHaveAttribute('role', 'alert')
    expect(form.querySelector('#login-error')).toBeEmptyDOMElement()
    expect(form.querySelector('.password-wrap > #login-pass + button#login-reveal.icon-btn.quiet')).not.toBeNull()
    expect(iconOf(screen.getByRole('button', { name: 'auth.page.submit' }))).toBe('right')
    const card = form.parentElement
    expect(card.querySelector(':scope > p.auth-sep > span')).toHaveTextContent('auth.page.or')
    const sso = card.querySelector(':scope > button#login-sso-4.btn.auth-alt')
    expect(sso).toHaveTextContent('auth.page.ssoButton')
    expect(sso.querySelector('span > small')).toHaveTextContent('Company SSO · OAuth 2.0')
    expect(iconOf(sso)).toBe('users')
    expect(card.querySelector(':scope > button#login-key.btn.auth-alt')).not.toBeNull()
  })

  it('names an empty field beside it as authFieldError() does, err-<id> described', async () => {
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.submit' }))
    const user = screen.getByLabelText('auth.page.username')
    expect(user).toHaveAttribute('aria-describedby', 'err-login-user')
    const error = document.getElementById('err-login-user')
    expect(error).toHaveClass('field-error')
    expect(error.parentElement).toHaveClass('field')
    expect(iconOf(error)).toBe('warning')
    expect(error).toHaveTextContent('auth.page.usernameMissing')
    expect(document.getElementById('err-login-pass')).toHaveTextContent('auth.page.passwordMissing')
    expect(document.activeElement).toBe(user)
  })

  it('reveals the password with the eye, which turns into the hide icon, pressed', async () => {
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    const reveal = screen.getByRole('button', { name: 'auth.page.showPassword' })
    expect(iconOf(reveal)).toBe('eye')
    fireEvent.click(reveal)
    expect(reveal).toHaveAttribute('aria-pressed', 'true')
    expect(iconOf(reveal)).toBe('hide')
    expect(screen.getByLabelText('auth.page.password')).toHaveAttribute('type', 'text')
  })

  it('puts the refused attempt in #login-error with the warning icon', async () => {
    s.loginPassword.mockRejectedValue(Object.assign(new Error('nope'), { status: 401 }))
    renderLogin()
    fireEvent.change(await screen.findByLabelText('auth.page.username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('auth.page.password'), { target: { value: 'bad' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.submit' }))
    await waitFor(() => expect(document.getElementById('login-error')).toHaveTextContent('auth.page.refused'))
    expect(iconOf(document.getElementById('login-error'))).toBe('warning')
  })

  it('shows a maintenance as the mockup\'s warning notice, its retry a text link inside', async () => {
    s.loginPassword.mockRejectedValue(Object.assign(new Error('m'), { status: 503, data: { code: 'maintenance' }, retryAfter: 10 }))
    renderLogin()
    fireEvent.change(await screen.findByLabelText('auth.page.username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('auth.page.password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.page.submit' }))
    const notice = await screen.findByRole('status')
    expect(notice).toHaveClass('notice', 'warn')
    expect(notice.parentElement).toHaveClass('auth-card')
    expect(notice.querySelector('span > button.text-link')).toHaveTextContent('auth.retryNow')
  })

  it('draws the locked account as auth-user with the avatar, and the switch as auth-switch', async () => {
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
    renderLogin()
    const card = (await screen.findByText('Alice Martin')).closest('.auth-user')
    expect(card.querySelector(':scope > span.avatar')).toHaveTextContent('AM')
    expect(card.querySelector('.mono')).toHaveTextContent('alice')
    expect(screen.getByRole('button', { name: 'auth.page.switchAccount' })).toHaveClass('text-link', 'auth-switch')
    expect(iconOf(screen.getByRole('button', { name: 'auth.page.unlock' }))).toBe('lock')
  })
})

describe("LoginPage after a sign-out (the mockup's signOut())", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    s.detectMethods.mockResolvedValue({ password: true, webauthn: false, mtls: false })
    s.getSsoProviders.mockResolvedValue({ data: [] })
    s.isEmailConfigured.mockResolvedValue({ data: { configured: false } })
  })

  it('says the sign-out once and focuses the title', async () => {
    markSignedOut()
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    await waitFor(() => expect(s.showSuccess).toHaveBeenCalledWith('auth.page.signedOut'))
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'auth.page.signInTitle' }))
    cleanup()
    s.showSuccess.mockClear()
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    expect(s.showSuccess).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(document.body)
  })

  it('says nothing on a plain visit', async () => {
    renderLogin()
    await screen.findByLabelText('auth.page.username')
    expect(s.showSuccess).not.toHaveBeenCalled()
  })
})
