/** The history is asked once when the page opens, not once per render that changes a filter's identity. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { acmeService } from '../../services/acme.service'
import ACMEPage from '../ACMEPage'

const ok = (data) => vi.fn().mockResolvedValue({ data })

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  Object.assign(acmeService, {
    getSettings: ok({}), getClientSettings: ok({}), getDnsProviders: ok([]), getDnsProviderTypes: ok([]),
    getDomains: ok([]), getLocalDomains: ok([]), getEabRequired: ok({ eab_required: false }), getCaAccounts: ok([]),
    getHistory: vi.fn().mockResolvedValue({ data: [], meta: { total: 0, cas: [] } }),
    getClientOrders: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
  })
})

describe('ACME page history requests', () => {
  it.each(['/acme', '/acme?tab=history'])('asks acme/history once on opening %s', async (entry) => {
    render(<MemoryRouter initialEntries={[entry]}><ACMEPage /></MemoryRouter>)
    await screen.findAllByRole('button')
    await new Promise((r) => setTimeout(r, 100))
    const asked = acmeService.getHistory.mock.calls.map(([p]) => JSON.stringify(p))
    expect(asked, asked.join(" | ")).toHaveLength(1)
  })
})
