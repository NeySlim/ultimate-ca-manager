/**
 * Reset from an emailed link: the minimum length is the server's password policy, as on the
 * other password forms, not a fixed eight.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({ resetPassword: vi.fn(), getPasswordPolicy: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts ? `${key} ${JSON.stringify(opts)}` : key), i18n: { language: 'en', changeLanguage: vi.fn() } }),
}))
vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../lib/passwordStrength', async (orig) => ({
  ...(await orig()),
  fetchPasswordStrength: vi.fn(async () => ({ score: 20, level: 'weak' })),
}))
vi.mock('../../services', () => ({
  authService: { resetPassword: m.resetPassword },
  usersService: { getPasswordPolicy: m.getPasswordPolicy },
}))

import ResetPasswordPage from '../ResetPasswordPage'

const mount = () => render(<MemoryRouter initialEntries={['/reset-password?token=abc']}><ResetPasswordPage /></MemoryRouter>)

const submitWith = (password) => {
  fireEvent.change(screen.getByLabelText('common.newPassword'), { target: { value: password } })
  fireEvent.change(screen.getByLabelText('common.confirmPassword'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'auth.resetPasswordTitle' }))
}

describe('ResetPasswordPage minimum length', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    m.resetPassword.mockResolvedValue({})
  })

  it('accepts a password the policy allows below eight characters', async () => {
    m.getPasswordPolicy.mockResolvedValue({ data: { min_length: 6 } })
    mount()
    await waitFor(() => expect(screen.getByText(/auth\.minCharacters/)).toHaveTextContent('"min_length":6'))
    submitWith('Ab1-xyz')
    await waitFor(() => expect(m.resetPassword).toHaveBeenCalledWith('abc', 'Ab1-xyz'))
  })

  it('refuses a password shorter than a policy of twelve, naming twelve', async () => {
    m.getPasswordPolicy.mockResolvedValue({ data: { min_length: 12 } })
    mount()
    await waitFor(() => expect(screen.getByText(/auth\.minCharacters/)).toHaveTextContent('"min_length":12'))
    submitWith('Abcdef-12x')
    expect(await screen.findByText(/auth\.passwordMinLength/)).toHaveTextContent('"min_length":12')
    expect(m.resetPassword).not.toHaveBeenCalled()
  })

  it('falls back to eight when the policy cannot be read', async () => {
    m.getPasswordPolicy.mockRejectedValue(new Error('offline'))
    mount()
    await waitFor(() => expect(m.getPasswordPolicy).toHaveBeenCalled())
    expect(screen.getByText(/auth\.minCharacters/)).toHaveTextContent('"min_length":8')
    submitWith('Ab1-xyz')
    expect(await screen.findByText(/auth\.passwordMinLength/)).toHaveTextContent('"min_length":8')
    expect(m.resetPassword).not.toHaveBeenCalled()
  })
})
