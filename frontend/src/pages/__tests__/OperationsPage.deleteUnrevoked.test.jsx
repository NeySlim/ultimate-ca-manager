/**
 * Bulk deletion of users whose mTLS certificates could not be revoked warns with
 * the server's message, as those certificates stay valid.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({ bulkDelete: vi.fn(), showWarning: vi.fn(), showSuccess: vi.fn() }))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess, showError: vi.fn(), showInfo: mocks.showInfo, showWarning: mocks.showWarning,
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
    isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({
    canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    isAdmin: () => true,
  }),
}))

vi.mock('../../services', () => ({
  opnsenseService: { test: vi.fn(), import: vi.fn() },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }), bulkDelete: vi.fn() },
  certificatesService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }) },
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), bulkSign: vi.fn() },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: {
    getAll: vi.fn().mockResolvedValue({ data: [{ id: 9, username: 'alice' }], meta: { total: 1 } }),
    bulkDelete: (...args) => mocks.bulkDelete(...args),
  },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportWidget: () => null }))

vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveLayout: ({ tabs = [], onTabChange, children }) => (
    <div>
      {tabs.map((tab) => <button key={tab.id} onClick={() => onTabChange(tab.id)}>{`tab-${tab.id}`}</button>)}
      {children}
    </div>
  ),
  ResponsiveDataTable: ({ onSelectionChange, bulkActions }) => (
    <div>
      <button onClick={() => onSelectionChange(new Set([9]))}>select-users</button>
      {bulkActions}
    </div>
  ),
}))

import OperationsPage from '../OperationsPage'

const deleteSelected = async () => {
  render(<MemoryRouter><OperationsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('tab-bulk'))
  fireEvent.click(await screen.findByText('select-users'))
  fireEvent.click(await screen.findByText('common.delete'))
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'common.delete' }))
}

describe('OperationsPage bulk user deletion with unrevoked mTLS certificates', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('ucm-ops-resource-type', 'users')
  })

  it('warns with the server message', async () => {
    mocks.bulkDelete.mockResolvedValue({
      data: { success: [9], failed: [], unrevoked: [{ user_id: 9, certificates: [{ id: 3 }] }] },
      message: '1 users deleted; mTLS certificate(s) #3 could not be revoked',
    })
    await deleteSelected()
    await waitFor(() => expect(mocks.showWarning)
      .toHaveBeenCalledWith('1 users deleted; mTLS certificate(s) #3 could not be revoked'))
  })

  it('does not warn when every certificate was revoked', async () => {
    mocks.bulkDelete.mockResolvedValue({ data: { success: [9], failed: [], unrevoked: [] }, message: '1 users deleted' })
    await deleteSelected()
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalled())
    expect(mocks.showWarning).not.toHaveBeenCalled()
  })
})
