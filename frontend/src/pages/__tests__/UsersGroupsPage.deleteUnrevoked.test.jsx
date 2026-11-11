/**
 * Deleting a user whose mTLS certificate could not be revoked warns with the
 * server's message instead of announcing a plain success.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  showSuccess: vi.fn(), showWarning: vi.fn(), showError: vi.fn(), del: vi.fn(),
}))
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: (...a) => mocks.showSuccess(...a), showError: (...a) => mocks.showError(...a),
    showWarning: (...a) => mocks.showWarning(...a), showInfo: () => {},
    showConfirm: () => Promise.resolve(true), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
  InspectorProvider: ({ children }) => children,
}))

vi.mock('../../components/UserSecurityKeys', () => ({ default: () => null }))
vi.mock('../../components/UserApiKeys', () => ({ default: () => null }))
vi.mock('../users/UserSecuritySection', () => ({ default: () => null }))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: actual.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

vi.mock('../../services', () => ({
  usersService: {
    getAll: vi.fn().mockResolvedValue({ data: [{ id: 9, username: 'alice', email: 'a@example.com', role: 'viewer', active: true }] }),
    delete: (...a) => mocks.del(...a),
  },
  groupsService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  rolesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  accountService: {},
  ssoService: {},
}))

vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveLayout: ({ children, slideOverContent }) => <div>{children}{slideOverContent}</div>,
  ResponsiveDataTable: ({ data = [], onRowClick }) => data.map(row => (
    <button key={row.id} type="button" onClick={() => onRowClick(row)}>{`row-${row.id}`}</button>
  )),
}))

import UsersGroupsPage from '../UsersGroupsPage'

const deleteUser = async () => {
  render(<MemoryRouter><UsersGroupsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('row-9'))
  fireEvent.click(await screen.findByRole('button', { name: /common\.delete/ }))
}

describe('UsersGroupsPage delete with unrevoked mTLS certificates', () => {
  beforeEach(() => { Object.values(mocks).forEach(m => m.mockReset()) })

  it('warns with the server message and no plain success', async () => {
    mocks.del.mockResolvedValue({
      data: { unrevoked_certificates: [{ id: 3, serial_number: 'AB' }] },
      message: 'User alice deleted; its mTLS certificate(s) #3 could not be revoked',
    })
    await deleteUser()
    await waitFor(() => expect(mocks.showWarning)
      .toHaveBeenCalledWith('User alice deleted; its mTLS certificate(s) #3 could not be revoked'))
    expect(mocks.showSuccess).not.toHaveBeenCalled()
  })

  it('warns once with both notes when the ACME CA was not told either', async () => {
    const message = 'User alice deleted; its mTLS certificate(s) #3 could not be revoked. Certificate #4: not told'
    mocks.del.mockResolvedValue({
      data: { unrevoked_certificates: [{ id: 3, serial_number: 'AB' }] },
      meta: { acme_local_only: [4] },
      message,
    })
    await deleteUser()
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith(message))
    expect(mocks.showWarning).toHaveBeenCalledTimes(1)
    expect(mocks.showSuccess).not.toHaveBeenCalled()
  })

  it('keeps the plain success when everything was revoked', async () => {
    mocks.del.mockResolvedValue({ message: 'User alice deleted successfully' })
    await deleteUser()
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('messages.success.delete.user'))
    expect(mocks.showWarning).not.toHaveBeenCalled()
  })
})
