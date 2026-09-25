/**
 * CAsPage: creating a CA or Smart-Importing a single object opens its detail.
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

// CAsPage imports these two directly by path — same spies, same module instances
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
      canRead: () => mockCanRead,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
vi.mock('../../services', () => ({
  casService: {
    getAll: (...args) => getAll(...args),
    getChainRepairStatus: vi.fn().mockResolvedValue({ data: null }),
  },
}))

vi.mock('../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  LoadingSpinner: () => <div>loading</div>,
  MultiSelectFilter: () => null,
}))
vi.mock('../../components/ui/responsive', () => ({
  ResponsiveLayout: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../components/cas/ManageTemplatePinsModal', () => ({
  ManageTemplatePinsModal: () => null,
}))
vi.mock('../cas/OrgView', () => ({ OrgView: () => null }))
vi.mock('../cas/ColumnsView', () => ({ ColumnsView: () => null }))
vi.mock('../cas/ListView', () => ({ ListView: () => null }))
vi.mock('../cas/CADetailsPanel', () => ({ CADetailsPanel: () => null }))
vi.mock('../cas/ChainRepairBar', () => ({ ChainRepairBar: () => null }))

// Stub the create modal: a button that fires onSuccess with the created CA
vi.mock('../cas/CreateCAModal', () => ({
  CreateCAModal: ({ open, onSuccess }) =>
    open ? <button onClick={() => onSuccess({ id: 42, common_name: 'New CA' })}>fire-create-success</button> : null,
}))

// Stub Smart Import: a button that fires onImportComplete with a given result
let importResult = null
vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) =>
    isOpen ? <button onClick={() => onImportComplete(importResult)}>fire-import-complete</button> : null,
}))

import CAsPage from '../CAsPage'

const renderPage = () => render(<MemoryRouter><CAsPage /></MemoryRouter>)

describe('CAsPage — opens detail after create/import', () => {
  beforeEach(() => {
    mockIsMobile = false
    mockCanRead = true
    openWindow.mockReset()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [] })
    importResult = null
  })

  it('opens the CA it has just created', async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('common.create'))
    fireEvent.click(await screen.findByText('fire-create-success'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 42))
  })

  it('Smart Import of a single CA opens it', async () => {
    importResult = { imported_ids: { cas: [7], certificates: [], csrs: [] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('common.import'))
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 7))
  })

  it('Smart Import of a single certificate opens it', async () => {
    importResult = { imported_ids: { cas: [], certificates: [9], csrs: [] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('common.import'))
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 9))
  })

  it('Smart Import of two objects opens nothing', async () => {
    importResult = { imported_ids: { cas: [7], certificates: [9], csrs: [] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('common.import'))
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(screen.queryByText('fire-import-complete')).not.toBeInTheDocument())
    expect(openWindow).not.toHaveBeenCalled()
  })
})
