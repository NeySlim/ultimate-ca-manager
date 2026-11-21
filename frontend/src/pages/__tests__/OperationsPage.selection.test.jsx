/**
 * The bulk list of Operations in the Atelier table: ticked records from every page, the
 * Selection view that shows them alone (the former basket), the local search and paging of the
 * resources the server sends whole, and the sort of the shown rows.
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
  certificatesService: { getAll: (params) => Promise.resolve(params?.per_page === 1
    ? { data: [], meta: { total: 30 } }
    : { data: params?.page === 2 ? [{ id: 3, cn: 'third.example', status: 'valid' }] : [{ id: 1, cn: 'first.example', status: 'valid' }, { id: 2, cn: 'second.example', status: 'expired' }], meta: { total: 30 } }) },
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), bulkSign: vi.fn() },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: {
    getAll: vi.fn().mockResolvedValue({ data: [{ id: 9, username: 'zoe', role: 'viewer', active: true }, { id: 10, username: 'alice', role: 'admin', active: true }] }),
    bulkDelete: (...args) => mocks.bulkDelete(...args),
  },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import OperationsPage from '../OperationsPage'

const open = () => render(<MemoryRouter initialEntries={['/operations?tab=bulk']}><OperationsPage /></MemoryRouter>)
const names = () => [...document.querySelectorAll('#ops-scroll tbody tr')].map((tr) => tr.querySelector('td:nth-child(2)').textContent)

describe('OperationsPage bulk list', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('keeps the ticked records of every page and shows them alone in the Selection view', async () => {
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    open()
    await waitFor(() => expect(names()).toEqual(['first.example', 'second.example']))
    const selection = screen.getByRole('button', { name: 'operations.selectionOnly' })
    expect(selection).toBeDisabled()
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'table.selectRow' })[0])
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(names()).toEqual(['third.example']))
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectRow' }))
    expect(screen.getByRole('group', { name: 'table.selection' })).toHaveTextContent('table.selectedCount')
    fireEvent.click(selection)
    expect(selection).toHaveAttribute('aria-pressed', 'true')
    expect(names().sort()).toEqual(['first.example', 'third.example'])
    expect(screen.queryByRole('button', { name: 'table.nextPage' })).toBeNull()
    // Unticking in the Selection view takes the record out of it
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'table.selectRow' })[0])
    expect(names()).toHaveLength(1)
    fireEvent.click(selection)
    expect(selection).toHaveAttribute('aria-pressed', 'false')
    await waitFor(() => expect(names()).toEqual(['third.example']))
  })

  it('searches and sorts the resources the server sends whole, here', async () => {
    localStorage.setItem('ucm-ops-resource-type', 'users')
    open()
    await waitFor(() => expect(names()).toEqual(['zoe', 'alice']))
    fireEvent.click(screen.getByRole('button', { name: 'common.user' }))
    expect(names()).toEqual(['alice', 'zoe'])
    fireEvent.click(screen.getByRole('button', { name: 'common.user' }))
    expect(names()).toEqual(['zoe', 'alice'])
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ali' } })
    expect(names()).toEqual(['alice'])
  })
})
