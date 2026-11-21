/**
 * Forced password change: the server refuses everything else, so the prompt
 * offers the change or a logout, never a way past it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mocks = vi.hoisted(() => ({
  logout: vi.fn(),
  changePassword: vi.fn(),
  getPasswordPolicy: vi.fn(),
  showError: vi.fn(),
  showSuccess: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../i18n', () => ({ languages: [{ code: 'en', name: 'English', flag: 'EN' }] }))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ logout: mocks.logout }),
  useNotification: () => ({ showError: mocks.showError, showSuccess: mocks.showSuccess }),
}))

vi.mock('../../services', () => ({
  accountService: { changePassword: mocks.changePassword },
  usersService: { getPasswordPolicy: mocks.getPasswordPolicy },
}))

import { ForcePasswordChange } from '../ForcePasswordChange'

// The gate is the sign-in card, in the router and theme the application gives it
const render = (ui) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>)

describe('ForcePasswordChange', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPasswordPolicy.mockResolvedValue({ data: { min_length: 8 } })
  })

  it('offers a logout and no way to skip the change', () => {
    const onComplete = vi.fn()
    render(<ForcePasswordChange onComplete={onComplete} />)
    expect(screen.queryByText('password.skipForNow')).toBeNull()
    // In the card, only the change and the logout: no close button, no skip
    const card = screen.getByRole('region', { name: 'password.changeRequired' })
    expect(within(card).getAllByRole('button').map(b => b.textContent)).toEqual(['common.changePassword', 'common.logout'])
    fireEvent.click(screen.getByText('common.logout'))
    expect(mocks.logout).toHaveBeenCalledTimes(1)
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('lifts the gate in place, keeping the success toast on screen', async () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const onComplete = vi.fn()
    mocks.changePassword.mockResolvedValue({ data: {} })
    render(<ForcePasswordChange onComplete={onComplete} />)
    for (const input of document.querySelectorAll('input[type="password"]')) {
      fireEvent.change(input, { target: { value: 'Replaced-Pass-456!' } })
    }
    fireEvent.click(screen.getByText('common.changePassword'))
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1))
    expect(mocks.showSuccess).toHaveBeenCalledWith('password.changeSuccess')
    expect(reload).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('names a refused field beside it in the sign-in card, the field focused, nothing sent', async () => {
    render(<ForcePasswordChange onComplete={vi.fn()} />)
    await waitFor(() => expect(mocks.getPasswordPolicy).toHaveBeenCalled())
    const fresh = screen.getByLabelText('common.newPassword')
    fireEvent.change(fresh, { target: { value: 'short' } })
    fireEvent.click(screen.getByText('common.changePassword'))
    expect(fresh).toHaveAttribute('aria-invalid', 'true')
    expect(fresh).toHaveAttribute('aria-describedby', 'err-force-new')
    expect(document.getElementById('err-force-new')).toHaveTextContent('password.minLength')
    expect(document.getElementById('err-force-new').closest('.field')).toContainElement(fresh)
    expect(document.activeElement).toBe(fresh)
    fireEvent.change(fresh, { target: { value: 'Long-enough-1' } })
    fireEvent.click(screen.getByText('common.changePassword'))
    const confirm = screen.getByLabelText('common.confirmNewPassword')
    expect(document.getElementById('err-force-confirm')).toHaveTextContent('common.passwordMismatch')
    expect(document.activeElement).toBe(confirm)
    expect(mocks.changePassword).not.toHaveBeenCalled()
    expect(fresh.closest('section')).toHaveClass('auth-card')
  })
})
