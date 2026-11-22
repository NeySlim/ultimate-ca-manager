/**
 * The columns of the ACME accounts and history (COLONNES-SPEC T1, T2, T4, T9, L7): the name takes the room left, one
 * column sorted from the first render, the sort in the address; the accounts read every page of the server before
 * sorting in memory, the history is sorted by the server and shown in its order.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'
import { acmeService } from '../../services/acme.service'
import { renderAtUrl } from '../../test/dockUrl'
import { absorbers, headersOf, rowNames, sortedHeaders, sortKeys } from '../../test/listContract'

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ hasPermission: () => true, canRead: () => true, canWrite: () => true, canDelete: () => true, isAdmin: () => true }),
}))

import ACMEPage from '../ACMEPage'

const ok = (data) => vi.fn().mockResolvedValue({ data })
const account = (i, extra = {}) => ({
  id: i, account_id: `k${String(i).padStart(3, '0')}-account-id`, contact: [`mailto:a${i}@example.com`], status: 'valid', orders_count: i % 7,
  created_at: new Date(Date.UTC(2026, 0, 1) + i * 3600e3).toISOString(), ...extra,
})
// 150 accounts on two pages of 100, as the server gives them (its own order: oldest first)
const ACCOUNTS = Array.from({ length: 150 }, (_, i) => account(i + 1))
const accountsPage = vi.fn(async ({ page = 1, per_page = 100 } = {}) => ({
  data: ACCOUNTS.slice((page - 1) * per_page, page * per_page), meta: { total: ACCOUNTS.length, page, per_page },
}))
const cert = (id, extra = {}) => ({
  id, common_name: `h${id}.example.com`, serial: String(id), issuer: 'Hist CA', source: 'acme', revoked: false,
  created_at: '2026-01-01T00:00:00Z', valid_to: '2030-01-01T00:00:00Z', order: {}, ...extra,
})

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  Object.assign(acmeService, {
    getSettings: ok({}), getClientSettings: ok({}), getDnsProviders: ok([]), getDnsProviderTypes: ok([]), getDomains: ok([]),
    getLocalDomains: ok([]), getEabRequired: ok({ eab_required: false }), getCaAccounts: ok([]),
    getClientOrders: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    getHistory: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    getAccounts: accountsPage, getAccountById: vi.fn(async (id) => ({ data: ACCOUNTS.find((a) => a.id === id) })),
    getOrders: ok([]), getChallenges: ok([]),
  })
})

describe('the ACME accounts list', () => {
  it('reads every page, opens on the newest account, the name taking the room left', async () => {
    const at = renderAtUrl(<ACMEPage />, '/acme')
    await screen.findByRole('button', { name: 'acct/k150-account' })
    // Both pages of the server, then the whole set sorted here: the newest (page two) first
    expect(accountsPage.mock.calls.map(([p]) => p.page).sort()).toEqual([1, 2])
    expect(rowNames(at.container)[0]).toBe('acct/k150-account')
    expect(sortedHeaders(at.container)).toEqual([['acme.createdOn', 'descending']])
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual(['name', 'contact', 'created', 'state', 'orders'])
    expect(headersOf(at.container).filter((h) => h.number).map((h) => h.label)).toEqual(['acme.columns.orders'])
    // The whole contact in its cell's title, wherever it is cut
    expect(at.container.querySelector('tbody tr td[title="a150@example.com"]')).not.toBeNull()
  })

  it('keeps its sort in the address and reads it back', async () => {
    const at = renderAtUrl(<ACMEPage />, '/acme')
    await screen.findByRole('button', { name: 'acct/k150-account' })
    fireEvent.click(screen.getByRole('button', { name: 'acme.contact' }))
    expect(at.where()).toBe('/acme?sort=contact&order=asc')
    expect(rowNames(at.container)[0]).toBe('acct/k001-account')
    // The default sort leaves the address bare
    fireEvent.click(screen.getByRole('button', { name: 'acme.createdOn' }))
    fireEvent.click(screen.getByRole('button', { name: 'acme.createdOn' }))
    expect(at.where()).toBe('/acme')
    at.unmount()
    const again = renderAtUrl(<ACMEPage />, '/acme?sort=orders&order=desc')
    await screen.findAllByRole('button', { name: /^acct\// })
    expect(sortedHeaders(again.container)).toEqual([['acme.columns.orders', 'descending']])
    again.unmount()
    // An unknown key falls back on the default without an error
    const odd = renderAtUrl(<ACMEPage />, '/acme?sort=nonsense&order=asc')
    await screen.findAllByRole('button', { name: /^acct\// })
    expect(sortedHeaders(odd.container)).toEqual([['acme.createdOn', 'descending']])
  })

  it('says the list is partial when a page cannot be read', async () => {
    acmeService.getAccounts = vi.fn(async (p) => (p.page === 2 ? Promise.reject(new Error('gone')) : accountsPage(p)))
    renderAtUrl(<ACMEPage />, '/acme')
    expect(await screen.findByText('acme.accountsListPartial')).toBeInTheDocument()
  })
})

describe('the ACME history list', () => {
  it('asks the server for the latest issued first and shows its order as given', async () => {
    // The server's order, deliberately not the one a sort here would give
    acmeService.getHistory = vi.fn().mockResolvedValue({ data: [cert(2, { common_name: 'b.example.com' }), cert(1, { common_name: 'a.example.com' }), cert(3, { common_name: 'c.example.com' })], meta: { total: 3 } })
    const at = renderAtUrl(<ACMEPage />, '/acme?tab=history')
    await screen.findByRole('button', { name: 'b.example.com' })
    expect(acmeService.getHistory.mock.calls.at(-1)[0]).toMatchObject({ page: 1, sort_by: 'created_at', sort_order: 'desc' })
    expect(sortedHeaders(at.container)).toEqual([['common.issued', 'descending']])
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual(['common_name', 'source', 'valid_to', 'created_at', 'status'])
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    await waitFor(() => expect(acmeService.getHistory.mock.calls.at(-1)[0]).toMatchObject({ page: 1, sort_by: 'common_name', sort_order: 'asc' }))
    expect(at.where()).toBe('/acme?tab=history&sort=common_name&order=asc')
    // The rows stay in the server's order: nothing is sorted again here
    expect(rowNames(at.container)).toEqual(['b.example.com', 'a.example.com', 'c.example.com'])
  })

  it('goes back to page one on a sort, and opens on a sort from the address', async () => {
    acmeService.getHistory = vi.fn(async ({ page }) => ({ data: [cert(page * 100)], meta: { total: 130 } }))
    const at = renderAtUrl(<ACMEPage />, '/acme?tab=history&sort=status&order=asc')
    await screen.findByRole('button', { name: 'h100.example.com' })
    expect(acmeService.getHistory.mock.calls.at(-1)[0]).toMatchObject({ sort_by: 'status', sort_order: 'asc' })
    expect(sortedHeaders(at.container)).toEqual([['atelier.state', 'ascending']])
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await screen.findByRole('button', { name: 'h200.example.com' })
    fireEvent.click(screen.getByRole('button', { name: 'common.expires' }))
    await waitFor(() => expect(acmeService.getHistory.mock.calls.at(-1)[0]).toMatchObject({ page: 1, sort_by: 'valid_to', sort_order: 'asc' }))
    // A change of view drops the sort of the one left (T9)
    fireEvent.click(screen.getByRole('tab', { name: /^acme\.views\.accounts/ }))
    expect(at.where()).toBe('/acme')
  })
})
