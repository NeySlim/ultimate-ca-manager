/**
 * The issuing-CA picker of the mTLS enrolment lists the CAs able to sign, keeps
 * the chosen one visible and counts the others (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const accountMocks = vi.hoisted(() => ({
  getMTLSCertificates: vi.fn(),
  downloadMTLSCertificate: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 7, username: 'probe', role: 'viewer' } }),
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showConfirm: vi.fn(),
    showPrompt: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useWindowManager: () => ({
    openWindow: vi.fn(),
    closeWindow: vi.fn(),
    windows: [],
    prefs: { sameWindow: true, closeOnNav: true },
    updatePrefs: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  WindowManagerProvider: ({ children }) => children,
}))

// usePermission reads `permissions` from AuthContext directly.
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services/account.service', () => ({
  accountService: {
    getProfile: vi.fn().mockResolvedValue({
      data: { username: 'probe', email: 'probe@test.local' },
    }),
    getApiKeys: vi.fn().mockResolvedValue({ data: [] }),
    getWebAuthnCredentials: vi.fn().mockResolvedValue({ data: [] }),
    getMTLSCertificates: accountMocks.getMTLSCertificates,
    getAvailableMTLSCertificates: vi.fn().mockResolvedValue({ data: [] }),
    createMTLSCertificate: vi.fn().mockResolvedValue({ data: {} }),
    downloadMTLSCertificate: accountMocks.downloadMTLSCertificate,
  },
}))

vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({
      data: [
        { id: 1, refid: 'ca-sign', descr: 'Signing CA', has_private_key: true },
        { id: 2, refid: 'ca-keyless', descr: 'Keyless root', certificate_only: true, has_private_key: false },
        { id: 3, refid: 'ca-offline', descr: 'Offline CA', has_private_key: true, offline: true },
      ],
    }),
  },
}))

vi.mock('../../services/user-certificates.service', () => ({
  userCertificatesService: { export: vi.fn() },
}))

// A native select exposes the options and the helper text that the real one hides in a portal.
// The extra button sets a value the way a saved selection would, even one no longer listed.
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        <option value="">-</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <button onClick={() => onChange?.('ca-keyless')}>choose-keyless</button>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import AccountPage from '../AccountPage'

async function openPicker() {
  authState.permissions = ['*']
  render(<MemoryRouter><AccountPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText('common.security'))[0])
  fireEvent.click((await screen.findAllByText('account.addCertificate'))[0])
  return screen.findByTestId('field-account.mtlsIssuingCA')
}

const labels = (field) => within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)

describe('AccountPage mTLS issuing CA picker (#426)', () => {
  beforeEach(() => {
    accountMocks.getMTLSCertificates.mockResolvedValue({ data: [] })
  })

  it('offers only the CA that can sign and counts the others', async () => {
    const field = await openPicker()
    expect(labels(field)).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('keeps the chosen CA listed when it holds no key and counts one less', async () => {
    const field = await openPicker()
    fireEvent.click(within(field).getByText('choose-keyless'))
    expect(labels(field)).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })
})
