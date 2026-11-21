/** Figures strip, the mockup's metric-strip: four figures from the routes the cards read, a dash for a figure no route gave. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
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
const metric = (id) => document.querySelector(`[data-metric="${id}"]`)
const value = (id) => metric(id).querySelector('.value')

beforeEach(() => {
  vi.clearAllMocks()
  api.getDashStats.mockResolvedValue({ data: { total_certificates: 282, total_cas: 139, pending_csrs: 2, ssh_certificates: 0, expired: 55, expiring_soon: 11 } })
  api.getQueue.mockResolvedValue({ data: { total: 20, counts: { manual_renewal_due: 16, ca_expiring: 4 }, items: [{ kind: 'ca_expiring', tier: 'critical', id: 1 }] } })
  api.getHealth.mockResolvedValue({ data: { protocols: { acme: { periods: days(2) }, scep: { periods: days(0) }, est: { periods: days(1) }, scheduler: { periods: null } } } })
})

describe('figures strip', () => {
  it('shows the four figures with the mockup legend', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('certificates').textContent).toBe('282'))
    expect([...document.querySelector('.metric-strip').children].map((m) => m.dataset.metric)).toEqual(['certificates', 'queue', 'expired', 'failures'])
    expect(metric('certificates').querySelector('small').textContent).toBe('overview.metrics.inventory')
    expect(value('queue').textContent).toBe('20')
    expect(metric('queue').querySelector('small').textContent).toBe('overview.metrics.queueSub:overview.metrics.interventions:17,3')
    expect(value('expired').textContent).toBe('55')
    expect(metric('expired').querySelector('small').textContent).toBe('overview.metrics.toCheck')
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
    await waitFor(() => expect(value('queue').className).toBe('value warn'))
    expect(value('failures').className).toBe('value bad')
    expect(value('certificates').className).toBe('value')
    expect(metric('failures').querySelector('.label').textContent).toBe('overview.metrics.failures')
  })

  it('the queue figure shows the whole queue, the failures figure leads to the health card', async () => {
    const showQueue = vi.fn()
    const toHealth = vi.fn()
    render(<MemoryRouter><MetricStrip showQueue={showQueue} go={(id) => (id === 'health' ? toHealth : null)} /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect(metric('queue').getAttribute('href')).toBe('#card-queue')
    fireEvent.click(metric('queue'))
    expect(showQueue).toHaveBeenCalledWith('')
    await waitFor(() => expect(value('failures').textContent).toBe('3'))
    expect(metric('failures').getAttribute('href')).toBe('#card-health')
    fireEvent.click(metric('failures'))
    expect(toHealth).toHaveBeenCalledTimes(1)
  })

  it('the failures figure leads nowhere when the health card is not on the page', async () => {
    render(<MemoryRouter><MetricStrip go={() => null} /></MemoryRouter>)
    await waitFor(() => expect(value('failures').textContent).toBe('3'))
    expect(metric('failures').hasAttribute('href')).toBe(false)
  })

  it('a route that fails leaves a dash, not a zero, and no link', async () => {
    api.getDashStats.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }))
    api.getHealth.mockRejectedValue(Object.assign(new Error('x'), { status: 403 }))
    render(<MemoryRouter><MetricStrip go={() => () => {}} /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect(value('certificates').textContent).toBe('–')
    expect(metric('certificates').hasAttribute('href')).toBe(false)
    expect(value('expired').textContent).toBe('–')
    expect(value('failures').textContent).toBe('–')
    expect(metric('failures').hasAttribute('href')).toBe(false)
    expect(value('failures').className).toBe('value')
  })

  it('nothing to handle is a plain zero', async () => {
    api.getQueue.mockResolvedValue({ data: { total: 0, counts: {}, items: [] } })
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('0'))
    expect(value('queue').className).toBe('value')
  })

  it('shows the mockup skeleton while the first answer is awaited', async () => {
    api.getDashStats.mockReturnValue(new Promise(() => {}))
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    expect(document.querySelectorAll('.metric-strip .sk-metric').length).toBeGreaterThanOrEqual(2)
  })
})
