/**
 * KeyRecoveryPage with ?request=N: the linked request comes first, follows its decision,
 * and leaves the list when the status filter excludes its state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

// One translator and one notifier for every render: the page reloads when either changes
const stable = vi.hoisted(() => ({
  i18n: { t: (key) => key, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: { showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {} },
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: () => {} }),
  useInspector: () => ({ openEntity: () => {}, windows: [], prefs: {}, updatePrefs: () => {} }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({ canWrite: () => true, canRead: () => true, canDelete: () => true, hasPermission: () => true }),
}))
const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), approve: vi.fn(), reject: vi.fn(), recover: vi.fn() }))
vi.mock('../../services', () => ({ keyRecoveryService: api }))

import KeyRecoveryPage from '../KeyRecoveryPage'

const req = (id, status, cn) => ({ id, status, cert_cn: cn, reason: 'lost', requested_by: 'alice', requested_at: '2026-11-01T10:00:00Z' })
// The database: what the list and the detail read
let rows
const renderPage = () => render(<MemoryRouter initialEntries={['/key-recovery?request=900']}><KeyRecoveryPage /></MemoryRouter>)
const cards = () => screen.getAllByText(/^cn-/).map((el) => el.textContent)
const filter = (name) => screen.getByRole('button', { name })
const linkedCard = () => document.querySelector('[aria-current="true"]')

beforeEach(() => {
  vi.clearAllMocks()
  rows = [req(1, 'pending', 'cn-one'), req(2, 'approved', 'cn-two'), req(900, 'pending', 'cn-linked')]
  // The list stops before the linked request, as past the 500 it holds
  api.list.mockImplementation(async (status) => ({ data: { requests: rows.filter((r) => r.id !== 900 && (!status || r.status === status)).map((r) => ({ ...r })), dual_control: true } }))
  api.get.mockImplementation(async (id) => ({ data: { ...rows.find((r) => String(r.id) === String(id)) } }))
  api.approve.mockImplementation(async (id) => { rows.find((r) => r.id === id).status = 'approved'; return {} })
})

describe('KeyRecoveryPage linked request', () => {
  it('shows the linked request first', async () => {
    // Listed this time, last: it still comes first
    api.list.mockImplementation(async () => ({ data: { requests: rows.map((r) => ({ ...r })), dual_control: true } }))
    renderPage()
    await waitFor(() => expect(linkedCard()).toBeTruthy())
    expect(within(linkedCard()).getByText('cn-linked')).toBeTruthy()
    expect(cards()).toEqual(['cn-linked', 'cn-one', 'cn-two'])
  })

  it('the listed copy of the linked request wins over the copy read on opening', async () => {
    api.list.mockImplementation(async (status) => ({ data: { requests: rows.filter((r) => !status || r.status === status).map((r) => ({ ...r })), dual_control: true } }))
    renderPage()
    await waitFor(() => expect(linkedCard()).toBeTruthy())
    rows[2].status = 'approved'
    fireEvent.click(filter('keyRecovery.status.approved'))
    await waitFor(() => expect(cards()).toEqual(['cn-linked', 'cn-two']))
    expect(within(linkedCard()).getByText('keyRecovery.status.approved')).toBeTruthy()
  })

  it('a linked request outside the list is shown first', async () => {
    renderPage()
    await waitFor(() => expect(linkedCard()).toBeTruthy())
    expect(cards()).toEqual(['cn-linked', 'cn-one', 'cn-two'])
  })

  it('no decision buttons are left once the linked request is approved', async () => {
    renderPage()
    await waitFor(() => expect(linkedCard()).toBeTruthy())
    fireEvent.click(filter('keyRecovery.status.pending'))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith('pending'))
    await waitFor(() => expect(cards()).toEqual(['cn-linked', 'cn-one']))
    fireEvent.click(within(linkedCard()).getByText('keyRecovery.approve'))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith(900))
    // Approved, it no longer matches the pending filter: neither shown nor offering its buttons
    await waitFor(() => expect(cards()).toEqual(['cn-one']))
    expect(screen.getAllByText('keyRecovery.approve')).toHaveLength(1)
    fireEvent.click(filter('common.all'))
    await waitFor(() => expect(cards()[0]).toBe('cn-linked'))
    expect(within(linkedCard()).queryByText('keyRecovery.approve')).toBeNull()
    expect(within(linkedCard()).getByText('keyRecovery.status.approved')).toBeTruthy()
  })

  it('the status filter removes a linked request in another state', async () => {
    renderPage()
    await waitFor(() => expect(cards()[0]).toBe('cn-linked'))
    fireEvent.click(filter('keyRecovery.status.approved'))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith('approved'))
    await waitFor(() => expect(cards()).toEqual(['cn-two']))
    expect(linkedCard()).toBeNull()
  })
})
