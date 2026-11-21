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
      .toEqual(['atelier.name', 'common.description', 'rbac.inheritsFrom', 'common.permissions', 'common.users', 'atelier.state', 'common.actions'])
    fireEvent.click(within(screen.getByRole('group', { name: 'rbac.filterByType' })).getByRole('button', { name: /common\.custom/ }))
    expect(screen.queryByRole('button', { name: 'Viewer' })).toBeNull()
    expect(container.querySelector('footer.table-footer')).toHaveTextContent('rbac.range {"shown":1,"count":2}')
  })
})

describe('the role dock', () => {
  it('reads a system role without any action', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Viewer' }))
    expect(within(dock()).getByText('rbac.systemRoleWarning')).toBeTruthy()
    expect(within(dock()).queryByRole('button', { name: 'common.saveChanges' })).toBeNull()
    expect(within(dock()).queryByRole('button', { name: 'common.delete' })).toBeNull()
    fireEvent.click(within(dock()).getByRole('tab', { name: 'common.permissions' }))
    const boxes = within(dock()).getAllByRole('checkbox')
    expect(boxes.length).toBeGreaterThan(0)
    expect(boxes.every((b) => b.disabled)).toBe(true)
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
    fireEvent.click(screen.getByRole('button', { name: 'Viewer' }))
    expect(r.where()).toBe('/rbac?item=1')
  })
})
