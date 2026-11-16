/**
 * CAsPage: a CA that appears after the first load starts expanded in the hierarchy,
 * so an intermediate just created under a new root is visible.
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
const openEntity = vi.fn()
let mockCanRead = true

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
  useMobile: () => ({ isMobile: mockIsMobile }),
  useInspector: () => ({ openEntity, closeWindow: vi.fn(), windows: [] }),
}))

// CAsPage imports these two directly by path — same spies, same module instances
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity, closeWindow: vi.fn(), windows: [] }),
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
    getCrossFindings: vi.fn().mockResolvedValue({ data: { findings: [] } }),
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
vi.mock('../cas/OrgView', () => ({
  OrgView: ({ expandedNodes }) => <div data-testid="expanded">{[...expandedNodes].sort().join(',')}</div>,
}))
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

describe('CAsPage: hierarchy expansion', () => {
  beforeEach(() => {
    mockIsMobile = false
    mockCanRead = true
    getAll.mockReset()
  })

  it('expands a root created after the first load once it has a child', async () => {
    getAll.mockResolvedValueOnce({ data: [{ id: 1, type: 'root', common_name: 'Old root' }] })
    getAll.mockResolvedValue({ data: [
      { id: 1, type: 'root', common_name: 'Old root' },
      { id: 2, type: 'root', common_name: 'New root' },
      { id: 3, type: 'intermediate', parent_id: 2, common_name: 'New intermediate' },
    ] })
    render(<MemoryRouter><CAsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('expanded').textContent).toBe('1'))
    fireEvent.click(await screen.findByText('common.create'))
    fireEvent.click(await screen.findByText('fire-create-success'))
    await waitFor(() => expect(screen.getByTestId('expanded').textContent.split(',')).toContain('2'))
  })
})
