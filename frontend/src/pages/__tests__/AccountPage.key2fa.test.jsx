/**
 * Account page: the security key turned on or off as second factor, and the
 * active second factors shown as the server reports them.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({
  getProfile: vi.fn(),
  getWebAuthnCredentials: vi.fn(),
  setWebAuthnSecondFactor: vi.fn(),
  showPrompt: vi.fn(),
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
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  userCertificatesService: {},
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 1, username: 'alice', role: 'operator' }, isAuthenticated: true, sessionChecked: true }),
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn(), showPrompt: m.showPrompt,
  }),
  useMobile: () => ({ isMobile: false, isDesktop: true, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({ openWindow: vi.fn(), closeWindow: vi.fn(), windows: [], prefs: {}, updatePrefs: vi.fn() }),
}))

const auth = { user: { id: 1, username: 'alice', role: 'operator' }, isAuthenticated: true, sessionChecked: true }
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth, AuthProvider: ({ children }) => children }))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn(), showPrompt: m.showPrompt }),
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
vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({ openWindow: vi.fn(), closeWindow: vi.fn(), windows: [], prefs: {}, updatePrefs: vi.fn() }),
  WindowManagerProvider: ({ children }) => children,
}))

import AccountPage from '../AccountPage'

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})

async function openSecurity(profile, keys) {
  m.getProfile.mockResolvedValue({ data: { username: 'alice', ...profile } })
  m.getWebAuthnCredentials.mockResolvedValue({ data: keys })
  render(<MemoryRouter><AccountPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText('common.security'))[0])
  return screen.findByText('account.keyAsSecondFactor')
}

const KEY = { id: 1, name: 'YubiKey', enabled: true, created_at: '2026-10-01T00:00:00Z' }

describe('AccountPage: security key as second factor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    m.setWebAuthnSecondFactor.mockResolvedValue({ data: {} })
  })

  it('turns it on when a key is registered', async () => {
    await openSecurity({ webauthn_2fa: false, two_factor_methods: [] }, [KEY])
    fireEvent.click(screen.getByText('account.turnOnKey2fa'))
    await waitFor(() => expect(m.setWebAuthnSecondFactor).toHaveBeenCalledWith(true))
  })

  it('cannot be turned on without a key', async () => {
    await openSecurity({ webauthn_2fa: false, two_factor_methods: [] }, [])
    expect(screen.getByText('account.turnOnKey2fa').closest('button')).toBeDisabled()
    expect(screen.getByText('account.keyAsSecondFactorNoKey')).toBeInTheDocument()
  })

  it('a disabled key does not count', async () => {
    await openSecurity({ webauthn_2fa: false, two_factor_methods: [] }, [{ ...KEY, enabled: false }])
    expect(screen.getByText('account.turnOnKey2fa').closest('button')).toBeDisabled()
  })

  it('asks for the password to turn it off', async () => {
    m.showPrompt.mockResolvedValue('secret-pw')
    await openSecurity({ webauthn_2fa: true, two_factor_methods: ['webauthn'] }, [KEY])
    fireEvent.click(screen.getByText('account.turnOffKey2fa'))
    await waitFor(() => expect(m.setWebAuthnSecondFactor).toHaveBeenCalledWith(false, 'secret-pw'))
  })

  it('lists the active second factors', async () => {
    await openSecurity({ two_factor_enabled: true, webauthn_2fa: true,
                         two_factor_methods: ['totp', 'webauthn'], two_factor_enforced: true }, [KEY])
    expect(screen.getByText(/account\.activeSecondFactors: account\.authenticatorApp, account\.securityKey/)).toBeInTheDocument()
    expect(screen.getByText(/account\.twoFactorEnforced/)).toBeInTheDocument()
  })
})
