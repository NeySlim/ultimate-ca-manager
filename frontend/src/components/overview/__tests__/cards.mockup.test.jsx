/**
 * Behaviours the design mock-up proves by mutation, applied to the overview cards:
 * queue ceiling, folded total, exact links, empty state distinct from the error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ Trans: ({ i18nKey }) => i18nKey, useTranslation: () => ({ t: (k, o) => (o?.defaultValue ?? k) }) }))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getHealth: vi.fn(), getCompliance: vi.fn(), getIssuance: vi.fn(),
  getStats: vi.fn(), getAll: vi.fn(), getActivity: vi.fn(), can: vi.fn(),
  getExpirations: vi.fn(), getRevocation: vi.fn(), getCertList: vi.fn(),
}))
vi.mock('../../../services', () => ({
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getCompliance: api.getCompliance, getIssuance: api.getIssuance,
    getExpirations: api.getExpirations, getRevocation: api.getRevocation,
    expirationQuery: (hint, from, to) => ({ status: hint.status, expires_from: from, expires_to: `${to}+1` }) },
  certificatesService: { getStats: api.getStats, getAll: api.getCertList },
  casService: { getAll: api.getAll },
  dashboardService: { getActivityLog: api.getActivity },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: api.can }) }))

import { QueueCard, HierarchyCard, HorizonCard, ActivityCard, ComplianceCard, HealthCard, IssuanceCard, RevocationCard } from '..'

const show = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const item = (i) => ({ kind: 'manual_renewal_due', tier: 'warning', id: i, label: `cert-${i}`, due_at: null, href_hint: `/certificates/${i}` })
// A row folded by the mockup carries hidden: it stays in the list, out of sight
const visibleNames = () => [...document.querySelectorAll('#queue-list li.queue-row')].filter((li) => !li.hidden).map((li) => li.querySelector('strong, .queue-subject').textContent)
const queue = (n, total = n) => ({ data: { items: Array.from({ length: n }, (_, i) => item(i + 1)), counts: { manual_renewal_due: total }, total } })

beforeEach(() => {
  vi.clearAllMocks()
  api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
  api.getCertList.mockResolvedValue({ data: [{ id: 7, common_name: 'soon.example', source: 'acme' }] })
  api.can.mockReturnValue(true)
})

describe('queue ceiling and folded total', () => {
  it('shows 6 of 9 rows, then the 3 others on request', async () => {
    api.getQueue.mockResolvedValue(queue(9))
    show(<QueueCard />)
    await screen.findByText('cert-1')
    expect(visibleNames()).toHaveLength(6)
    fireEvent.click(screen.getByText('overview.queue.unfold'))
    expect(visibleNames()).toHaveLength(9)
    fireEvent.click(screen.getByText('overview.queue.less'))
    expect(visibleNames()).toHaveLength(6)
  })

  it('the total counts the whole queue, not the rows shown', async () => {
    api.getQueue.mockResolvedValue(queue(100, 140))
    show(<QueueCard />)
    await screen.findByText('cert-1')
    expect(document.querySelector('#card-queue-title .counter').textContent).toBe('140')
    expect(screen.getByText('overview.queue.group.renew').closest('button').textContent).toContain('140')
    expect(screen.getByText('overview.queue.partial')).toBeTruthy()
  })

  it('the fold state starts from the stored preference', async () => {
    api.getQueue.mockResolvedValue(queue(9))
    show(<QueueCard defaultOpen />)
    await screen.findByText('cert-9')
    expect(visibleNames()).toHaveLength(9)
  })
})

describe('exact links', () => {
  it('hierarchy nests a CA under its parent and links each to its own page', async () => {
    api.getAll.mockResolvedValue({ data: [
      { id: 1, refid: 'a', descr: 'Root', parent_id: null },
      { id: 2, refid: 'b', descr: 'Issuing', parent_id: 1 },
      { id: 3, refid: 'c', descr: 'Orphan', parent_id: 99 },
    ], meta: { total: 3 } })
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'b', issued: 4, total: 4 }] } })
    show(<HierarchyCard />)
    const root = (await screen.findByText('Root')).closest('a')
    const child = screen.getByText('Issuing').closest('a')
    expect(root.getAttribute('href')).toBe('/cas/1')
    expect(child.getAttribute('href')).toBe('/cas/2')
    expect(root.closest('li').querySelector('ul').contains(child)).toBe(true)
    // A CA whose parent is not in the list heads its own tree
    expect(screen.getByText('Orphan').closest('li').parentElement.closest('li')).toBeNull()
    expect(child.textContent).toContain('overview.hierarchy.issued')
    // A root gives its CRL and its state, not issuances
    expect(root.textContent).not.toContain('overview.hierarchy.issued')
  })

  it('the horizon opens the list of the day picked on its filter hint, each row its certificate', async () => {
    api.getExpirations.mockResolvedValue({ data: { from: '2026-11-23', total: 3, filter_hint: { status: ['valid', 'expiring'] },
      periods: [{ date: '2026-11-23', total: 0 }, { date: '2026-11-24', total: 3, manual: 3, automatic: 0 }] } })
    show(<HorizonCard />)
    expect((await screen.findByText('soon.example')).closest('a').getAttribute('href')).toBe('/certificates/7')
    expect(screen.getByText('overview.horizon.open').closest('a').getAttribute('href'))
      .toBe('/certificates?status=valid&status=expiring&expires_from=2026-11-24&expires_to=2026-11-24%2B1')
  })

  it('the whole trail is linked only with the audit permission', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [{ message: 'Created x', user: 'u', timestamp: null }] } })
    api.can.mockReturnValue(true)
    const a = show(<ActivityCard />)
    expect((await screen.findByText('overview.activity.all')).closest('a').getAttribute('href')).toBe('/audit')
    a.unmount()
    api.can.mockReturnValue(false)
    show(<ActivityCard />)
    await screen.findByText('Created x')
    expect(screen.queryByText('overview.activity.all')).toBeNull()
  })
})

describe('empty state is not the error state', () => {
  const cards = [
    ['queue', QueueCard, api.getQueue, { items: [], counts: {}, total: 0 }, 'overview.queue.emptyTitle'],
    ['health', HealthCard, api.getHealth, { protocols: {} }, 'overview.state.empty'],
    ['hierarchy', HierarchyCard, api.getAll, [], 'overview.hierarchy.emptyTitle'],
    ['horizon', HorizonCard, api.getExpirations, { from: '2026-11-23', total: 0, periods: [{ date: '2026-11-23', total: 0 }] }, 'overview.horizon.quiet'],
    ['compliance', ComplianceCard, api.getCompliance, { total: 0, counters: {}, by_key_algorithm: [] }, 'overview.state.empty'],
    ['activity', ActivityCard, api.getActivity, { activity: [] }, 'overview.state.empty'],
    ['issuance', IssuanceCard, api.getIssuance, { flow: { periods: [], previous: { total: 0 } } }, 'overview.flow.quiet'],
    ['revocation', RevocationCard, api.getRevocation, { total: 0, items: [] }, 'overview.state.empty'],
  ]
  it.each(cards)('%s says "nothing" for an empty answer and offers a retry for a failure, never both', async (id, Card, fetcher, empty, emptyText) => {
    fetcher.mockResolvedValueOnce({ data: empty, meta: { total: 0 } })
    const a = show(<Card />)
    await screen.findByText(emptyText)
    expect(screen.queryByRole('alert')).toBeNull()
    a.unmount()

    fetcher.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 500 }))
    show(<Card />)
    await screen.findByRole('alert')
    expect(screen.queryByText(emptyText)).toBeNull()
    await waitFor(() => expect(screen.getByText('table.retry')).toBeTruthy())
  })

  it('hierarchy keeps its tree, flagged partial, when its issuance half fails', async () => {
    api.getAll.mockResolvedValue({ data: [{ id: 1, refid: 'a', descr: 'Root' }], meta: { total: 1 } })
    api.getIssuance.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }))
    show(<HierarchyCard />)
    expect(await screen.findByText('Root')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('note')).toBeTruthy()
  })
})
