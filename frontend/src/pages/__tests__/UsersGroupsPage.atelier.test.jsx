/**
 * Users and roles as the mockup's users module draws it: the account list (Identifiant, Courriel,
 * Source, Rôle, État, Dernier accès) and its state chips with SSO, the dock (Profil, Permissions,
 * Clés API, then the product's Sécurité and mTLS), the disable confirmation, the export of the
 * list, the groups view, and the actions each permission allows.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const m = vi.hoisted(() => ({
  update: vi.fn(), getAll: vi.fn(), getApiKeys: vi.fn(), effective: vi.fn(), catalog: vi.fn(), download: vi.fn(),
  groupById: vi.fn(), create: vi.fn(), write: true, del: true,
}))
const stable = vi.hoisted(() => ({
  i18n: { t: (k, o) => (o ? `${k} ${JSON.stringify(o)}` : k), i18n: { language: 'fr', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() },
}))
const phone = vi.hoisted(() => ({ on: false }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: phone.on }) }))
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
    getById: (...a) => m.groupById(...a), create: (...a) => m.create(...a),
    getAvailablePermissions: () => Promise.resolve({ data: ['read:cas', 'read:certificates', 'write:certificates'] }),
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
  phone.on = false
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

  it('opens by name, keeps the sort in the address and reads it back (T4, T9); the e-mail gives way first', async () => {
    const at = { search: '' }
    function Where() { at.search = useLocation().search; return null }
    const r = render(<MemoryRouter initialEntries={['/users']}><UsersGroupsPage /><Where /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Chloé Durand' })
    const names = () => [...document.querySelectorAll('tbody .entity-label')].map((n) => n.textContent)
    const sorted = () => screen.getAllByRole('columnheader').filter((h) => /ending/.test(h.getAttribute('aria-sort') || '')).map((h) => [h.textContent, h.getAttribute('aria-sort')])
    expect(sorted()).toEqual([['atelier.name', 'ascending']])
    expect(names()).toEqual(['Administrateur', 'ancien', 'Chloé Durand'])
    // The e-mail is the absorbing text; the last access a date named on a phone
    expect(screen.getByRole('columnheader', { name: 'users.email' })).toHaveClass('col-description')
    fireEvent.click(screen.getByRole('button', { name: 'users.lastSeen' }))
    expect(at.search).toBe('?sort=seen&order=asc')
    r.unmount()
    render(<MemoryRouter initialEntries={['/users?sort=seen&order=desc']}><UsersGroupsPage /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Chloé Durand' })
    expect(sorted()).toEqual([['users.lastSeen', 'descending']])
    // Never seen sorts last whichever the direction
    expect(names()[0]).toBe('Administrateur')
  })

  it('keeps the e-mail before the login: the login folds first, the e-mail is a fact of a phone record (E2 bis)', async () => {
    phone.on = true
    page()
    const name = await screen.findByRole('button', { name: 'Administrateur' })
    const facts = [...name.closest('.mobile-record').querySelectorAll('.row-meta > span')].map((s) => s.textContent)
    expect(facts).toContain('admin@example.com')
    expect(facts).not.toContain('admin')
  })

  // Thirty-three rows sorted fourteen times: well over a second under a full parallel run
  it('sorts its seven columns from their headers, on the pages it keeps', async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ id: 100 + i, username: `u${String(i).padStart(2, '0')}`, email: `u${i}@example.com`, role: 'viewer', active: true, sso_identities: [] }))
    m.getAll.mockResolvedValue({ data: [ME, CHLOE, OLD, ...many] })
    const { container } = page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    const footer = container.querySelector('footer.table-footer')
    const bodyRows = () => container.querySelectorAll('tbody tr')
    expect(footer).toHaveTextContent('users.pageRange {"start":1,"end":25,"count":33}')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(footer).toHaveTextContent('users.pageRange {"start":26,"end":33,"count":33}')
    fireEvent.click(screen.getByRole('button', { name: 'users.lastSeen' }))
    expect(screen.getByRole('columnheader', { name: 'users.lastSeen' })).toHaveAttribute('aria-sort', 'ascending')
    expect(footer).toHaveTextContent('users.pageRange {"start":1,"end":25,"count":33}')
    expect(bodyRows()[0]).toHaveTextContent('admin')
    // The role sorts by its words, as the list shows it
    fireEvent.click(screen.getByRole('button', { name: 'common.role' }))
    expect(bodyRows()[0]).toHaveTextContent('common.operator')
    fireEvent.click(screen.getByRole('button', { name: 'common.role' }))
    expect(bodyRows()[0]).toHaveTextContent('users.admin')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    expect(bodyRows()[0]).toHaveTextContent('ancien')
    fireEvent.click(screen.getByRole('button', { name: 'users.email' }))
    expect(bodyRows()[0]).toHaveTextContent('=cmd|calc')
    fireEvent.click(screen.getByRole('button', { name: 'users.source' }))
    fireEvent.click(screen.getByRole('button', { name: 'users.source' }))
    expect(bodyRows()[0]).toHaveTextContent('Chloé Durand')
    fireEvent.click(screen.getByRole('button', { name: 'users.login' }))
    fireEvent.click(screen.getByRole('button', { name: 'users.login' }))
    expect(bodyRows()[0]).toHaveTextContent('u29')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    expect(bodyRows()[0]).toHaveTextContent('admin')
    // A search goes back to page one
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'example.com' } })
    expect(footer).toHaveTextContent('users.pageRange {"start":1,"end":25,"count":32}')
  }, 15000)

  it("words the head's main action in full, a short verb kept for a phone", async () => {
    page()
    const create = await screen.findByRole('button', { name: 'users.createUser' })
    expect(create).toHaveAttribute('id', 'users-new')
    expect(create.querySelector('.wide-label')).toHaveTextContent(/^users\.createUser$/)
    expect(create.querySelector('.phone-label')).toHaveTextContent(/^common\.create$/)
  })

  // A phone hides the head's secondary buttons (the mockup's rule): its « ⋯ » menu gives them back
  it("gives the head's secondary actions a « ⋯ » menu, as the journal's", async () => {
    page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    const more = document.querySelector('.page-head .page-more')
    expect(more).not.toBeNull()
    fireEvent.click(within(more).getByRole('button', { name: 'common.moreActions' }))
    const items = within(more).getAllByRole('menuitem').map((b) => b.textContent)
    expect(items).toEqual(['common.groups', 'users.exportList'])
    fireEvent.click(within(more).getByRole('menuitem', { name: 'common.groups' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'common.groups' })).toBeInTheDocument()
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
    // The group dialog's grid, read only: named resources, read, write and delete, never a raw scope
    const table = await within(dockOf(container)).findByRole('table', { name: 'users.tabs.permissions' })
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['groups.resource', 'groups.actions.read', 'groups.actions.write', 'groups.actions.delete'])
    const certs = within(table).getByRole('rowheader', { name: 'rbac.categories.certificates' }).closest('tr')
    expect([...certs.querySelectorAll('td')].map((td) => td.textContent)).toEqual(['users.allowed', 'users.allowed', 'users.notAllowed'])
    expect(within(table).getAllByRole('rowheader')).toHaveLength(1)
    expect(dockOf(container).textContent).not.toMatch(/(read|write|delete):/)
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

  it('reads a group\'s permissions in the dialog\'s grid, named and marked allowed or not', async () => {
    const { container } = page('/users?tab=groups')
    fireEvent.click(await screen.findByRole('button', { name: 'pki-ops' }))
    await waitFor(() => expect(m.groupById).toHaveBeenCalledWith(3))
    fireEvent.click(within(dockOf(container)).getByRole('tab', { name: 'groups.permissions' }))
    const table = await within(dockOf(container)).findByRole('table', { name: 'groups.permissions' })
    // what the server lets a group grant, and what this group holds beyond it
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent))
      .toEqual(['rbac.categories.certificates', 'rbac.categories.certificateAuthorities', 'rbac.categories.auditLogs'])
    const row = (name) => [...within(table).getByRole('rowheader', { name }).closest('tr').querySelectorAll('td')].map((td) => td.textContent)
    expect(row('rbac.categories.auditLogs')).toEqual(['users.allowed', '', ''])
    expect(row('rbac.categories.certificates')).toEqual(['users.notAllowed', 'users.notAllowed', ''])
    expect(table.querySelector('input')).toBeNull()
    expect(dockOf(container).textContent).not.toMatch(/(read|write|delete):/)
  })

  it('reads a group\'s overview as typed rows: its description long, a missing date muted', async () => {
    const { container } = page('/users?tab=groups')
    fireEvent.click(await screen.findByRole('button', { name: 'pki-ops' }))
    await waitFor(() => expect(m.groupById).toHaveBeenCalledWith(3))
    const kv = await waitFor(() => { const dl = dockOf(container).querySelector('dl.kv'); expect(dl).not.toBeNull(); return dl })
    expect(dockOf(container).querySelector('dl.props')).toBeNull()
    const row = (term) => within(kv).getByText(term, { selector: 'dt' }).closest('div.row')
    expect(row('common.description')).toHaveClass('long')
    expect(row('common.description').querySelector('dd.v')).toHaveTextContent('Exploitation')
    expect(row('groups.members').querySelector('dd.v')).toHaveTextContent('groups.memberCount {"count":1}')
    expect(row('common.created').querySelector('dd')).toHaveClass('absent')
  })

  it('opens on the groups from the address', async () => {
    page('/users?tab=groups')
    expect(await screen.findByRole('button', { name: 'pki-ops' })).toBeTruthy()
    // Its three columns sort too, by name first (T4)
    expect(screen.getByRole('columnheader', { name: 'atelier.name' })).toHaveAttribute('aria-sort', 'ascending')
    for (const name of ['common.description', 'groups.members']) {
      fireEvent.click(screen.getByRole('button', { name }))
      expect(screen.getByRole('columnheader', { name })).toHaveAttribute('aria-sort', 'ascending')
    }
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    expect(screen.getByRole('columnheader', { name: 'atelier.name' })).toHaveAttribute('aria-sort', 'ascending')
  })
})

describe('the account and group dialogs', () => {
  it('opens the account form in the mockup dialog, its fields in the grid and its actions under the rule', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    fireEvent.click(screen.getByRole('button', { name: 'users.createUser' }))
    const dialog = await waitFor(() => { const d = document.querySelector('dialog'); expect(d).toBeTruthy(); return d })
    expect(container.querySelector('.atl')).toContainElement(dialog)
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title')
    const fields = dialog.querySelector('form .form-fields')
    expect(within(fields).getByLabelText('common.username')).toBeRequired()
    expect(within(fields).getByLabelText('common.role').tagName).toBe('SELECT')
    expect([...dialog.querySelectorAll('.modal-actions > button')].map((b) => [b.className, b.textContent]))
      .toEqual([['btn', 'common.cancel'], ['btn primary', 'common.create']])
  })

  it('grants the group permissions in a table of named resources and the read, write and delete columns', async () => {
    m.create.mockResolvedValue({})
    page()
    await screen.findByRole('button', { name: 'Chloé Durand' })
    fireEvent.click(screen.getByRole('button', { name: 'common.groups' }))
    await screen.findByRole('button', { name: 'pki-ops' })
    fireEvent.click(screen.getByRole('button', { name: 'groups.createGroup' }))
    const dialog = await waitFor(() => { const d = document.querySelector('dialog'); expect(d).toBeTruthy(); return d })
    const table = await within(dialog).findByRole('table', { name: 'groups.permissions' })
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['groups.resource', 'groups.actions.read', 'groups.actions.write', 'groups.actions.delete'])
    // One row per resource, named as the RBAC page names it, a box only where the action is grantable
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent)).toEqual(['rbac.categories.certificates', 'rbac.categories.certificateAuthorities'])
    const certs = within(table).getByRole('rowheader', { name: 'rbac.categories.certificates' }).closest('tr')
    expect(within(certs).getAllByRole('checkbox').map((c) => c.getAttribute('aria-label'))).toEqual([
      'groups.grant {"action":"groups.actions.read","resource":"rbac.categories.certificates"}',
      'groups.grant {"action":"groups.actions.write","resource":"rbac.categories.certificates"}',
    ])
    expect(certs.querySelectorAll('td')).toHaveLength(3)
    expect(dialog.textContent).not.toContain('read:certificates')
    fireEvent.change(within(dialog).getByLabelText('groups.groupName'), { target: { value: 'ops' } })
    fireEvent.click(within(certs).getAllByRole('checkbox')[1])
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.create' }))
    await waitFor(() => expect(m.create).toHaveBeenCalledWith({ name: 'ops', description: '', permissions: ['write:certificates'] }))
  })
})

describe('the open account or group in the URL', () => {
  let where
  function Where() { const l = useLocation(); where = l.pathname + l.search; return null }
  const at = (url) => render(<MemoryRouter initialEntries={[url]}><UsersGroupsPage /><Where /></MemoryRouter>)

  it('opens the account of a palette result (?selected=) and writes it as item', async () => {
    const { container } = at('/users?selected=2')
    await waitFor(() => expect(dockOf(container)).toBeTruthy())
    expect(within(dockOf(container)).getByRole('heading', { level: 2 })).toHaveTextContent('Chloé Durand')
    fireEvent.click(within(dockOf(container)).getByRole('tab', { name: 'common.security' }))
    expect(where).toBe('/users?item=2&section=security')
  })

  it('reopens a group and its section on reload, and the tab change closes it', async () => {
    const { container } = at('/users?tab=groups&item=3&section=members')
    await waitFor(() => expect(dockOf(container)).toBeTruthy())
    expect(within(dockOf(container)).getByRole('tab', { name: 'groups.members' })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(m.groupById).toHaveBeenCalledWith(3))
    fireEvent.click(screen.getByRole('button', { name: 'users.accounts' }))
    await waitFor(() => expect(where).toBe('/users?tab=users'))
    expect(dockOf(container)).toBeNull()
  })
})
