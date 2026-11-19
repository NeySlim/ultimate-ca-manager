/** Figures strip: four figures from the routes the cards read, a dash for a figure no route gave. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o && Object.keys(o).length > 0 ? `${k}:${Object.values(o).join(',')}` : k) }),
}))
const api = vi.hoisted(() => ({ getDashStats: vi.fn(), getQueue: vi.fn(), getHealth: vi.fn() }))
vi.mock('../../../services', () => ({
  dashboardService: { getStats: api.getDashStats },
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { MetricStrip } from '..'

const days = (failed) => [{ date: 'a', ok: 9, failed: 7 }, { date: 'b', ok: 1, failed }]
const metric = (id) => screen.getByTestId(`metric-${id}`)
const value = (id) => metric(id).querySelector('.ov-metric-value')

beforeEach(() => {
  vi.clearAllMocks()
  api.getDashStats.mockResolvedValue({ data: { total_certificates: 282, total_cas: 139, pending_csrs: 2, ssh_certificates: 0, expired: 55, expiring_soon: 11 } })
  api.getQueue.mockResolvedValue({ data: { total: 20, counts: { manual_renewal_due: 16, ca_expiring: 4 }, items: [{ kind: 'ca_expiring', tier: 'critical', id: 1 }] } })
  api.getHealth.mockResolvedValue({ data: { protocols: { acme: { periods: days(2) }, scep: { periods: days(0) }, est: { periods: days(1) }, scheduler: { periods: null } } } })
})

describe('figures strip', () => {
  it('shows the four figures with their legend', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('certificates').textContent).toBe('282'))
    expect(metric('certificates').textContent).toContain('overview.metrics.cas:139 · overview.metrics.pending:2')
    expect(metric('certificates').textContent).not.toContain('overview.metrics.ssh')
    expect(value('queue').textContent).toBe('20')
    expect(metric('queue').textContent).toContain('overview.metrics.queueSub:17,3')
    expect(value('expired').textContent).toBe('55')
    expect(metric('expired').textContent).toContain('overview.metrics.expiringSoon:11')
    // Today only: the last day of each protocol series, the scheduler has none
    expect(value('failures').textContent).toBe('3')
  })

  it('a figure that is a subset opens its filtered list, the inventory its whole list', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('certificates').textContent).toBe('282'))
    expect(metric('certificates').getAttribute('href')).toBe('/certificates')
    expect(metric('expired').getAttribute('href')).toBe('/certificates?status=expired')
  })

  it('colours a figure only when it calls for attention, the legend saying what it is', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('queue').className).toContain('is-warn'))
    expect(value('failures').className).toContain('is-bad')
    expect(value('certificates').className).not.toMatch(/is-/)
    expect(metric('failures').textContent).toContain('overview.metrics.failures')
  })

  it('leads to the card of a figure when the page shows that card, and nowhere otherwise', async () => {
    const toQueue = vi.fn()
    render(<MemoryRouter><MetricStrip go={(id) => (id === 'queue' ? toQueue : null)} /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect(metric('queue').tagName).toBe('BUTTON')
    fireEvent.click(metric('queue'))
    expect(toQueue).toHaveBeenCalledTimes(1)
    expect(metric('failures').tagName).toBe('DIV')
  })

  it('a route that fails leaves a dash, not a zero, and no link', async () => {
    api.getDashStats.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }))
    api.getHealth.mockRejectedValue(Object.assign(new Error('x'), { status: 403 }))
    render(<MemoryRouter><MetricStrip go={() => () => {}} /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect(value('certificates').textContent).toBe('–')
    expect(metric('certificates').tagName).toBe('DIV')
    expect(value('expired').textContent).toBe('–')
    expect(value('failures').textContent).toBe('–')
    expect(metric('failures').tagName).toBe('DIV')
    expect(value('failures').className).not.toContain('is-bad')
  })

  it('nothing to handle is a plain zero', async () => {
    api.getQueue.mockResolvedValue({ data: { total: 0, counts: {}, items: [] } })
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('0'))
    expect(value('queue').className).not.toContain('is-warn')
  })
})
