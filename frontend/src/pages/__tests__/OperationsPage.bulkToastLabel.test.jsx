/**
 * OperationsPage: the toast closing a bulk action names the action in the reader's words,
 * never by its internal code.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && opts.action !== undefined ? `${key}[${opts.action}]` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  certExportAll: vi.fn(), caExportAll: vi.fn(), certBulkExport: vi.fn(), certBulkDelete: vi.fn(),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess, showError: mocks.showError, showInfo: vi.fn(),
    showWarning: mocks.showWarning,
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
    isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
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
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }), bulkDelete: vi.fn(),
    exportAll: (...a) => mocks.caExportAll(...a),
  },
  certificatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: [{ id: 1, cn: 'a.example.com' }], meta: { total: 1 } })),
    bulkDelete: (...a) => mocks.certBulkDelete(...a),
    exportAll: (...a) => mocks.certExportAll(...a),
    bulkExport: (...a) => mocks.certBulkExport(...a),
  },
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), bulkSign: vi.fn() },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: { getAll: vi.fn().mockResolvedValue({ data: [] }), bulkDelete: vi.fn() },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

// The list stands in for the Atelier table: one button ticks the records, the selection bar follows
vi.mock('../../components/atelier', async (orig) => ({
  ...(await orig()),
  TableView: ({ selection, batch }) => (
    <div>
      <button onClick={() => ([1]).forEach((id) => selection.onToggle(id))}>select-certs</button>
      {batch}
    </div>
  ),
}))

import OperationsPage from '../OperationsPage'

const selectCertificates = async () => {
  render(<MemoryRouter><OperationsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('link', { name: 'operations.bulkActions' }))
  fireEvent.click(await screen.findByText('select-certs'))
}

describe('OperationsPage bulk result toast', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  it('names a delete by its translated label', async () => {
    mocks.certBulkDelete.mockResolvedValue({ data: { success: [1], failed: [] } })
    await selectCertificates()
    fireEvent.click(await screen.findByRole('button', { name: 'common.delete' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('operations.bulkSuccess[common.delete]'))
  })

  it('names an export of the selection by its translated label', async () => {
    mocks.certBulkExport.mockResolvedValue(new Blob(['pem']))
    await selectCertificates()
    fireEvent.click(await screen.findByText('operations.exportPem'))
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('operations.bulkSuccess[common.export]'))
  })
})
