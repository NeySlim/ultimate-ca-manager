/**
 * Account page on the sectioned template: profile, security and API keys each in a frame
 * on one page, a table of contents, a link to ?tab= landing on its frame, the profile's
 * edit and the key creation in their frame heading, no save bar.
 */
import { describe, it, expect, vi, beforeEach, beforeAll, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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

const open = (entry = '/account') => render(<MemoryRouter initialEntries={[entry]}><AccountPage /></MemoryRouter>)

describe('AccountPage sections', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { delete Element.prototype.scrollIntoView })

  it('shows the three sections on one page with a table of contents and no save bar', async () => {
    open()
    const toc = await screen.findByRole('navigation', { name: 'account.tocLabel' })
    expect(within(toc).getAllByRole('link').map((a) => a.getAttribute('href')))
      .toEqual(['/account', '/account?tab=security', '/account?tab=api-keys'])
    for (const name of ['account.profile', 'common.security', 'account.apiKeys']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument()
    }
    expect(screen.queryByTestId('sf-savebar')).toBeNull()
  })

  it('lands a link to ?tab= on its frame', async () => {
    const scrolled = []
    Element.prototype.scrollIntoView = vi.fn(function scroll() { scrolled.push(this.id) })
    open('/account?tab=api-keys')
    await waitFor(() => expect(scrolled).toContain('sf-sec-api-keys'))
  })

  it('keeps the profile edit and the key creation in their frame heading', async () => {
    open()
    const profile = await screen.findByRole('region', { name: 'account.profile' })
    const heading = profile.querySelector('.sf-heading')
    fireEvent.click(within(heading).getByRole('button', { name: 'common.edit' }))
    expect(within(heading).getByRole('button', { name: 'common.save' })).toBeInTheDocument()
    expect(within(heading).getByRole('button', { name: 'common.cancel' })).toBeInTheDocument()
    const keys = screen.getByRole('region', { name: 'account.apiKeys' }).querySelector('.sf-heading')
    expect(within(keys).getByRole('button', { name: 'account.createKey' })).toBeInTheDocument()
  })
})
