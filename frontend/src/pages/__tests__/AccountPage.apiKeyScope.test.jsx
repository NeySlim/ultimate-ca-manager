/**
 * Account page: the Certificates Only preset never asks for more than the account holds,
 * so an operator without the SSH scopes still gets a key instead of a 403.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({ createApiKey: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../services', () => ({
  accountService: {
    getProfile: vi.fn().mockResolvedValue({ data: { username: 'alice' } }),
    getApiKeys: vi.fn().mockResolvedValue({ data: [] }),
    getWebAuthnCredentials: vi.fn().mockResolvedValue({ data: [] }),
    getMTLSCertificates: vi.fn().mockResolvedValue({ data: [] }),
    createApiKey: m.createApiKey,
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  userCertificatesService: {},
}))

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const auth = vi.hoisted(() => ({
  user: { id: 1, username: 'alice', role: 'operator' }, isAuthenticated: true, sessionChecked: true,
  permissions: [],
}))
const env = vi.hoisted(() => ({
  mobile: { isMobile: false, isDesktop: true, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: () => {} },
  windows: { openEntity: () => {}, closeWindow: () => {}, windows: [], prefs: {}, updatePrefs: () => {} },
}))

vi.mock('../../contexts', () => ({
  useAuth: () => auth,
  useNotification: () => notify,
  useMobile: () => env.mobile,
  useInspector: () => env.windows,
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth, AuthProvider: ({ children }) => children }))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => notify, NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => env.mobile, MobileProvider: ({ children }) => children }))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: [], colors: {} }),
  ThemeProvider: ({ children }) => children,
}))
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => env.windows, InspectorProvider: ({ children }) => children,
}))
// A native select stands in for the portal one; the help card reads translated arrays
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  HelpCard: () => null,
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Input: ({ label, helperText: _helperText, ...props }) => <input aria-label={label} {...props} />,
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import AccountPage from '../AccountPage'

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})

async function createCertificatesKey() {
  render(<MemoryRouter><AccountPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText('account.apiKeys'))[0])
  fireEvent.click((await screen.findAllByText('account.createKey'))[0])
  fireEvent.change(await screen.findByLabelText('account.apiKeyName'), { target: { value: 'ci' } })
  fireEvent.change(screen.getByLabelText('account.permissionScope'), { target: { value: 'certificates' } })
  fireEvent.submit(screen.getByLabelText('account.apiKeyName').closest('form'))
  await waitFor(() => expect(m.createApiKey).toHaveBeenCalledTimes(1))
  return m.createApiKey.mock.calls[0][0].permissions
}

describe('AccountPage: Certificates Only API key', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    m.createApiKey.mockResolvedValue({ data: { id: 1, key: 'k' } })
  })

  it('asks for no SSH scope the account lacks', async () => {
    auth.permissions = ['read:certificates', 'write:certificates', 'read:cas', 'read:crl', 'read:ssh']
    expect(await createCertificatesKey()).toEqual(
      ['read:certificates', 'write:certificates', 'read:cas', 'read:crl', 'read:ssh'])
  })

  it('keeps the SSH scopes an account holds through a wildcard', async () => {
    auth.permissions = ['read:*', 'write:*']
    expect(await createCertificatesKey()).toEqual([
      'read:certificates', 'write:certificates', 'read:cas', 'read:crl', 'read:ssh', 'write:ssh', 'read:ssh_cas',
    ])
  })
})
