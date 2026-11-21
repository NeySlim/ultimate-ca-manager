/**
 * ACME history tab: paged by the server, and its export walks every page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { acmeService } from '../../services/acme.service'

const exported = vi.hoisted(() => ({ csv: vi.fn() }))
vi.mock('../../lib/utils', async () => {
  const actual = await vi.importActual('../../lib/utils')
  return { ...actual, exportToCSV: exported.csv }
})

import ACMEPage from '../ACMEPage'

const TOTAL = 130
const row = (id) => ({
  id, common_name: `h${id}.example.com`, serial: String(id), issuer: 'Hist CA', source: 'acme',
  status: 'valid', revoked: false, created_at: '2026-01-01T00:00:00Z', valid_to: '2030-01-01T00:00:00Z', order: {},
})
const pageOf = ({ page, per_page }) => ({
  data: Array.from({ length: Math.max(0, Math.min(per_page, TOTAL - (page - 1) * per_page)) },
    (_, i) => row((page - 1) * per_page + i + 1)),
  meta: { total: TOTAL, cas: ['Hist CA'] },
})
const ok = (data) => vi.fn().mockResolvedValue({ data })

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  Object.assign(acmeService, {
    getSettings: ok({}), getHistory: vi.fn(async (p) => pageOf(p)), getClientSettings: ok({}),
    getDnsProviders: ok([]), getDnsProviderTypes: ok([]), getDomains: ok([]), getLocalDomains: ok([]),
    getEabRequired: ok({ eab_required: false }), getCaAccounts: ok([]),
    getClientOrders: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
  })
})

async function openHistory() {
  render(<MemoryRouter initialEntries={['/acme?tab=history']}><ACMEPage /></MemoryRouter>)
  await screen.findByText('h1.example.com')
}

describe('ACME history tab', () => {
  it('asks the server for one page and shows its total', async () => {
    await openHistory()
    expect(acmeService.getHistory.mock.calls.at(-1)[0]).toMatchObject({ page: 1, per_page: 25 })
    expect(screen.queryByText('h26.example.com')).toBeNull()
  })

  it('exports every page of the list', async () => {
    await openHistory()
    acmeService.getHistory.mockClear()
    fireEvent.click(await screen.findByRole('button', { name: 'table.exportData' }))
    fireEvent.click(await screen.findByRole('button', { name: 'table.exportCSV' }))
    await waitFor(() => expect(exported.csv).toHaveBeenCalled())
    expect(exported.csv.mock.calls[0][0]).toHaveLength(TOTAL)
  })

  it('keeps the answer of the last search when an older one arrives later', async () => {
    await openHistory()
    const pending = {}
    acmeService.getHistory.mockImplementation((p) => new Promise((resolve) => { pending[p.search] = resolve }))
    const reply = (id) => ({ data: [row(id)], meta: { total: 1, cas: [] } })
    const box = screen.getByPlaceholderText('common.searchCertificates')
    fireEvent.change(box, { target: { value: 'ab' } })
    await waitFor(() => expect(pending.ab).toBeTruthy())
    fireEvent.change(box, { target: { value: 'abc' } })
    await waitFor(() => expect(pending.abc).toBeTruthy())
    pending.abc(reply(51))
    await screen.findByText('h51.example.com')
    pending.ab(reply(26))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('h26.example.com')).toBeNull()
  })
})
