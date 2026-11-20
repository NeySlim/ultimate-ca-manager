/**
 * Operations on the sectioned template: a table of contents of the three operations,
 * one frame at a time, a link to ?tab= opening on its operation, no save bar (import,
 * export and bulk actions keep their own buttons).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.ids ? `${key} ${opts.ids}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({ bulkDelete: vi.fn(), showWarning: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess, showError: vi.fn(), showInfo: mocks.showInfo, showWarning: mocks.showWarning,
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
    isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useInspector: () => ({
    openEntity: vi.fn(),closeWindow: vi.fn(), windows: [],
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
  ResponsiveLayout: ({ children }) => <div>{children}</div>,
  ResponsiveDataTable: ({ onSelectionChange, bulkActions }) => (
    <div>
      <button onClick={() => onSelectionChange(new Set([9]))}>select-users</button>
      {bulkActions}
    </div>
  ),
}))

import OperationsPage from '../OperationsPage'

const open = (entry = '/operations') => render(<MemoryRouter initialEntries={[entry]}><OperationsPage /></MemoryRouter>)
const toc = () => screen.getByRole('navigation', { name: 'operations.tocLabel' })

describe('OperationsPage sections', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('lists the three operations and shows import first, without a save bar', async () => {
    open()
    const links = within(toc()).getAllByRole('link')
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/operations', '/operations?tab=export', '/operations?tab=bulk'])
    expect(screen.getByRole('heading', { level: 2, name: 'common.import' })).toBeInTheDocument()
    expect(within(toc()).getByRole('link', { name: 'common.import' })).toHaveAttribute('aria-current', 'true')
    expect(screen.queryByTestId('sf-savebar')).toBeNull()
  })

  it('opens on the operation a link names', async () => {
    open('/operations?tab=bulk')
    expect(await screen.findByRole('heading', { level: 2, name: 'operations.bulkActions' })).toHaveFocus()
    expect(screen.queryByRole('heading', { level: 2, name: 'common.import' })).toBeNull()
  })

  it('switches the frame from the table of contents and from the phone list', async () => {
    open()
    fireEvent.click(within(toc()).getByRole('link', { name: 'common.export' }))
    expect(screen.getByRole('heading', { level: 2, name: 'common.export' })).toHaveFocus()
    fireEvent.change(screen.getByLabelText('sectioned.jumpLabel'), { target: { value: 'bulk' } })
    expect(await screen.findByRole('heading', { level: 2, name: 'operations.bulkActions' })).toBeInTheDocument()
  })
})
