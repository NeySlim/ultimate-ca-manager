/** Forgotten password and reset pages in the sign-in frame: every state and its way out. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const s = vi.hoisted(() => ({ forgotPassword: vi.fn(), resetPassword: vi.fn() }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
}))
vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../services', () => ({ authService: s }))
vi.mock('../../lib/passwordStrength', async (orig) => ({
  ...(await orig()),
  fetchPasswordStrength: vi.fn(async () => ({ score: 20, level: 'weak' })),
}))

import ForgotPasswordPage from '../ForgotPasswordPage'
import ResetPasswordPage from '../ResetPasswordPage'

const renderAt = (entry) => render(
  <MemoryRouter initialEntries={[entry]}>
    <Routes>
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/login" element={<p>login-page</p>} />
    </Routes>
  </MemoryRouter>
)

describe('ForgotPasswordPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('focuses nothing when it opens', () => {
    renderAt('/forgot-password')
    expect(document.activeElement).toBe(document.body)
  })

  it('names a wrong address beside its field and sends nothing', () => {
    renderAt('/forgot-password')
    fireEvent.change(screen.getByLabelText('common.emailAddress'), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.sendResetLink' }))
    expect(screen.getByLabelText('common.emailAddress')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('auth.validEmailRequired')).toBeInTheDocument()
    expect(s.forgotPassword).not.toHaveBeenCalled()
  })

  it('answers the same whether the server accepts or not', async () => {
    s.forgotPassword.mockRejectedValue(new Error('unknown'))
    renderAt('/forgot-password')
    fireEvent.change(screen.getByLabelText('common.emailAddress'), { target: { value: 'a@b.example' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.sendResetLink' }))
    expect(await screen.findByRole('heading', { name: 'auth.checkYourEmail' })).toBeInTheDocument()
    expect(screen.getByText('a@b.example')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'auth.tryAnotherEmail' }))
    expect(screen.getByRole('heading', { name: 'auth.forgotPasswordTitle' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'auth.backToLogin' }))
    expect(screen.getByText('login-page')).toBeInTheDocument()
  })
})

describe('ResetPasswordPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('says a link without token is invalid and offers a new one', () => {
    renderAt('/reset-password')
    expect(screen.getByRole('heading', { name: 'auth.invalidLink' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'auth.requestNewResetLink' })).toHaveAttribute('href', '/forgot-password')
  })

  it('refuses a short or unconfirmed password, then resets it', async () => {
    s.resetPassword.mockResolvedValue({})
    renderAt('/reset-password?token=t1')
    const submit = () => fireEvent.click(screen.getByRole('button', { name: 'auth.resetPasswordTitle' }))
    const fresh = screen.getByLabelText('common.newPassword')
    const confirm = screen.getByLabelText('common.confirmPassword')
    fireEvent.change(fresh, { target: { value: 'short' } })
    submit()
    // A field error sits under its field, red, and the field takes the focus
    expect(fresh).toHaveAttribute('aria-invalid', 'true')
    expect(document.getElementById(fresh.getAttribute('aria-describedby').split(' ').find(id => id.endsWith('-error'))))
      .toHaveTextContent('auth.passwordMinLength')
    expect(document.activeElement).toBe(fresh)
    expect(screen.queryByRole('alert')).toBeNull()
    expect(await screen.findByText('passwordStrength.weak')).toBeInTheDocument()
    fireEvent.change(fresh, { target: { value: 'long enough 1' } })
    expect(fresh).not.toHaveAttribute('aria-invalid')
    fireEvent.change(confirm, { target: { value: 'other' } })
    submit()
    expect(confirm).toHaveAttribute('aria-invalid', 'true')
    expect(confirm).toHaveAttribute('aria-describedby', 'reset-confirm-error')
    expect(screen.getByText('common.passwordMismatch').closest('.auth-field')).toContainElement(confirm)
    expect(document.activeElement).toBe(confirm)
    fireEvent.change(confirm, { target: { value: 'long enough 1' } })
    submit()
    await waitFor(() => expect(s.resetPassword).toHaveBeenCalledWith('t1', 'long enough 1'))
    expect(await screen.findByRole('heading', { name: 'auth.passwordReset' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'auth.goToLogin' }))
    expect(screen.getByText('login-page')).toBeInTheDocument()
  })

  it('shows the server refusal as sent', async () => {
    s.resetPassword.mockRejectedValue(new Error('Token expired'))
    renderAt('/reset-password?token=t1')
    fireEvent.change(screen.getByLabelText('common.newPassword'), { target: { value: 'long enough 1' } })
    fireEvent.change(screen.getByLabelText('common.confirmPassword'), { target: { value: 'long enough 1' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.resetPasswordTitle' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Token expired')
  })
})
