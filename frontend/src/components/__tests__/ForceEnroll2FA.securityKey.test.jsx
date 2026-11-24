/**
 * Forced 2FA enrolment: a security key can be registered instead of TOTP.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mocks = vi.hoisted(() => ({
  enable2FA: vi.fn(),
  confirm2FA: vi.fn(),
  registerWebAuthnKey: vi.fn(),
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
  useAuth: () => ({ logout: vi.fn() }),
  useNotification: () => ({ showError: mocks.showError, showSuccess: mocks.showSuccess }),
}))

vi.mock('../../services', () => ({
  accountService: { enable2FA: mocks.enable2FA, confirm2FA: mocks.confirm2FA, registerWebAuthnKey: mocks.registerWebAuthnKey },
}))

vi.mock('../../services/apiClient', async (importOriginal) => ({
  ...(await importOriginal()), holdSignOut: vi.fn(),
}))

import { ForceEnroll2FA } from '../ForceEnroll2FA'
import { holdSignOut } from '../../services/apiClient'

// The gate is the sign-in card, in the router and theme the application gives it
const render = (ui) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>)

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

  // Sessions the server reports closed: 0 says nothing of them, a count or no count does
  const CLOSED = [[0, ''], [2, ' account.otherSessionsClosed'], [undefined, ' account.otherSessionsClosed']]

  it.each(CLOSED)('a key registered with %s other sessions closed', async (closed, note) => {
    mocks.registerWebAuthnKey.mockResolvedValue({ data: {}, meta: closed === undefined ? {} : { other_sessions_closed: closed } })
    const onComplete = vi.fn()
    render(<ForceEnroll2FA onComplete={onComplete} />)
    fireEvent.click(screen.getByText('account.registerKey'))
    await waitFor(() => expect(onComplete).toHaveBeenCalled())
    expect(mocks.showSuccess).toHaveBeenCalledWith(`account.keyRegistered${note}`)
  })

  it.each(CLOSED)('TOTP confirmed with %s other sessions closed', async (closed, note) => {
    mocks.confirm2FA.mockResolvedValue({ data: { backup_codes: ['A-B'] }, ...(closed === undefined ? {} : { meta: { other_sessions_closed: closed } }) })
    const onComplete = vi.fn()
    render(<ForceEnroll2FA onComplete={onComplete} />)
    fireEvent.change(await screen.findByPlaceholderText('account.codePlaceholder'), { target: { value: '123456' } })
    fireEvent.click(screen.getByText('account.verifyAndEnable'))
    fireEvent.click(await screen.findByText('account.backupCodesSaved'))
    await waitFor(() => expect(onComplete).toHaveBeenCalled())
    expect(mocks.showSuccess).toHaveBeenCalledWith(`account.twoFaEnabled${note}`)
  })

  it('shows the QR code named in words, then the backup codes listed in the card', async () => {
    mocks.confirm2FA.mockResolvedValue({ data: { backup_codes: ['AAAA-1111', 'BBBB-2222'] } })
    render(<ForceEnroll2FA onComplete={vi.fn()} />)
    expect(await screen.findByRole('img', { name: 'account.qrCodeAlt' })).toHaveAttribute('src', 'data:image/png;base64,AA==')
    const verify = screen.getByRole('button', { name: 'account.verifyAndEnable' })
    expect(verify).toBeDisabled()
    fireEvent.change(screen.getByLabelText('account.enterDigitCode'), { target: { value: '12a3456' } })
    expect(screen.getByLabelText('account.enterDigitCode')).toHaveValue('123456')
    fireEvent.click(verify)
    const codes = await screen.findByRole('list')
    expect([...codes.querySelectorAll('li')].map(li => li.textContent)).toEqual(['AAAA-1111', 'BBBB-2222'])
    expect(codes.closest('section')).toHaveClass('auth-card')
  })

  it('still lists the codes when 2FA is saved but the session could not be kept', async () => {
    mocks.confirm2FA.mockRejectedValue(Object.assign(new Error('saved, sign in again'),
      { status: 500, data: { data: { backup_codes: ['AAAA-1111', 'BBBB-2222'] } } }))
    render(<ForceEnroll2FA onComplete={vi.fn()} />)
    fireEvent.change(await screen.findByPlaceholderText('account.codePlaceholder'), { target: { value: '123456' } })
    fireEvent.click(screen.getByText('account.verifyAndEnable'))
    const codes = await screen.findByRole('list')
    expect([...codes.querySelectorAll('li')].map(li => li.textContent)).toEqual(['AAAA-1111', 'BBBB-2222'])
    expect(mocks.showError).toHaveBeenCalledWith('saved, sign in again')
  })
})


describe('ForceEnroll2FA: recovery codes of an enrolment whose session was not kept', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.enable2FA.mockResolvedValue({ data: { qr_code: 'data:image/png;base64,AA==' } })
    mocks.confirm2FA.mockRejectedValue(Object.assign(new Error('saved, sign in again'),
      { status: 500, data: { data: { backup_codes: ['AAAA-BBBB', 'CCCC-DDDD'] } } }))
  })

  const confirm = async (onComplete) => {
    const view = render(<ForceEnroll2FA onComplete={onComplete} />)
    fireEvent.change(await screen.findByPlaceholderText('account.codePlaceholder'), { target: { value: '123456' } })
    fireEvent.click(screen.getByText('account.verifyAndEnable'))
    await screen.findByText('AAAA-BBBB')
    return view
  }

  it('keeps the codes on screen, the sign-out held, until they are acknowledged', async () => {
    const onComplete = vi.fn()
    await confirm(onComplete)
    expect(holdSignOut).toHaveBeenLastCalledWith()
    expect(onComplete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('account.backupCodesSaved'))
    await waitFor(() => expect(onComplete).toHaveBeenCalled())
    expect(holdSignOut).toHaveBeenLastCalledWith(false)
    // No success is announced for a session that is gone
    expect(mocks.showSuccess).not.toHaveBeenCalled()
  })

  it('releases the hold when the gate goes', async () => {
    const view = await confirm(vi.fn())
    view.unmount()
    expect(holdSignOut).toHaveBeenLastCalledWith(false)
  })
})
