/**
 * OperationsPage: Smart Import widget completion opens the sole created
 * entity (#368). A CSR has no detail window, so it opens nothing.
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

let mockIsMobile = false
const openWindow = vi.fn()

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: mockIsMobile, isTablet: false, isDesktop: !mockIsMobile, isTouch: false,
    isLargeScreen: !mockIsMobile, screenWidth: mockIsMobile ? 375 : 1440,
    sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useWindowManager: () => ({
    openWindow, closeWindow: vi.fn(), windows: [],
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
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('../../components/SmartImport', () => ({
  SmartImportWidget: ({ onImportComplete }) => (
    <button onClick={() => onImportComplete(window.__importResult)}>do-import</button>
  ),
}))

import OperationsPage from '../OperationsPage'

const renderPage = () => render(
  <MemoryRouter><OperationsPage /></MemoryRouter>
)

describe('OperationsPage — Smart Import opens the sole created entity (#368)', () => {
  beforeEach(() => {
    mockIsMobile = false
    openWindow.mockReset()
  })

  it('opens the CA when exactly one was imported', async () => {
    window.__importResult = { imported_ids: { cas: [501] } }
    renderPage()
    fireEvent.click(await screen.findByText('do-import'))
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 501))
  })

  it('opens nothing when exactly one CSR was imported (no detail window)', async () => {
    window.__importResult = { imported_ids: { csrs: [502] } }
    renderPage()
    fireEvent.click(await screen.findByText('do-import'))
    // Give any (wrong) async open a chance to fire before asserting it didn't
    await new Promise((r) => setTimeout(r, 0))
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('opens nothing when two objects were imported', async () => {
    window.__importResult = { imported_ids: { cas: [503], certificates: [504] } }
    renderPage()
    fireEvent.click(await screen.findByText('do-import'))
    await new Promise((r) => setTimeout(r, 0))
    expect(openWindow).not.toHaveBeenCalled()
  })
})
