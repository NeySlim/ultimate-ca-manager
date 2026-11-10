import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
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

import { QueueCard, ComplianceCard, HealthCard, HierarchyCard, HorizonCard, ActivityCard } from '..'

const show = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const item = (i) => ({ kind: 'manual_renewal_due', tier: 'warning', id: i, label: `cert-${i}`, due_at: null, href_hint: `/certificates/${i}` })
const error = (status) => Object.assign(new Error('x'), { status })

beforeEach(() => {
  vi.clearAllMocks()
  api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
  api.getNext.mockResolvedValue({ data: [] })
  api.can.mockReturnValue(true)
})

describe('card states', () => {
  const cases = [
    ['queue', QueueCard, api.getQueue, { items: [], counts: {}, total: 0 }],
    ['compliance', ComplianceCard, api.getCompliance, { total: 0, counters: {}, by_key_algorithm: [] }],
    ['health', HealthCard, api.getHealth, { protocols: {} }],
    ['hierarchy', HierarchyCard, api.getAll, []],
    ['horizon', HorizonCard, api.getStats, { total: 0 }],
    ['activity', ActivityCard, api.getActivity, { activity: [] }],
  ]
  it.each(cases)('%s: loading, empty, error with retry, missing permission', async (id, Card, fetcher, empty) => {
    fetcher.mockReturnValueOnce(new Promise(() => {}))
    const { unmount } = show(<Card />)
    expect(screen.getByRole('status').textContent).toBe('overview.state.loading')
    unmount()

    fetcher.mockResolvedValueOnce({ data: empty, meta: { total: 0 } })
    show(<Card />)
    expect(await screen.findByText('overview.state.empty')).toBeTruthy()

    fetcher.mockRejectedValueOnce(error(500)).mockResolvedValueOnce({ data: empty, meta: { total: 0 } })
    show(<Card />)
    fireEvent.click(await screen.findByText('overview.state.retry'))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(4))

    fetcher.mockRejectedValueOnce(error(403))
    const { container } = show(<Card />)
    await waitFor(() => expect(container.textContent).toContain('overview.state.forbidden'))
  })
})

describe('queue card', () => {
  it('lists 6 rows, folds the totals per kind, and each row opens its href_hint', async () => {
    api.getQueue.mockResolvedValue({ data: {
      items: [1, 2, 3, 4, 5, 6, 7, 8].map(item), counts: { manual_renewal_due: 8, crl_due: 2 }, total: 10,
      filter_hints: { manual_renewal_due: { renewal: 'manual_renewal_due' } },
    } })
    show(<QueueCard />)
    await screen.findByText('cert-1')
    expect(screen.queryByText('cert-7')).toBeNull()
    expect(screen.getByText('cert-6').closest('a').getAttribute('href')).toBe('/certificates/6')
    expect(screen.getByTestId('queue-total').textContent).toBe('10')
    expect(screen.getByLabelText('overview.queue.perKind').textContent).toContain('2')
    const toList = screen.getAllByRole('link').find((a) => a.getAttribute('href') === '/certificates?renewal=manual_renewal_due')
    expect(toList).toBeTruthy()
    fireEvent.click(screen.getByText('overview.queue.unfold'))
    expect(screen.getByText('cert-8')).toBeTruthy()
  })
})

describe('compliance card', () => {
  const entry = (count, hint) => ({ count, filter_available: Boolean(hint), filter_hint: hint })
  it('links a counter to the list its hint names, and not one without a filter', async () => {
    api.getCompliance.mockResolvedValue({ data: {
      total: 5, by_key_algorithm: [{ key_algo: 'RSA 2048', count: 2, filter_available: true, filter_hint: { live: 'true', key_algo: 'RSA 2048' } }],
      counters: {
        rsa_below_3072: entry(2, { live: 'true', key_algo_prefix: 'RSA', key_bits_below: '3072' }),
        weak_signature_hash: entry(1, { live: 'true', sig_hash: ['sha1', 'md5'] }),
        no_private_key: entry(3, null),
      },
    } })
    show(<ComplianceCard />)
    const rsa = (await screen.findByText('overview.compliance.rsa_below_3072')).closest('a')
    expect(rsa.getAttribute('href')).toBe('/certificates?live=true&key_algo_prefix=RSA&key_bits_below=3072')
    expect(screen.getByText('overview.compliance.weak_signature_hash').closest('a').getAttribute('href'))
      .toBe('/certificates?live=true&sig_hash=sha1&sig_hash=md5')
    expect(screen.getByText('overview.compliance.no_private_key').closest('a')).toBeNull()
    expect(screen.getByText('RSA 2048').closest('a').getAttribute('href')).toBe('/certificates?live=true&key_algo=RSA+2048')
  })

  it('shows a dash, not zero, for a figure the response lacks', async () => {
    api.getCompliance.mockResolvedValue({ data: { total: 3, counters: { rsa_below_3072: {} }, by_key_algorithm: [] } })
    show(<ComplianceCard />)
    const row = (await screen.findByText('overview.compliance.rsa_below_3072')).parentElement
    expect(row.textContent).toContain('–')
    expect(row.textContent.replace('overview.compliance.rsa_below_3072', '')).toBe('–')
  })
})

describe('missing figures read as a dash on every card', () => {
  it('hierarchy, horizon', async () => {
    api.getIssuance.mockResolvedValue({ data: {} })
    api.getStats.mockResolvedValue({ data: { total: 4 } })
    api.getAll.mockResolvedValue({ data: [{ id: 1, refid: 'r', descr: 'Root' }], meta: {} })
    const a = show(<HierarchyCard />)
    expect((await screen.findByText('Root')).closest('a').textContent).toContain('overview.hierarchy.issued7d –')
    expect(a.container.querySelector('a[href="/cas"]').textContent).toBe('–')
    a.unmount()
    show(<HorizonCard />)
    expect((await screen.findByText('overview.horizon.expiring')).parentElement.textContent).toContain('–')
  })
})

describe('hierarchy card', () => {
  it('marks an offline CA and a cross-signed one, and no other', async () => {
    api.getAll.mockResolvedValue({ data: [
      { id: 1, refid: 'r', descr: 'Root', offline: true, offline_label: 'Offline', cross_certificate_count: 0 },
      { id: 2, refid: 's', descr: 'Sub', parent_id: 1, offline: false, offline_label: null, cross_certificate_count: 2 },
      { id: 3, refid: 't', descr: 'Plain', parent_id: 1, offline: false, cross_certificate_count: 0 },
    ], meta: { total: 3 } })
    show(<HierarchyCard />)
    const line = async (name) => (await screen.findByText(name)).closest('a').textContent
    expect(await line('Root')).toContain('overview.hierarchy.offline')
    expect(await line('Root')).not.toContain('overview.hierarchy.crossSigned')
    expect(await line('Sub')).toContain('overview.hierarchy.crossSigned')
    expect(await line('Sub')).not.toContain('overview.hierarchy.offline')
    expect(await line('Plain')).not.toMatch(/offline|crossSigned/)
  })
})
