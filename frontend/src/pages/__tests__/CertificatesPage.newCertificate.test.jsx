/**
 * CertificatesPage: a certificate just issued is easy to find (#368).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, renderHook, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockIsMobile = false
const openWindow = vi.fn()
const create = vi.fn()

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({ isMobile: mockIsMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({
    openWindow, closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
const getById = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...args) => getAll(...args),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 3, expiring: 0, expired: 0, revoked: 1, total: 4 } }),
    revoke: vi.fn().mockResolvedValue({ data: {} }),
    create: (...args) => create(...args),
    getById: (...args) => getById(...args),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
}))


// The form itself is not under test: a stub that submits what the real one would
vi.mock('../certificates/IssueCertificateForm', () => ({
  IssueCertificateForm: ({ onSubmit }) => (
    <button type="button" onClick={() => onSubmit({ cn: 'new.example.com' })}>submit-issue</button>
  ),
}))

// Stub Smart Import: a button that fires onImportComplete with a given result
let importResult = null
vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) =>
    isOpen ? <button onClick={() => onImportComplete(importResult)}>fire-import-complete</button> : null,
}))

import CertificatesPage from '../CertificatesPage'
import { useCertificateColumns } from '../certificates/useCertificateColumns'

const renderPage = () => render(
  <MemoryRouter><CertificatesPage /></MemoryRouter>
)

const issue = async () => {
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getAllByText('certificates.issueCertificate')[0])
  fireEvent.click(await screen.findByText('submit-issue'))
  await waitFor(() => expect(create).toHaveBeenCalled())
}

describe('CertificatesPage — finding a new certificate (#368)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mockIsMobile = false
    openWindow.mockReset()
    create.mockReset()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    importResult = null
  })

  it('offers a sortable creation date column', () => {
    const { result } = renderHook(() => useCertificateColumns((key) => key))
    const column = result.current.find(col => col.key === 'created_at')
    expect(column).toBeDefined()
    expect(column.sortable).toBe(true)
    expect(column.header).toBe('common.created')
  })

  it('opens the certificate it has just issued', async () => {
    create.mockResolvedValue({ data: { id: 99, cn: 'new.example.com' } })
    renderPage()
    await issue()
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 99))
  })

  it('opens nothing while the request waits for approval', async () => {
    create.mockResolvedValue({ data: {
      approval_required: true, approval_id: 7, policy_name: 'P', status: 'pending_approval',
    } })
    renderPage()
    await issue()
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('Smart Import of a single certificate opens it', async () => {
    importResult = { imported_ids: { cas: [], certificates: [13], csrs: [] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(screen.getAllByText('common.import')[0])
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 13))
  })

  it('Smart Import of a single CA opens it', async () => {
    importResult = { imported_ids: { cas: [21], certificates: [], csrs: [] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(screen.getAllByText('common.import')[0])
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 21))
  })

  it('Smart Import of several objects opens nothing', async () => {
    importResult = { imported_ids: { cas: [21], certificates: [13], csrs: [] } }
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(screen.getAllByText('common.import')[0])
    fireEvent.click(await screen.findByText('fire-import-complete'))
    await waitFor(() => expect(screen.queryByText('fire-import-complete')).not.toBeInTheDocument())
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('a deep link opens the certificate even when filters hide its row', async () => {
    // Mobile follows /certificates/:id after a creation made on another page
    mockIsMobile = true
    getById.mockResolvedValue({ data: { id: 401, subject: 'CN=hidden' } })
    render(
      <MemoryRouter initialEntries={['/certificates/401']}>
        <Routes><Route path="/certificates/:id" element={<CertificatesPage />} /></Routes>
      </MemoryRouter>
    )
    await waitFor(() => expect(getById).toHaveBeenCalledWith(401))
  })
})
