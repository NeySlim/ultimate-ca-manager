/**
 * The orders tab under a rate limit: a page that keeps answering 429 leaves a partial list with a notice.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { acmeService } from '../../services/acme.service'
import ACMEPage from '../ACMEPage'

const TOTAL = 150
const order = (id) => ({ id, primary_domain: `o${id}.example.com`, status: 'valid', environment: 'production' })
const pageOf = ({ page, per_page }) => ({
  data: Array.from({ length: Math.max(0, Math.min(per_page, TOTAL - (page - 1) * per_page)) },
    (_, i) => order((page - 1) * per_page + i + 1)),
  meta: { total: TOTAL },
})
const rateLimited = () => Object.assign(new Error('Too many requests'), { status: 429, retryAfter: 0 })
const ok = (data) => vi.fn().mockResolvedValue({ data })

function mockAcme(getClientOrders) {
  Object.assign(acmeService, {
    getSettings: ok({}), getHistory: ok([]), getClientSettings: ok({}), getDnsProviders: ok([]),
    getDnsProviderTypes: ok([]), getDomains: ok([]), getLocalDomains: ok([]),
    getEabRequired: ok({ eab_required: false }), getCaAccounts: ok([]),
    getClientOrders: vi.fn((_s, _e, page) => getClientOrders(page)),
  })
}

async function openOrdersTab() {
  render(<MemoryRouter initialEntries={['/acme']}><ACMEPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText('acme.letsEncryptOrders'))[0])
}

describe('ACMEPage orders under a rate limit', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows the pages obtained and says the list is partial', async () => {
    mockAcme((page) => (page.page === 2 ? Promise.reject(rateLimited()) : Promise.resolve(pageOf(page))))
    await openOrdersTab()
    expect(await screen.findByText('o1.example.com')).toBeInTheDocument()
    expect(screen.queryByText('o101.example.com')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('acme.ordersListPartial')
    expect(acmeService.getClientOrders.mock.calls.filter(([, , p]) => p.page === 2)).toHaveLength(3)
  })

  it('shows the whole list once a retried page answers', async () => {
    let refused = false
    mockAcme((page) => {
      if (page.page === 2 && !refused) { refused = true; return Promise.reject(rateLimited()) }
      return Promise.resolve(pageOf(page))
    })
    await openOrdersTab()
    expect(await screen.findByText('o150.example.com')).toBeInTheDocument()
    expect(screen.getByText('o1.example.com')).toBeInTheDocument()
    expect(screen.queryByText('acme.ordersListPartial')).toBeNull()
  })
})
