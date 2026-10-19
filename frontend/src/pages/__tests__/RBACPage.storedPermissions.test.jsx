/**
 * The role editor never drops a stored permission: one the server does not
 * grant is shown as ignored and saved back as it is.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    useModals: modals.useModals,
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
  }
})

const updateRole = vi.fn(() => Promise.resolve({ data: {} }))
const ROLE = {
  id: 5, name: 'Legacy Role', description: '', is_system: false, user_count: 0,
  permissions: ['read:certs', '*', 'read:dashboard'], all_permissions: ['read:certificates'],
}
vi.mock('../../services', () => ({
  rolesService: {
    listRoles: () => Promise.resolve({ data: [ROLE] }),
    listPermissions: () => Promise.resolve({ data: ['read:certificates', 'write:certificates', 'read:cas'] }),
    updateRole: (...args) => updateRole(...args),
  },
}))

import RBACPage from '../RBACPage'

describe('RBACPage keeps what it cannot grant', () => {
  it('shows ignored permissions, counts only applied ones, and saves them all back', async () => {
    render(<MemoryRouter><RBACPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('Legacy Role'))[0])

    const ignored = await screen.findByTestId('rbac-ignored-permissions')
    expect(ignored.textContent).toContain('*')
    expect(ignored.textContent).toContain('read:dashboard')
    expect(screen.getByText('1/3')).toBeInTheDocument()

    fireEvent.click(screen.getByText('common.saveChanges'))
    await waitFor(() => expect(updateRole).toHaveBeenCalled())
    const sent = updateRole.mock.calls[0][1].permissions
    expect(sent).toEqual(['read:certificates', '*', 'read:dashboard'])
  })

  it('toggles the legacy name it displays as granted', async () => {
    updateRole.mockClear()
    render(<MemoryRouter><RBACPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('Legacy Role'))[0])
    await screen.findByTestId('rbac-ignored-permissions')
    // certificates comes first; its "read" chip reads as granted through read:certs
    fireEvent.click(screen.getAllByText('read')[0])
    fireEvent.click(screen.getByText('common.saveChanges'))
    await waitFor(() => expect(updateRole).toHaveBeenCalled())
    expect(updateRole.mock.calls[0][1].permissions).toEqual(['*', 'read:dashboard'])
  })
})
