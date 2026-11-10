/**
 * Behaviours the design mock-up proves by mutation, applied to the overview cards:
 * queue ceiling, folded total, exact links, empty state distinct from the error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k, o) => (o?.defaultValue ?? k) }) }))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getHealth: vi.fn(), getCompliance: vi.fn(), getIssuance: vi.fn(),
  getStats: vi.fn(), getAll: vi.fn(), getNext: vi.fn(), getActivity: vi.fn(), can: vi.fn(),
}))
vi.mock('../../../services', () => ({
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getCompliance: api.getCompliance, getIssuance: api.getIssuance },
  certificatesService: { getStats: api.getStats },
  casService: { getAll: api.getAll },
  dashboardService: { getNextExpirations: api.getNext, getActivityLog: api.getActivity },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: api.can }) }))

import { QueueCard, HierarchyCard, HorizonCard, ActivityCard, ComplianceCard, HealthCard } from '..'

const show = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const item = (i) => ({ kind: 'manual_renewal_due', tier: 'warning', id: i, label: `cert-${i}`, due_at: null, href_hint: `/certificates/${i}` })
const queue = (n, total = n) => ({ data: { items: Array.from({ length: n }, (_, i) => item(i + 1)), counts: { manual_renewal_due: total }, total } })

beforeEach(() => {
  vi.clearAllMocks()
  api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
  api.getNext.mockResolvedValue({ data: [] })
  api.can.mockReturnValue(true)
})

describe('queue ceiling and folded total', () => {
  it('shows 6 of 9 rows, then the 3 others on request', async () => {
    api.getQueue.mockResolvedValue(queue(9))
    show(<QueueCard />)
    await screen.findByText('cert-1')
    expect(screen.getAllByText(/^cert-\d$/)).toHaveLength(6)
    fireEvent.click(screen.getByText('overview.queue.unfold'))
    expect(screen.getAllByText(/^cert-\d$/)).toHaveLength(9)
    fireEvent.click(screen.getByText('overview.queue.fold'))
    expect(screen.getAllByText(/^cert-\d$/)).toHaveLength(6)
  })

  it('the total counts the whole queue, not the rows shown', async () => {
    api.getQueue.mockResolvedValue(queue(100, 140))
    show(<QueueCard />)
    await screen.findByText('cert-1')
    expect(screen.getByTestId('queue-total').textContent).toBe('140')
    expect(screen.getByLabelText('overview.queue.perKind').textContent).toContain('140')
  })

  it('the fold state starts from the stored preference', async () => {
    api.getQueue.mockResolvedValue(queue(9))
    show(<QueueCard defaultOpen />)
    await screen.findByText('cert-9')
    expect(screen.getAllByText(/^cert-\d$/)).toHaveLength(9)
  })
})

describe('exact links', () => {
  it('hierarchy nests a CA under its parent and links each to its own page', async () => {
    api.getAll.mockResolvedValue({ data: [
      { id: 1, refid: 'a', descr: 'Root', parent_id: null },
      { id: 2, refid: 'b', descr: 'Issuing', parent_id: 1 },
      { id: 3, refid: 'c', descr: 'Orphan', parent_id: 99 },
    ], meta: { total: 3 } })
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'b', issued: 4 }] } })
    show(<HierarchyCard />)
    const root = (await screen.findByText('Root')).closest('a')
    const child = screen.getByText('Issuing').closest('a')
    expect(root.getAttribute('href')).toBe('/cas/1')
    expect(child.getAttribute('href')).toBe('/cas/2')
    expect(root.closest('li').querySelector('ul').contains(child)).toBe(true)
    expect(screen.getByText('Orphan').closest('ul').parentElement.tagName).toBe('SECTION')
    expect(child.textContent).toContain('overview.hierarchy.issued7d 4')
    expect(root.textContent).toContain('overview.hierarchy.issued7d 0')
  })

  it('horizon counters open the list of their own status, each soonest row its certificate', async () => {
    api.getStats.mockResolvedValue({ data: { total: 9, expiring: 3, expired: 1 } })
    api.getNext.mockResolvedValue({ data: [{ id: 7, common_name: 'soon.example', valid_to: '2027-01-01T00:00:00Z' }] })
    show(<HorizonCard />)
    expect((await screen.findByText('overview.horizon.expiring')).closest('a').getAttribute('href')).toBe('/certificates?status=expiring')
    expect(screen.getByText('overview.horizon.expired').closest('a').getAttribute('href')).toBe('/certificates?status=expired')
    expect(screen.getByText('soon.example').closest('a').getAttribute('href')).toBe('/certificates/7')
  })

  it('the whole trail is linked only with the audit permission', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [{ message: 'Created x', user: 'u', timestamp: null }] } })
    api.can.mockReturnValue(true)
    const a = show(<ActivityCard />)
    expect((await screen.findByText('overview.activity.all')).getAttribute('href')).toBe('/audit')
    a.unmount()
    api.can.mockReturnValue(false)
    show(<ActivityCard />)
    await screen.findByText('Created x')
    expect(screen.queryByText('overview.activity.all')).toBeNull()
  })
})

describe('empty state is not the error state', () => {
  const cards = [
    ['queue', QueueCard, api.getQueue, { items: [], counts: {}, total: 0 }],
    ['health', HealthCard, api.getHealth, { protocols: {} }],
    ['hierarchy', HierarchyCard, api.getAll, []],
    ['horizon', HorizonCard, api.getStats, { total: 0 }],
    ['compliance', ComplianceCard, api.getCompliance, { total: 0, counters: {}, by_key_algorithm: [] }],
    ['activity', ActivityCard, api.getActivity, { activity: [] }],
  ]
  it.each(cards)('%s says "nothing" for an empty answer and offers a retry for a failure, never both', async (id, Card, fetcher, empty) => {
    fetcher.mockResolvedValueOnce({ data: empty, meta: { total: 0 } })
    const a = show(<Card />)
    await screen.findByText('overview.state.empty')
    expect(screen.queryByRole('alert')).toBeNull()
    a.unmount()

    fetcher.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 500 }))
    show(<Card />)
    await screen.findByRole('alert')
    expect(screen.queryByText('overview.state.empty')).toBeNull()
    await waitFor(() => expect(screen.getByText('overview.state.retry')).toBeTruthy())
  })

  it('hierarchy fails as a whole when its issuance half fails', async () => {
    api.getAll.mockResolvedValue({ data: [{ id: 1, refid: 'a', descr: 'Root' }], meta: { total: 1 } })
    api.getIssuance.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }))
    show(<HierarchyCard />)
    await screen.findByRole('alert')
    expect(screen.queryByText('Root')).toBeNull()
  })
})
