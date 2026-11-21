/**
 * The SCEP requests tab is paged and filtered by the server: the page asks for
 * one page at a time, with the typed search and the chosen status.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { scepService } from '../../services/scep.service'
import { casService } from '../../services/cas.service'
import SCEPPage from '../SCEPPage'

const TOTAL = 80
const row = (id) => ({ id, transaction_id: `tx${id}`, subject: `CN=dev${id}`, status: 'pending', created_at: '2026-01-01T00:00:00Z' })
const pageOf = ({ page = 1, per_page = 50 } = {}) => ({
  data: Array.from({ length: Math.max(0, Math.min(per_page, TOTAL - (page - 1) * per_page)) },
    (_, i) => row((page - 1) * per_page + i + 1)),
  meta: { total: TOTAL, page, per_page },
})

beforeEach(() => {
  Object.assign(scepService, {
    getConfig: vi.fn().mockResolvedValue({ data: {} }),
    getRequests: vi.fn(async (p) => pageOf(p)),
    getStats: vi.fn().mockResolvedValue({ data: { pending: 80, approved: 0, rejected: 0, total: 80 } }),
    getProfiles: vi.fn().mockResolvedValue({ data: [] }),
    getChallenge: vi.fn().mockResolvedValue({ data: {} }),
  })
  casService.getAll.mockResolvedValue({ data: [] })
})

describe('SCEPPage requests paging', () => {
  it('asks the server for one page, not the first fifty', async () => {
    render(<MemoryRouter initialEntries={['/scep']}><SCEPPage /></MemoryRouter>)
    await screen.findAllByText('dev1')
    const params = scepService.getRequests.mock.calls.at(-1)[0]
    expect(params).toMatchObject({ page: 1, per_page: 25 })
    expect(screen.queryByText('dev26')).toBeNull()
  })

  it('sends the typed search to the server', async () => {
    render(<MemoryRouter initialEntries={['/scep']}><SCEPPage /></MemoryRouter>)
    await screen.findAllByText('dev1')
    fireEvent.change(screen.getByPlaceholderText('scep.searchRequests'), { target: { value: 'dev7' } })
    await waitFor(() => expect(scepService.getRequests.mock.calls.at(-1)[0]).toMatchObject({ search: 'dev7', page: 1 }))
  })

  it('keeps the answer of the last search when an older one arrives later', async () => {
    const pending = {}
    scepService.getRequests = vi.fn((p) => (p.search
      ? new Promise((resolve) => { pending[p.search] = resolve })
      : Promise.resolve(pageOf(p))))
    const reply = (name) => ({ data: [{ ...row(900), subject: `CN=${name}` }], meta: { total: 1 } })
    render(<MemoryRouter initialEntries={['/scep']}><SCEPPage /></MemoryRouter>)
    await screen.findAllByText('dev1')
    const box = screen.getByPlaceholderText('scep.searchRequests')
    fireEvent.change(box, { target: { value: 'ab' } })
    await waitFor(() => expect(pending.ab).toBeTruthy())
    fireEvent.change(box, { target: { value: 'abc' } })
    await waitFor(() => expect(pending.abc).toBeTruthy())
    pending.abc(reply('from-abc'))
    await screen.findAllByText('from-abc')
    pending.ab(reply('from-ab'))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('from-ab')).toBeNull()
    expect(screen.getAllByText('from-abc').length).toBeGreaterThan(0)
  })
})
