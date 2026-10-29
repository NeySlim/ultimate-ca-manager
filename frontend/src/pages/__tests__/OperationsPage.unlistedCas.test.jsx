/**
 * The CA picker of the bulk CSR signing lists the CAs able to sign and counts
 * the others (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
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
  casService: { getAll: vi.fn().mockResolvedValue({ data: [
    { id: 1, descr: 'Signing CA', has_private_key: true },
    { id: 2, descr: 'Keyless root', certificate_only: true, has_private_key: false },
    { id: 3, descr: 'Offline CA', has_private_key: true, offline: true },
  ] }), bulkDelete: vi.fn() },
  certificatesService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }) },
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 7, cn: 'req.example.com' }], meta: { total: 1 } }), bulkSign: vi.fn() },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportWidget: () => null }))

// Stubs for the layout and the table: a tab button, and a selection button that shows the bulk actions.
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
      <button onClick={() => onSelectionChange(new Set([7]))}>select-csr</button>
      {bulkActions}
    </div>
  ),
}))

import OperationsPage from '../OperationsPage'

describe('OperationsPage bulk CSR signing CA picker (#426)', () => {
  beforeEach(() => {
    mockIsMobile = false
    localStorage.setItem('ucm-ops-resource-type', 'csrs')
  })

  it('offers only the CA that can sign and counts the others', async () => {
    render(<MemoryRouter><OperationsPage /></MemoryRouter>)
    fireEvent.click(await screen.findByText('tab-bulk'))
    fireEvent.click(await screen.findByText('select-csr'))
    fireEvent.click(await screen.findByText('common.sign'))
    const dialog = await screen.findByRole('dialog')
    const options = within(dialog).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)
    expect(options).toEqual(['Signing CA'])
    expect(dialog).toHaveTextContent('cas.notListedForSigning:2')
  })
})
