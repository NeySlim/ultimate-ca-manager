/**
 * Users and roles as the mockup's users module draws it: the account list (Identifiant, Courriel,
 * Source, Rôle, État, Dernier accès) and its state chips with SSO, the dock (Profil, Permissions,
 * Clés API, then the product's Sécurité and mTLS), the disable confirmation, the export of the
 * list, the groups view, and the actions each permission allows.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const m = vi.hoisted(() => ({
  update: vi.fn(), getAll: vi.fn(), getApiKeys: vi.fn(), effective: vi.fn(), catalog: vi.fn(), download: vi.fn(),
  groupById: vi.fn(), write: true, del: true,
}))
const stable = vi.hoisted(() => ({
  i18n: { t: (k, o) => (o ? `${k} ${JSON.stringify(o)}` : k), i18n: { language: 'fr', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false }),
  useAuth: () => ({ user: { id: 1 } }),
}))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: persisted.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    useWebSocket: () => ({ muteToasts: () => {} }),
    usePermission: () => ({ canWrite: () => m.write, canDelete: () => m.del, hasPermission: () => true, canRead: () => true }),
  }
})
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../../lib/utils', async (orig) => ({ ...(await orig()), downloadBlob: (...a) => m.download(...a) }))
vi.mock('../../services', () => ({
  usersService: {
    getAll: (...a) => m.getAll(...a), update: (...a) => m.update(...a), getApiKeys: (...a) => m.getApiKeys(...a),
    getSecurityKeys: () => Promise.resolve({ data: [] }), getMtlsCertificates: () => Promise.resolve({ data: [] }),
  },
  groupsService: {
    getAll: () => Promise.resolve({ data: [{ id: 3, name: 'pki-ops', description: 'Exploitation', member_count: 1 }] }),
    getById: (...a) => m.groupById(...a),
  },
  rolesService: {
    getAll: () => Promise.resolve({ data: [] }), listRoles: () => Promise.resolve({ data: [] }),
    getEffectivePermissions: (...a) => m.effective(...a), listPermissions: (...a) => m.catalog(...a),
  },
  casService: { getAll: () => Promise.resolve({ data: [] }) },
  accountService: {},
  ssoService: { getProviders: () => Promise.resolve({ data: [] }) },
}))

import UsersGroupsPage from '../UsersGroupsPage'

const ME = { id: 1, username: 'admin', full_name: 'Administrateur', email: 'admin@example.com', role: 'admin', active: true,
  last_login: '2026-11-08T11:58:00Z', two_factor_enabled: true, sso_identities: [] }
const CHLOE = { id: 2, username: 'c.durand', full_name: 'Chloé Durand', email: '=cmd|calc', role: 'operator', active: true,
  last_login: null, two_factor_enabled: false,
  sso_identities: [{ id: 9, provider_id: 4, provider_name: 'sso.example.com', provider_type: 'oauth2', external_id: 'sub', state: 'bound' }] }
const OLD = { id: 3, username: 'ancien', email: 'old@example.com', role: 'viewer', active: false, sso_identities: [] }

const page = (route = '/users') => render(<MemoryRouter initialEntries={[route]}><UsersGroupsPage /></MemoryRouter>)
const dockOf = (container) => container.querySelector('aside#inspector')

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  m.write = true
  m.del = true
  m.getAll.mockResolvedValue({ data: [ME, CHLOE, OLD] })
  m.update.mockResolvedValue({})
  m.getApiKeys.mockResolvedValue({ data: [{ id: 5, name: 'Supervision', key_prefix: 'ucm_3f9a', permissions: ['read:*'], created_at: '2026-03-02T10:00:00Z',
    last_used_at: null, expires_at: null, is_active: true, is_expired: false }] })
  m.effective.mockResolvedValue({ data: ['read:*', 'write:certificates'] })
  m.catalog.mockResolvedValue({ data: ['read:certificates', 'write:certificates', 'delete:certificates'] })
  m.groupById.mockResolvedValue({ data: { id: 3, name: 'pki-ops', description: 'Exploitation', members: [{ id: 2, username: 'c.durand', email: 'c@example.com' }], permissions: ['read:audit'] } })
})

describe('the account list', () => {
  it('draws the mockup columns and the state chips, SSO included', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    expect(container.querySelector('h1#main-title')).toHaveTextContent('users.title')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('users.unit {"count":3}')
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'users.login', 'users.email', 'users.source', 'common.role', 'atelier.state', 'users.lastSeen', 'common.actions'])
    const chips = within(screen.getByRole('group', { name: 'users.filterByState' })).getAllByRole('button').map((b) => b.textContent)
    expect(chips).toEqual(['common.all3', 'users.views.active2', 'users.views.disabled1', 'users.views.sso1'])
    fireEvent.click(screen.getByRole('button', { name: /users\.views\.sso/ }))
    expect(screen.getByRole('button', { name: 'Chloé Durand' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Administrateur' })).toBeNull()
    expect(container.querySelector('footer.table-footer')).toHaveTextContent('users.range {"shown":1,"count":3}')
  })

  it('searches and filters by role, then resets from the no-match block', async () => {
    page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    fireEvent.change(screen.getByRole('combobox', { name: 'users.filterByRole' }), { target: { value: 'viewer' } })
    expect(screen.getByRole('button', { name: 'ancien' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Chloé Durand' })).toBeNull()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })
    fireEvent.click(await screen.findByRole('button', { name: 'table.clearFilters' }))
    expect(screen.getByRole('button', { name: 'Chloé Durand' })).toBeTruthy()
  })

  it('exports the whole list, a formula-like cell neutralised', async () => {
    page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    fireEvent.click(screen.getByRole('button', { name: 'users.exportList' }))
    expect(m.download).toHaveBeenCalledTimes(1)
    const [blob, name] = m.download.mock.calls[0]
    expect(name).toBe('users.csv')
    const text = await new Promise((resolve) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.readAsText(blob) })
    expect(text.split('\r\n')[0]).toBe('atelier.name,users.login,users.email,users.source,common.role,atelier.state,users.lastSeen')
    expect(text).toContain("Chloé Durand,c.durand,'=cmd|calc,")
    expect(text.trim().split('\r\n')).toHaveLength(4)
  })
})

describe('the account dock', () => {
  it('shows the profile of an SSO account and its actions', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Chloé Durand' }))
    const dock = dockOf(container)
    expect(within(dock).getAllByRole('tab').map((x) => x.textContent))
      .toEqual(['users.tabs.profile', 'users.tabs.permissions', 'users.apiKeys.title', 'common.security', 'users.mtls.title'])
    expect(within(dock).getByText('users.sourceSso {"providers":"users.authSource.oauth2 sso.example.com"}')).toBeTruthy()
    for (const name of ['common.edit', 'users.resetPassword…', 'users.disableEllipsis', 'common.delete']) {
      expect(within(dock).getByRole('button', { name })).toBeTruthy()
    }
    expect(within(dock).queryByText('users.selfNotice')).toBeNull()
    expect(within(dock).getByText('users.roleDesc.operator')).toBeTruthy()
  })

  it('keeps your own account from being disabled or deleted, and says so', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Administrateur' }))
    const dock = dockOf(container)
    expect(within(dock).getByText('users.selfNotice')).toBeTruthy()
    expect(within(dock).queryByRole('button', { name: 'users.disableEllipsis' })).toBeNull()
    expect(within(dock).queryByRole('button', { name: 'common.delete' })).toBeNull()
  })

  it('disables an account only after the confirmation, and not when cancelled', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Chloé Durand' }))
    fireEvent.click(within(dockOf(container)).getByRole('button', { name: 'users.disableEllipsis' }))
    const dialog = screen.getByRole('dialog', { name: 'users.disableTitle' })
    expect(dialog).toHaveTextContent('users.disableText {"login":"c.durand"}')
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.cancel' }))
    expect(m.update).not.toHaveBeenCalled()
    fireEvent.click(within(dockOf(container)).getByRole('button', { name: 'users.disableEllipsis' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'users.disableTitle' })).getByRole('button', { name: 'users.disableConfirm' }))
    await waitFor(() => expect(m.update).toHaveBeenCalledWith(2, { active: false }))
  })

  it('enables a disabled account at once', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'ancien' }))
    fireEvent.click(within(dockOf(container)).getByRole('button', { name: 'users.activate' }))
    await waitFor(() => expect(m.update).toHaveBeenCalledWith(3, { active: true }))
  })

  it('lists the effective permissions, a wildcard granting its whole action', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Chloé Durand' }))
    fireEvent.click(within(dockOf(container)).getByRole('tab', { name: 'users.tabs.permissions' }))
    await waitFor(() => expect(m.effective).toHaveBeenCalledWith(2))
    const items = await within(dockOf(container)).findAllByRole('listitem')
    const state = Object.fromEntries(items.map((li) => [li.querySelector('.mono').textContent, li.querySelector('.flag').textContent]))
    expect(state).toEqual({ 'delete:certificates': 'users.notAllowed', 'read:*': 'users.allowed', 'read:certificates': 'users.allowed', 'write:certificates': 'users.allowed' })
  })

  it('shows each API key with its scope and its creation date', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Chloé Durand' }))
    fireEvent.click(within(dockOf(container)).getByRole('tab', { name: 'users.apiKeys.title' }))
    const row = (await within(dockOf(container)).findByText('Supervision')).closest('li')
    expect(row).toHaveTextContent('ucm_3f9a…')
    expect(row).toHaveTextContent('"scope":"account.scopeReadOnly","created":"2 mars 2026"')
  })

  it('gives no write action to a reader', async () => {
    m.write = false
    m.del = false
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Chloé Durand' }))
    const dock = dockOf(container)
    for (const name of ['common.edit', 'users.resetPassword…', 'users.disableEllipsis', 'common.delete', 'users.sso.attach']) {
      expect(within(dock).queryByRole('button', { name })).toBeNull()
    }
    expect(within(dock).queryByRole('tab', { name: 'users.mtls.title' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'users.createUser' })).toBeNull()
  })
})

describe('the groups view', () => {
  it('opens from the head, lists the groups and their members', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    fireEvent.click(screen.getByRole('button', { name: 'common.groups' }))
    fireEvent.click(await screen.findByRole('button', { name: 'pki-ops' }))
    await waitFor(() => expect(m.groupById).toHaveBeenCalledWith(3))
    fireEvent.click(within(dockOf(container)).getByRole('tab', { name: 'groups.members' }))
    expect(await within(dockOf(container)).findByText('c.durand')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'users.accounts' }))
    expect(await screen.findByRole('button', { name: 'Chloé Durand' })).toBeTruthy()
  })

  it('opens on the groups from the address', async () => {
    page('/users?tab=groups')
    expect(await screen.findByRole('button', { name: 'pki-ops' })).toBeTruthy()
  })
})
