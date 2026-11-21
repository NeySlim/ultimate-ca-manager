/**
 * OperationsPage: an export that left unreadable entries out says so, on the
 * export tab (all certificates, all CAs) and on the bulk export of a selection.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

const mocks = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  certExportAll: vi.fn(), caExportAll: vi.fn(), certBulkExport: vi.fn(),
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

const blob = (skipped, exported) => {
  const b = new Blob(['pem'])
  if (skipped) b.skippedCount = skipped
  if (exported !== undefined) b.exportedCount = exported
  return b
}

const openTab = async (tab) => {
  render(<MemoryRouter><OperationsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('link', { name: { export: 'common.export', bulk: 'operations.bulkActions' }[tab] }))
}

describe('OperationsPage export of everything', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  // First "pemBundle" button is the certificates one, the second the CAs one
  it.each([
    ['certificates', 0, 'certExportAll'],
    ['CAs', 1, 'caExportAll'],
  ])('warns when %s were left out', async (_n, index, svc) => {
    mocks[svc].mockResolvedValue(blob(2))
    await openTab('export')
    fireEvent.click((await screen.findAllByRole('button', { name: 'common.download importExport.export.pemBundle' }))[index])
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('export.skippedUnreadable:2'))
    expect(mocks.showSuccess).toHaveBeenCalled()
  })

  it.each([
    ['certificates', 0, 'certExportAll'],
    ['CAs', 1, 'caExportAll'],
  ])('says nothing more when no %s were left out', async (_n, index, svc) => {
    mocks[svc].mockResolvedValue(blob(0))
    await openTab('export')
    fireEvent.click((await screen.findAllByRole('button', { name: 'common.download importExport.export.pemBundle' }))[index])
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalled())
    expect(mocks.showWarning).not.toHaveBeenCalled()
  })
})

describe('OperationsPage bulk export of a selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  const exportSelection = async () => {
    await openTab('bulk')
    fireEvent.click(await screen.findByText('select-certs'))
    fireEvent.click(await screen.findByText('operations.exportPem'))
  }

  it('warns when certificates of the selection were left out', async () => {
    mocks.certBulkExport.mockResolvedValue(blob(2))
    await exportSelection()
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('export.skippedUnreadable:2'))
    expect(mocks.certBulkExport).toHaveBeenCalledWith([1], 'pem')
  })

  it('says nothing more when the whole selection was exported', async () => {
    mocks.certBulkExport.mockResolvedValue(blob(0))
    await exportSelection()
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalled())
    expect(mocks.showWarning).not.toHaveBeenCalled()
  })

  it('announces the number the server exported, not the number selected', async () => {
    mocks.certBulkExport.mockResolvedValue(blob(0, 7))
    await exportSelection()
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('operations.bulkSuccess:7'))
  })

  it('falls back to the selection when the server gave no count', async () => {
    mocks.certBulkExport.mockResolvedValue(blob(0))
    await exportSelection()
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('operations.bulkSuccess:1'))
  })
})
