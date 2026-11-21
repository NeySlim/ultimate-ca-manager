/**
 * Bulk actions: a row reads as the mockup's table, the name alone (no coloured icon tile)
 * and the status as a badge of an icon and a word (no dot).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number'
      ? `${key}:${opts.count}${opts.ids ? `:${opts.ids}` : ''}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  bulkRevoke: vi.fn(), bulkRenew: vi.fn(), bulkDeleteUsers: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(), getById: vi.fn(),
  selection: [1],
  certs: [
    { id: 1, cn: 'pair.example.com', related_certificate_id: 2 },
    { id: 2, cn: 'pair.example.com', related_certificate_id: 1 },
    { id: 3, cn: 'web.example.com', related_certificate_id: null },
    { id: 4, cn: 'pair.example.com', related_certificate_id: 1 },
    { id: 5, cn: 'old.example.com', related_certificate_id: 6 },
    { id: 6, cn: 'old.example.com', related_certificate_id: 5, revoked: true },
    { id: 7, cn: 'far.example.com', related_certificate_id: 8 },
    { id: 9, cn: 'old2.example.com', related_certificate_id: 10 },
    { id: 10, cn: 'old2.example.com', related_certificate_id: 9, archived: true },
  ],
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: mocks.showInfo, showWarning: mocks.showWarning,
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
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }), bulkDelete: vi.fn() },
  certificatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: mocks.certs, meta: { total: 3 } })),
    bulkRevoke: (...args) => mocks.bulkRevoke(...args),
    bulkRenew: (...args) => mocks.bulkRenew(...args),
    getById: (...args) => mocks.getById(...args),
  },
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), bulkSign: vi.fn() },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: { getAll: vi.fn().mockResolvedValue({ data: [] }), bulkDelete: (...args) => mocks.bulkDeleteUsers(...args) },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

vi.mock('../../components/atelier', async (orig) => ({
  ...(await orig()),
  // Draws each cell of each row as the page renders it
  TableView: ({ rows, columns }) => (
    <table><tbody>{rows.map((row) => (
      <tr key={row.id}>{columns.map((c) => <td key={c.id}>{c.cell(row)}</td>)}</tr>
    ))}</tbody></table>
  ),
}))

import OperationsPage from '../OperationsPage'

describe('OperationsPage bulk table cells', () => {
  beforeEach(() => {
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    mocks.certs = [{ id: 1, cn: 'web.example.com', status: 'valid', has_private_key: true }]
  })

  it('shows the name without an icon tile and the status without a dot', async () => {
    const { container } = render(<MemoryRouter initialEntries={['/operations?tab=bulk']}><OperationsPage /></MemoryRouter>)
    await screen.findByText('web.example.com')
    const row = container.querySelector('tbody tr')
    expect(row.querySelector('[class*="icon-bg-"]')).toBeNull()
    expect(row.querySelector('.ui-dot, [class*="animate-ping"], [class*="rounded-full"]')).toBeNull()
    expect(row).toHaveTextContent('common.valid')
  })
})
