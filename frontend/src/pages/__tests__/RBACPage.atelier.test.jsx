/**
 * Roles as a module list of the mockup: the System and Custom chips, the columns, the dock of a
 * role; a system role reads its permissions only, a custom one edits them by resource or one by one.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const stable = vi.hoisted(() => ({
  i18n: { t: (k, o) => (o ? `${k} ${JSON.stringify(o)}` : k), i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() },
  update: vi.fn(), remove: vi.fn(), list: vi.fn(),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({ useNotification: () => stable.notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    useModals: modals.useModals, usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
  }
})
vi.mock('../../services', () => ({
  rolesService: {
    listRoles: (...a) => stable.list(...a),
    listPermissions: () => Promise.resolve({ data: ['read:certificates', 'write:certificates', 'read:cas'] }),
    updateRole: (...a) => stable.update(...a),
    deleteRole: (...a) => stable.remove(...a),
  },
}))

import { renderAtUrl } from '../../test/dockUrl'
import RBACPage from '../RBACPage'

const ROLES = [
  { id: 1, name: 'Viewer', description: 'Read only', is_system: true, user_count: 7, permissions: ['read:certificates', 'read:cas'], all_permissions: ['read:certificates', 'read:cas'] },
  { id: 2, name: 'Cert Team', description: '', is_system: false, user_count: 4, permissions: ['read:certificates'], all_permissions: ['read:certificates'] },
]
const page = () => render(<MemoryRouter><RBACPage /></MemoryRouter>)
const names = () => [...document.querySelectorAll('tbody .entity-label')].map((b) => b.textContent)
const sortedHeads = () => screen.getAllByRole('columnheader').filter((h) => /ending/.test(h.getAttribute('aria-sort') || '')).map((h) => [h.textContent, h.getAttribute('aria-sort')])
const sortableHeads = () => screen.getAllByRole('columnheader').filter((h) => h.querySelector('button[data-sort]')).map((h) => h.textContent)
const dock = () => document.querySelector('aside#inspector')

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  stable.list.mockResolvedValue({ data: ROLES })
  stable.update.mockResolvedValue({})
  stable.remove.mockResolvedValue({})
})

describe('the role list', () => {
  it('draws the columns and filters by type', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: 'Cert Team' })
    expect(container.querySelector('.page-head .total')).toHaveTextContent('rbac.unit {"count":2}')
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'common.description', 'rbac.inheritsFrom', 'rbac.columns.permissions', 'rbac.columns.users', 'common.type', 'common.actions'])
    fireEvent.click(within(screen.getByRole('group', { name: 'rbac.filterByType' })).getByRole('button', { name: /common\.custom/ }))
    expect(screen.queryByRole('button', { name: 'common.viewer' })).toBeNull()
    expect(container.querySelector('footer.table-footer')).toHaveTextContent('rbac.range {"shown":1,"count":2}')
  })
})

describe('the seeded roles', () => {
  // Named and described in the language, as the account list names the same roles; a custom role keeps its own words
  it('names and describes a system role in the language, a custom role as written', async () => {
    page()
    await screen.findByRole('button', { name: 'common.viewer' })
    expect(screen.queryByText('Read only')).toBeNull()
    expect(screen.getAllByText('rbac.systemRoles.viewer').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Cert Team' })).toBeInTheDocument()
  })
})

describe('the role dock', () => {
  it('reads the properties as typed rows: the type a neutral pill, no parent muted, the counts plain, in the list\'s words', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Cert Team' }))
    const kv = dock().querySelector('dl.kv')
    expect(kv).not.toBeNull()
    expect(dock().querySelector('dl.props')).toBeNull()
    const row = (term) => within(kv).getByText(term, { selector: 'dt' }).closest('div.row')
    // A type, not a state: neutral, never the success colour
    expect(row('common.type').querySelector('dd.v .badge')).toHaveTextContent('common.custom')
    expect(row('common.type').querySelector('dd.v .badge').className).toBe('badge')
    const parent = row('rbac.inheritsFrom').querySelector('dd')
    expect(parent).toHaveClass('absent')
    expect(parent).toHaveTextContent('—')
    expect(row('rbac.columns.users').querySelector('dd.v')).toHaveTextContent('users.unit {"count":4}')
    expect(row('rbac.columns.permissions').querySelector('dd.v')).toHaveTextContent(/^1\/3$/)
  })

  it('reads a system role without any action', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'common.viewer' }))
    expect(within(dock()).getByText('rbac.systemRoleWarning')).toBeTruthy()
    expect(within(dock()).queryByRole('button', { name: 'common.saveChanges' })).toBeNull()
    expect(within(dock()).queryByRole('button', { name: 'common.delete' })).toBeNull()
    fireEvent.click(within(dock()).getByRole('tab', { name: 'common.permissions' }))
    const boxes = within(dock()).getAllByRole('checkbox')
    expect(boxes.length).toBeGreaterThan(0)
    expect(boxes.every((b) => b.disabled)).toBe(true)
  })

  it('draws a role\'s permissions in the group dialog\'s grid, a whole-resource box first', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Cert Team' }))
    fireEvent.click(within(dock()).getByRole('tab', { name: 'common.permissions' }))
    const table = within(dock()).getByRole('table', { name: 'common.permissions' })
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['groups.resource', 'common.all', 'groups.actions.read', 'groups.actions.write', 'groups.actions.delete'])
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent)).toEqual(['rbac.categories.certificates', 'rbac.categories.certificateAuthorities'])
    const certs = within(table).getByRole('rowheader', { name: 'rbac.categories.certificates' }).closest('tr')
    expect(within(certs).getAllByRole('checkbox').map((c) => [c.getAttribute('aria-label'), c.checked])).toEqual([
      ['rbac.allOf {"name":"rbac.categories.certificates"}', false],
      ['groups.grant {"action":"groups.actions.read","resource":"rbac.categories.certificates"}', true],
      ['groups.grant {"action":"groups.actions.write","resource":"rbac.categories.certificates"}', false],
    ])
    expect(dock().textContent).not.toMatch(/(read|write|delete):/)
    // Save waits for a change, then saves it
    expect(within(dock()).getByRole('button', { name: 'common.saveChanges' })).toBeDisabled()
    fireEvent.click(within(certs).getByRole('checkbox', { name: /groups\.actions\.write/ }))
    expect(within(dock()).getByRole('button', { name: 'common.saveChanges' })).toBeEnabled()
    fireEvent.click(within(dock()).getByRole('button', { name: 'common.saveChanges' }))
    await waitFor(() => expect(stable.update).toHaveBeenCalled())
    expect(stable.update.mock.calls[0][1].permissions.sort()).toEqual(['read:certificates', 'write:certificates'])
  })

  it('marks a permission inherited from the parent role, checked and locked', async () => {
    stable.list.mockResolvedValue({ data: [{ id: 3, name: 'Child', is_system: false, user_count: 0, inherits_from: 1, parent_name: 'Viewer',
      permissions: ['write:certificates'], all_permissions: ['write:certificates', 'read:cas'] }] })
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Child' }))
    fireEvent.click(within(dock()).getByRole('tab', { name: 'common.permissions' }))
    const box = within(dock()).getByRole('checkbox', { name: 'groups.grant {"action":"groups.actions.read","resource":"rbac.categories.certificateAuthorities"}' })
    expect(box).toBeChecked()
    expect(box).toBeDisabled()
    expect(box.closest('td')).toHaveTextContent('rbac.inherited {"name":"Viewer"}')
    expect(within(dock()).getByRole('checkbox', { name: /groups\.actions\.write.*certificates/ })).not.toBeDisabled()
  })

  it('grants a whole resource to a custom role and saves it', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Cert Team' }))
    fireEvent.click(within(dock()).getByRole('tab', { name: 'common.permissions' }))
    const all = within(dock()).getAllByRole('checkbox', { name: /rbac\.allOf/ })[0]
    expect(all.indeterminate).toBe(true)
    fireEvent.click(all)
    fireEvent.click(within(dock()).getByRole('button', { name: 'common.saveChanges' }))
    await waitFor(() => expect(stable.update).toHaveBeenCalled())
    expect(stable.update.mock.calls[0][1].permissions.sort()).toEqual(['read:certificates', 'write:certificates'])
  })

  it('deletes a custom role after the confirmation only', async () => {
    stable.notify.showConfirm.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Cert Team' }))
    fireEvent.click(within(dock()).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(stable.notify.showConfirm).toHaveBeenCalledTimes(1))
    expect(stable.remove).not.toHaveBeenCalled()
    fireEvent.click(within(dock()).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(stable.remove).toHaveBeenCalledWith(2))
  })
})

describe('the role dock in the URL', () => {
  it('reopens the role and section of the URL, then writes the one opened', async () => {
    const r = renderAtUrl(<RBACPage />, '/rbac?item=2&section=permissions')
    const dock = await r.dock()
    expect(within(dock).getByRole('tab', { name: 'common.permissions' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Cert Team')
    fireEvent.click(screen.getByRole('button', { name: 'common.viewer' }))
    expect(r.where()).toBe('/rbac?item=1')
  })

  it('opens by name, sorts every column from its header, keeps the sort in the address and reads it back (T1, T4, T9)', async () => {
    const r = renderAtUrl(<RBACPage />, '/rbac')
    await screen.findByRole('button', { name: 'Cert Team' })
    expect(sortedHeads()).toEqual([['atelier.name', 'ascending']])
    expect(names()).toEqual(['Cert Team', 'common.viewer'])
    expect(sortableHeads()).toEqual(['atelier.name', 'common.description', 'rbac.inheritsFrom', 'rbac.columns.permissions', 'rbac.columns.users', 'common.type'])
    // The counts are numbers at the right, under short labels that name the whole one
    expect(screen.getByRole('button', { name: 'common.permissions' })).toHaveTextContent('rbac.columns.permissions')
    expect(screen.getByRole('button', { name: 'common.users' }).closest('th')).toHaveClass('num')
    fireEvent.click(screen.getByRole('button', { name: 'common.users' }))
    expect(names()).toEqual(['Cert Team', 'common.viewer'])
    fireEvent.click(screen.getByRole('button', { name: 'common.users' }))
    expect(names()).toEqual(['common.viewer', 'Cert Team'])
    expect(r.where()).toBe('/rbac?sort=users&order=desc')
    r.unmount()
    renderAtUrl(<RBACPage />, '/rbac?sort=permissions&order=desc')
    await screen.findByRole('button', { name: 'Cert Team' })
    expect(sortedHeads()).toEqual([['rbac.columns.permissions', 'descending']])
    expect(names()).toEqual(['common.viewer', 'Cert Team'])
  })
})
