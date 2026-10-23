/**
 * Forced password change: the server refuses everything else, so the prompt
 * offers the change or a logout, never a way past it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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

vi.mock('../../contexts', () => ({
  useAuth: () => ({ logout: mocks.logout }),
  useNotification: () => ({ showError: mocks.showError, showSuccess: mocks.showSuccess }),
}))

vi.mock('../../services', () => ({
  accountService: { changePassword: mocks.changePassword },
  usersService: { getPasswordPolicy: mocks.getPasswordPolicy },
}))

import { ForcePasswordChange } from '../ForcePasswordChange'

describe('ForcePasswordChange', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPasswordPolicy.mockResolvedValue({ data: { min_length: 8 } })
  })

  it('offers a logout and no way to skip the change', () => {
    const onComplete = vi.fn()
    render(<ForcePasswordChange onComplete={onComplete} />)
    expect(screen.queryByText('password.skipForNow')).toBeNull()
    // Only the change and the logout: no close button, no skip
    expect(screen.getAllByRole('button')).toHaveLength(2)
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
})
