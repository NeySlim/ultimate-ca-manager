/** The Users tile counts each user once: through the built-in role every user holds. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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

const ROLES = [
  { id: 1, name: 'Viewer', description: '', is_system: true, user_count: 7, permissions: [], all_permissions: [] },
  { id: 2, name: 'Cert Team', description: '', is_system: false, user_count: 4, permissions: [], all_permissions: [] },
]
vi.mock('../../services', () => ({
  rolesService: {
    listRoles: () => Promise.resolve({ data: ROLES }),
    listPermissions: () => Promise.resolve({ data: [] }),
  },
}))

import RBACPage from '../RBACPage'

describe('RBACPage users tile', () => {
  it('does not add custom-role holders a second time', async () => {
    render(<MemoryRouter><RBACPage /></MemoryRouter>)
    await screen.findAllByText('Cert Team')
    expect(screen.getAllByText('7').length).toBeGreaterThan(0)
    expect(screen.queryByText('11')).toBeNull()
  })
})
