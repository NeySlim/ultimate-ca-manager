/**
 * Account page: the recovery codes the server returns when TOTP is confirmed
 * are shown once, until the user says they are saved.
 */
import { describe, it, expect, vi, beforeEach, beforeAll, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({
  getProfile: vi.fn(),
  getWebAuthnCredentials: vi.fn(),
  setWebAuthnSecondFactor: vi.fn(),
  enable2FA: vi.fn(),
  confirm2FA: vi.fn(),
  showPrompt: vi.fn(),
  showSuccess: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../services', () => ({
  accountService: {
    getProfile: m.getProfile,
    getApiKeys: vi.fn().mockResolvedValue({ data: [] }),
    getWebAuthnCredentials: m.getWebAuthnCredentials,
    getMTLSCertificates: vi.fn().mockResolvedValue({ data: [] }),
    setWebAuthnSecondFactor: m.setWebAuthnSecondFactor,
    enable2FA: m.enable2FA,
    confirm2FA: m.confirm2FA,
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  userCertificatesService: {},
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 1, username: 'alice', role: 'operator' }, isAuthenticated: true, sessionChecked: true }),
  useNotification: () => ({
    showSuccess: m.showSuccess, showError: vi.fn(), showConfirm: vi.fn(), showPrompt: m.showPrompt,
  }),
  useMobile: () => ({ isMobile: false, isDesktop: true, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [], prefs: {}, updatePrefs: vi.fn() }),
}))

const auth = { user: { id: 1, username: 'alice', role: 'operator' }, isAuthenticated: true, sessionChecked: true }
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth, AuthProvider: ({ children }) => children }))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: m.showSuccess, showError: vi.fn(), showConfirm: vi.fn(), showPrompt: m.showPrompt }),
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: false, isDesktop: true, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  MobileProvider: ({ children }) => children,
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: [], colors: {} }),
  ThemeProvider: ({ children }) => children,
}))
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [], prefs: {}, updatePrefs: vi.fn() }),
  InspectorProvider: ({ children }) => children,
}))

vi.mock('../../services/apiClient', async (importOriginal) => ({
  ...(await importOriginal()), holdSignOut: vi.fn(),
}))

import AccountPage from '../AccountPage'
import { holdSignOut } from '../../services/apiClient'

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})

const CODES = ['AAAA-BBBB-CCCC-DDDD', '1111-2222-3333-4444']

describe('AccountPage: TOTP recovery codes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    m.getProfile.mockResolvedValue({ data: { username: 'alice', two_factor_enabled: false, two_factor_methods: [] } })
    m.getWebAuthnCredentials.mockResolvedValue({ data: [] })
    m.enable2FA.mockResolvedValue({ data: { secret: 'JBSWY3DPEHPK3PXP', qr_code: 'data:image/png;base64,AA==' } })
    m.confirm2FA.mockResolvedValue({ data: { backup_codes: CODES }, meta: { other_sessions_closed: 0 } })
  })

  it('shows the codes returned by the confirmation until they are acknowledged', async () => {
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('common.security'))[0])
    fireEvent.click(await screen.findByText('common.enable2FA'))
    fireEvent.change(await screen.findByPlaceholderText('account.codePlaceholder'), { target: { value: '123456' } })
    fireEvent.click(screen.getByText('account.verifyAndEnable'))

    await waitFor(() => expect(m.confirm2FA).toHaveBeenCalledWith('123456'))
    // The codes sit in a read-only field of the dialog, one per line, to be copied
    const box = await screen.findByLabelText('account.backupCodes')
    expect(box).toHaveAttribute('readonly')
    expect(box.value.split('\n')).toEqual(CODES)
    expect(screen.queryByText('account.verifyAndEnable')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('account.backupCodesSaved'))
    await waitFor(() => expect(screen.queryByLabelText('account.backupCodes')).not.toBeInTheDocument())
  })

  it('still shows the codes when 2FA is saved but the session could not be kept', async () => {
    const saved = Object.assign(new Error('2FA is enabled with these recovery codes, but...'),
      { status: 500, data: { data: { backup_codes: CODES } } })
    m.confirm2FA.mockRejectedValue(saved)
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('common.security'))[0])
    fireEvent.click(await screen.findByText('common.enable2FA'))
    fireEvent.change(await screen.findByPlaceholderText('account.codePlaceholder'), { target: { value: '123456' } })
    fireEvent.click(screen.getByText('account.verifyAndEnable'))
    const box = await screen.findByLabelText('account.backupCodes')
    expect(box.value.split('\n')).toEqual(CODES)
  })
})

describe('AccountPage: recovery codes of a change whose session was not kept', () => {
  const saved = () => Object.assign(new Error('2FA is enabled with these recovery codes, but...'),
    { status: 500, data: { data: { backup_codes: CODES } } })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('location', { pathname: '/account', search: '?section=security', hash: '', href: '/account?section=security' })
    m.getProfile.mockResolvedValue({ data: { username: 'alice', two_factor_enabled: false, two_factor_methods: [] } })
    m.getWebAuthnCredentials.mockResolvedValue({ data: [] })
    m.enable2FA.mockResolvedValue({ data: { secret: 'JBSWY3DPEHPK3PXP', qr_code: 'data:image/png;base64,AA==' } })
    m.confirm2FA.mockRejectedValue(saved())
  })
  afterEach(() => vi.unstubAllGlobals())

  const confirm = async () => {
    const view = render(<MemoryRouter><AccountPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('common.security'))[0])
    fireEvent.click(await screen.findByText('common.enable2FA'))
    fireEvent.change(await screen.findByPlaceholderText('account.codePlaceholder'), { target: { value: '123456' } })
    fireEvent.click(screen.getByText('account.verifyAndEnable'))
    await screen.findByLabelText('account.backupCodes')
    return view
  }

  it('holds the sign-out of the dead session while the codes are on screen', async () => {
    await confirm()
    // The next 401 (a poll of the shell) neither redirects nor clears the codes
    expect(holdSignOut).toHaveBeenLastCalledWith()
    expect(window.location.href).toBe('/account?section=security')
  })

  it('signs in again once the codes are acknowledged, and only then', async () => {
    await confirm()
    fireEvent.click(screen.getByText('account.backupCodesSaved'))
    expect(holdSignOut).toHaveBeenLastCalledWith(false)
    expect(window.location.href).toBe('/login?next=%2Faccount%3Fsection%3Dsecurity')
  })

  it('releases the hold when the page is left', async () => {
    const view = await confirm()
    view.unmount()
    expect(holdSignOut).toHaveBeenLastCalledWith(false)
  })

  it('holds nothing when the session was kept', async () => {
    m.confirm2FA.mockResolvedValue({ data: { backup_codes: CODES }, meta: { other_sessions_closed: 0 } })
    await confirm()
    fireEvent.click(screen.getByText('account.backupCodesSaved'))
    expect(holdSignOut).not.toHaveBeenCalled()
    expect(window.location.href).toBe('/account?section=security')
  })
})
