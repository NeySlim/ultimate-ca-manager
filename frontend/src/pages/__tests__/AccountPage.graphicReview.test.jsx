/**
 * Account page after the graphic review: the API key tips read as one help, a key's SSO scope in
 * words, and the language of the interface among the preferences, under no title of its own.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({ createApiKey: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, o) => (o?.returnObjects ? [`${key}.1`, `${key}.2`] : o?.resource ? `${o.resource}: ${o.actions}` : key), i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../services', () => ({
  accountService: {
    getProfile: vi.fn().mockResolvedValue({ data: { username: 'alice' } }),
    getApiKeys: vi.fn().mockResolvedValue({ data: [
      { id: 3, name: 'old', is_active: false, created_at: '2025-01-01', permissions: ['read:*'] },
      { id: 4, name: 'ops', is_active: true, created_at: '2026-01-01', permissions: ['write:sso'] },
    ] }),
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

describe('AccountPage after the graphic review', () => {
  it('gives the API key tips as one help and names a key\'s SSO scope in words', async () => {
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('account.apiKeys'))[0])
    const group = (await screen.findByText('account.yourAPIKeys')).closest('fieldset')
    const hints = group.querySelectorAll('.group-hint')
    expect(hints).toHaveLength(1)
    expect(hints[0]).toHaveTextContent('account.apiKeyHint')
    const row = await within(group).findByText('ops')
    expect(row.closest('tr')).toHaveTextContent('common.sso')
  })

  it('lists the keys in use before the revoked ones', async () => {
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('account.apiKeys'))[0])
    const group = (await screen.findByText('account.yourAPIKeys')).closest('fieldset')
    await within(group).findByText('ops')
    expect([...group.querySelectorAll('table.module-table tbody tr')].map((tr) => tr.querySelector('th, td').textContent.trim())).toEqual(['ops', 'old'])
  })

  it('puts the language of the interface among the preferences, no group named after its one field', async () => {
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    const field = await screen.findByLabelText('settings.interfaceLanguage')
    expect(field.closest('fieldset').querySelector('legend')).toHaveTextContent('account.preferences')
    expect([...document.querySelectorAll('legend')].map((l) => l.textContent)).not.toContain('settings.language')
  })
})
