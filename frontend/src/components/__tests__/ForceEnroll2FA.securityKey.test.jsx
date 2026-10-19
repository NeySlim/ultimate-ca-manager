/**
 * Forced 2FA enrolment: a security key can be registered instead of TOTP.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  enable2FA: vi.fn(),
  registerWebAuthnKey: vi.fn(),
  showError: vi.fn(),
  showSuccess: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ logout: vi.fn() }),
  useNotification: () => ({ showError: mocks.showError, showSuccess: mocks.showSuccess }),
}))

vi.mock('../../services', () => ({
  accountService: { enable2FA: mocks.enable2FA, registerWebAuthnKey: mocks.registerWebAuthnKey },
}))

import { ForceEnroll2FA } from '../ForceEnroll2FA'

describe('ForceEnroll2FA: security key', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.PublicKeyCredential = function PublicKeyCredential() {}
    mocks.enable2FA.mockResolvedValue({ data: { qr_code: 'data:image/png;base64,AA==' } })
  })

  afterEach(() => { delete window.PublicKeyCredential })

  it('registers a key and lifts the enrolment', async () => {
    mocks.registerWebAuthnKey.mockResolvedValue({ data: {} })
    const onComplete = vi.fn()
    render(<ForceEnroll2FA onComplete={onComplete} />)
    fireEvent.change(screen.getByPlaceholderText('account.keyNamePlaceholder'), { target: { value: 'YubiKey' } })
    fireEvent.click(screen.getByText('account.registerKey'))
    await waitFor(() => expect(onComplete).toHaveBeenCalled())
    expect(mocks.registerWebAuthnKey).toHaveBeenCalledWith('YubiKey')
  })

  it('stays in enrolment when the registration fails', async () => {
    mocks.registerWebAuthnKey.mockRejectedValue(Object.assign(new Error('x'), { name: 'NotAllowedError' }))
    const onComplete = vi.fn()
    render(<ForceEnroll2FA onComplete={onComplete} />)
    fireEvent.click(screen.getByText('account.registerKey'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('account.registrationCancelled'))
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('offers no key without WebAuthn support', () => {
    delete window.PublicKeyCredential
    render(<ForceEnroll2FA onComplete={vi.fn()} />)
    expect(screen.queryByText('account.registerKey')).not.toBeInTheDocument()
  })
})
