/**
 * The bulk list of Operations in the Atelier table: ticked records from every page, the
 * Selection view that shows them alone (the former basket), the local search and paging of the
 * resources the server sends whole, and the sort of the shown rows.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.ids ? `${key} ${opts.ids}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({ bulkDelete: vi.fn(), showWarning: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn(), certCalls: [] }))

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
  certificatesService: { getAll: (params) => mocks.certCalls.push(params) && Promise.resolve(params?.per_page === 1
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
import { csrsService } from '../../services'

const open = () => render(<MemoryRouter initialEntries={['/operations?tab=bulk']}><OperationsPage /></MemoryRouter>)
const names = () => [...document.querySelectorAll('#ops-scroll tbody tr')].map((tr) => tr.querySelector('td:nth-child(2)').textContent)

describe('OperationsPage bulk list', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('keeps the ticked records of every page and shows them alone in the Selection view', async () => {
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    open()
    await waitFor(() => expect(names()).toEqual(['first.example', 'second.example']))
    // The server pages the certificates: a page number to type, as the mockup's large lists
    expect(document.getElementById('page-jump')).not.toBeNull()
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
    // By name from the first view
    await waitFor(() => expect(names()).toEqual(['alice', 'zoe']))
    expect(document.getElementById('page-jump')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'common.user' }))
    expect(names()).toEqual(['zoe', 'alice'])
    fireEvent.click(screen.getByRole('button', { name: 'common.user' }))
    expect(names()).toEqual(['alice', 'zoe'])
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ali' } })
    expect(names()).toEqual(['alice'])
  })

  it('sorts the certificates and the CSRs by the server from the first page, the page shown as it came, the selection kept', async () => {
    mocks.certCalls.length = 0
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    const at = { search: '' }
    function Where() { at.search = useLocation().search; return null }
    render(<MemoryRouter initialEntries={['/operations?tab=bulk']}><OperationsPage /><Where /></MemoryRouter>)
    await waitFor(() => expect(names()).toEqual(['first.example', 'second.example']))
    const pages = () => mocks.certCalls.filter((p) => p.per_page !== 1)
    expect(pages().pop()).toMatchObject({ page: 1, sort_by: 'subject', sort_order: 'asc' })
    expect(screen.getByRole('columnheader', { name: 'common.commonName' })).toHaveAttribute('aria-sort', 'ascending')
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'table.selectRow' })[0])
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(names()).toEqual(['third.example']))
    // In memory the expired one would come first: the page is the server's, as it came
    fireEvent.click(screen.getByRole('button', { name: 'common.status' }))
    await waitFor(() => expect(pages().pop()).toMatchObject({ page: 1, sort_by: 'status', sort_order: 'asc' }))
    await waitFor(() => expect(names()).toEqual(['first.example', 'second.example']))
    expect(at.search).toBe('?tab=bulk&sort=status&order=asc')
    expect(screen.getByRole('group', { name: 'table.selection' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'table.fullExpires' }))
    fireEvent.click(screen.getByRole('button', { name: 'table.fullExpires' }))
    await waitFor(() => expect(pages().pop()).toMatchObject({ page: 1, sort_by: 'valid_to', sort_order: 'desc' }))
    // Another resource starts by its name again
    fireEvent.click(screen.getByRole('button', { name: /common\.csrsShort/ }))
    await waitFor(() => expect(csrsService.getAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, sort_by: 'cn', sort_order: 'asc' })))
    expect(at.search).toBe('?tab=bulk')
    // The CSR's subject is not a server key: its header does not sort
    expect(screen.getByRole('columnheader', { name: 'common.subject' }).querySelector('button')).toBeNull()
  })
})

