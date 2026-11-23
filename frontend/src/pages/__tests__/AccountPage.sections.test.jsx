/**
 * Account page on the mockup's sectioned form: profile, security and API keys each in a frame
 * on one page, a table of contents, a link to ?tab= landing on its frame, the profile's fields
 * edited in place and saved by the save bar, the key creation in its frame heading, a profile
 * edit kept for the return to the page, and the inspector's "close on navigate" preference.
 */
import { describe, it, expect, vi, beforeEach, beforeAll, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom'

const m = vi.hoisted(() => ({ createApiKey: vi.fn(), updateProfile: vi.fn(), persistPreference: vi.fn() }))
vi.mock('../../stores/userPreferencesStore', async (orig) => ({ ...(await orig()), persistPreference: m.persistPreference }))

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
    updateProfile: m.updateProfile,
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
  windows: { openEntity: () => {}, closeWindow: () => {}, windows: [], prefs: {}, updatePrefs: () => {}, closeOnNav: true, toggleCloseOnNav: vi.fn() },
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
import { accountService } from '../../services'
import { dropAllDrafts } from '../../lib/draftMemory'

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})

const open = (entry = '/account') => render(<MemoryRouter initialEntries={[entry]}><AccountPage /></MemoryRouter>)

describe('AccountPage sections', () => {
  beforeEach(() => { vi.clearAllMocks(); m.updateProfile.mockResolvedValue({}) })
  afterEach(() => { delete Element.prototype.scrollIntoView; dropAllDrafts() })

  it('shows the three sections on one page with a table of contents and the save bar at rest', async () => {
    open()
    const toc = await screen.findByRole('navigation', { name: 'account.tocLabel' })
    expect(within(toc).getAllByRole('link').map((a) => a.getAttribute('href')))
      .toEqual(['/account', '/account?tab=security', '/account?tab=api-keys'])
    for (const name of ['account.profile', 'common.security', 'account.apiKeys']) {
      expect(screen.getByRole('region', { name })).toHaveClass('panel', 'settings-section')
    }
    const bar = document.getElementById('settings-savebar')
    expect(bar).not.toHaveClass('dirty')
    expect(within(bar).getByRole('button', { name: 'common.save' })).toBeDisabled()
    expect(bar).toHaveTextContent('sectioned.nothingPending')
  })

  it('carries the language of the account in its profile, saved with the preferences', async () => {
    open()
    const select = await screen.findByRole('combobox', { name: 'settings.interfaceLanguage' })
    fireEvent.change(select, { target: { value: 'fr' } })
    expect(m.persistPreference).toHaveBeenCalledWith('language', 'fr')
  })

  it('lands a link to ?tab= on its frame', async () => {
    const scrolled = []
    Element.prototype.scrollIntoView = vi.fn(function scroll() { scrolled.push(this.id) })
    open('/account?tab=api-keys')
    await waitFor(() => expect(scrolled).toContain('set-sec-api-keys'))
    expect(document.activeElement).toBe(document.getElementById('set-title-api-keys'))
  })

  it('edits the profile in place and keeps the key creation in its frame heading', async () => {
    open()
    const profile = await screen.findByRole('region', { name: 'account.profile' })
    expect(within(profile).queryByRole('button', { name: 'common.edit' })).toBeNull()
    expect(within(profile).getByLabelText('account.fullName')).not.toHaveAttribute('readonly')
    expect(within(profile).getByLabelText('common.username')).toHaveAttribute('readonly')
    const keys = screen.getByRole('region', { name: 'account.apiKeys' }).querySelector('.panel-heading')
    expect(within(keys).getByRole('button', { name: 'account.createKey' })).toBeInTheDocument()
  })

  it('keeps a profile edit when the page is left, and finds it again on the return', async () => {
    render(
      <MemoryRouter initialEntries={['/account']}>
        <Routes>
          <Route path="/account" element={<><Link to="/certificates">elsewhere</Link><AccountPage /></>} />
          <Route path="/certificates" element={<Link to="/account">back</Link>} />
        </Routes>
      </MemoryRouter>,
    )
    await screen.findByRole('region', { name: 'account.profile' })
    fireEvent.change(screen.getByLabelText('account.fullName'), { target: { value: 'Alice B.' } })
    fireEvent.click(screen.getByText('elsewhere'))
    expect(notify.showConfirm).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByText('back'))
    expect(await screen.findByLabelText('account.fullName')).toHaveValue('Alice B.')
    // Undoing forgets it: the next visit shows the profile as stored
    fireEvent.click(screen.getByRole('button', { name: 'sectioned.undo' }))
    fireEvent.click(screen.getByText('elsewhere'))
    fireEvent.click(await screen.findByText('back'))
    expect(await screen.findByLabelText('account.fullName')).toHaveValue('')
  })

  it('says a profile edit waits in the save bar and the table of contents, and says nothing once undone', async () => {
    open()
    await screen.findByRole('region', { name: 'account.profile' })
    const bar = document.getElementById('settings-savebar')
    fireEvent.change(screen.getByLabelText('account.fullName'), { target: { value: 'Alice B.' } })
    expect(bar).toHaveClass('dirty')
    expect(bar).toHaveTextContent('sectioned.pendingTitle')
    expect(bar).toHaveTextContent('sectioned.pendingFields')
    const toc = screen.getByRole('navigation', { name: 'account.tocLabel' })
    expect(within(toc).getByText('sectioned.flagModified')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: 'sectioned.undo' }))
    expect(bar).not.toHaveClass('dirty')
    expect(within(toc).queryByText('sectioned.flagModified')).toBeNull()
    expect(screen.getByLabelText('account.fullName')).toHaveValue('')
  })

  it('saves the changed profile from the save bar, and with Enter in one of its fields', async () => {
    open()
    await screen.findByRole('region', { name: 'account.profile' })
    fireEvent.change(screen.getByLabelText('common.email'), { target: { value: 'a@example.com' } })
    fireEvent.click(within(document.getElementById('settings-savebar')).getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(m.updateProfile).toHaveBeenCalledWith({ full_name: '', email: 'a@example.com' }))
    fireEvent.change(screen.getByLabelText('account.fullName'), { target: { value: 'Alice' } })
    fireEvent.keyDown(screen.getByLabelText('account.fullName'), { key: 'Enter' })
    await waitFor(() => expect(m.updateProfile).toHaveBeenCalledTimes(2))
  })

  it('offers the inspector preference "close on navigate" as a check box with its hint', async () => {
    open()
    const box = await screen.findByRole('checkbox', { name: 'account.closeInspectorOnNav' })
    expect(box).toBeChecked()
    expect(box).toHaveAccessibleDescription('account.closeInspectorOnNavHint')
    fireEvent.click(box)
    expect(env.windows.toggleCloseOnNav).toHaveBeenCalledTimes(1)
  })

  it('reads the activity of the account as lines of terms and values, as the mockup props', async () => {
    open()
    const profile = await screen.findByRole('region', { name: 'account.profile' })
    const kv = profile.querySelector('dl.kv')
    expect(kv).not.toBeNull()
    expect(profile.querySelector('dl.props')).toBeNull()
    expect(within(kv).getByText('account.totalLogins').tagName).toBe('DT')
    expect(within(profile).getByLabelText('common.username')).toHaveValue('alice')
  })

  it('mutes the activity the server does not report and writes the status as a state', async () => {
    open()
    const profile = await screen.findByRole('region', { name: 'account.profile' })
    const kv = profile.querySelector('dl.kv')
    const dd = (term) => within(kv).getByText(term, { selector: 'dt' }).closest('div.row').querySelector('dd')
    expect(dd('account.accountCreated')).toHaveClass('absent')
    expect(dd('account.accountCreated')).toHaveTextContent('—')
    expect(dd('common.lastLogin')).toHaveClass('absent')
    expect(dd('account.totalLogins')).toHaveClass('v')
    expect(dd('account.totalLogins')).toHaveTextContent(/^0$/)
    expect(dd('common.status').querySelector('.badge')).not.toBeNull()
  })

  it('lists the API keys in the settings table with the revoke action named', async () => {
    accountService.getApiKeys.mockResolvedValueOnce({ data: [
      { id: 4, name: 'ci', key_prefix: 'ucm_ab', is_active: true, is_expired: false, created_at: '2026-11-01T10:00:00Z', permissions: ['read:certificates'] },
    ] })
    open()
    const keys = await screen.findByRole('region', { name: 'account.apiKeys' })
    const row = (await within(keys).findByText('ci')).closest('tr')
    expect(row.closest('table')).toHaveClass('module-table')
    // its permissions in words, never the raw scope
    expect(row).toHaveTextContent('rbac.permissionOf')
    expect(row).not.toHaveTextContent('read:certificates')
    expect(row).toHaveTextContent('ucm_ab…')
    expect(within(row).getByTitle('common.revoke')).toHaveAttribute('data-write')
  })
})
