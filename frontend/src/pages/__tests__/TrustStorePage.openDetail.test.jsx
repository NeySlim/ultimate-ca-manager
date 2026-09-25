/**
 * TrustStorePage: adding one CA (managed or via Smart Import) opens its detail.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
  }),
}))

let mockIsMobile = false
const openWindow = vi.fn()
let mockCanRead = true

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
  useMobile: () => ({ isMobile: mockIsMobile }),
  useWindowManager: () => ({ openWindow, closeWindow: vi.fn(), windows: [] }),
}))

// TrustStorePage imports these two directly by path — same spies
vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({ openWindow, closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: mockIsMobile }),
}))

vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    useModals: modals.useModals,
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true,
      canRead: (resource) => (resource === 'cas' ? mockCanRead : true),
    }),
  }
})

const getAll = vi.fn()
const add = vi.fn()
const exportCA = vi.fn()
vi.mock('../../services', () => ({
  truststoreService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 0, root_ca: 0, intermediate_ca: 0, expired: 0, valid: 0 } }),
    add: (...args) => add(...args),
  },
  casService: {
    getAll: (...args) => getAll(...args),
    export: (...args) => exportCA(...args),
  },
}))

vi.mock('../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Badge: ({ children }) => <span>{children}</span>,
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Textarea: (props) => <textarea {...props} />,
  HelpCard: ({ children }) => <div>{children}</div>,
  CompactSection: ({ children }) => <div>{children}</div>,
  CompactGrid: ({ children }) => <div>{children}</div>,
  CompactField: () => null,
  FormSelect: () => null,
}))
vi.mock('../../components/ui/responsive', () => ({
  ResponsiveLayout: ({ children }) => <div>{children}</div>,
  ResponsiveDataTable: ({ toolbarActions }) => <div>{toolbarActions}</div>,
}))

// Stub Smart Import: a button that fires onImportComplete with a given result
let importResult = null
vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) =>
    isOpen ? <button onClick={() => onImportComplete(importResult)}>fire-import-complete</button> : null,
}))

import TrustStorePage from '../TrustStorePage'

const renderPage = () => render(<MemoryRouter><TrustStorePage /></MemoryRouter>)

describe('TrustStorePage — opens detail after add/import', () => {
  beforeEach(() => {
    mockIsMobile = false
    mockCanRead = true
    openWindow.mockReset()
    getAll.mockReset()
    add.mockReset()
    exportCA.mockReset()
    getAll.mockResolvedValue({ data: [
      { id: 1, descr: 'CA One', is_root: true },
      { id: 2, descr: 'CA Two', is_root: true },
    ] })
    exportCA.mockResolvedValue({ data: 'PEM-DATA' })
    importResult = null
  })

  it('adding one managed CA opens the entry truststoreService.add returned', async () => {
    add.mockResolvedValue({ data: { id: 101 } })
    renderPage()
    fireEvent.click(await screen.findByText('trustStore.add'))
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    const checkboxes = await screen.findAllByRole('checkbox')
    // index 0 is "select all"; pick the first CA row only
    fireEvent.click(checkboxes[1])
    fireEvent.click(screen.getByText('trustStore.addSelected:1'))
    await waitFor(() => expect(add).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('truststore', 101))
  })

  it('adding two managed CAs opens nothing', async () => {
    add.mockResolvedValue({ data: { id: 101 } })
    renderPage()
    fireEvent.click(await screen.findByText('trustStore.add'))
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    const checkboxes = await screen.findAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    fireEvent.click(checkboxes[2])
    fireEvent.click(screen.getByText('trustStore.addSelected:2'))
    await waitFor(() => expect(add).toHaveBeenCalledTimes(2))
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('Smart Import of a single CA opens it', async () => {
    importResult = { imported_ids: { cas: [55], certificates: [], csrs: [] } }
    renderPage()
    fireEvent.click(await screen.findByText('common.import'))
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 55))
  })

  it('Smart Import opening a CA is blocked without read permission', async () => {
    mockCanRead = false
    importResult = { imported_ids: { cas: [55], certificates: [], csrs: [] } }
    renderPage()
    fireEvent.click(await screen.findByText('common.import'))
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(screen.queryByText('fire-import-complete')).not.toBeInTheDocument())
    expect(openWindow).not.toHaveBeenCalled()
  })
})
