/**
 * Figures strip (maquette-1): four figures from the routes the cards read, each with its trend or split
 * and a named gap, its tooltip on focus; a dash for a figure no route gave.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({ t: (k, o) => (o && Object.keys(o).length > 0 ? `${k}:${Object.values(o).join(',')}` : k) }),
}))
const api = vi.hoisted(() => ({ getDashStats: vi.fn(), getQueue: vi.fn(), getHealth: vi.fn(), getIssuance: vi.fn(), getExpirations: vi.fn() }))
vi.mock('../../../services', () => ({
  dashboardService: { getStats: api.getDashStats },
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getIssuance: api.getIssuance, getExpirations: api.getExpirations },
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
  api.getDashStats.mockResolvedValue({ data: { total_certificates: 282, total_cas: 139, pending_csrs: 2, ssh_certificates: 0, expired: 55, expiring_soon: 11, valid: 200 } })
  api.getIssuance.mockResolvedValue({ data: { days: 3, to: '2026-11-22', by_ca: [
    { caref: 'a', periods: [{ date: '2026-11-20', issued: 1 }, { date: '2026-11-21', issued: 5 }, { date: '2026-11-22', issued: 2 }] },
  ] } })
  api.getQueue.mockResolvedValue({ data: { total: 20, counts: { manual_renewal_due: 16, ca_expiring: 4 }, items: [{ kind: 'ca_expiring', tier: 'critical', id: 1 }] } })
  api.getHealth.mockResolvedValue({ data: { protocols: { acme: { periods: days(2) }, scep: { periods: days(0) }, est: { periods: days(1) }, scheduler: { periods: null } } } })
  // 30 UTC days from a Wednesday: five Monday-first weeks, the third with the busiest day
  const from = Date.parse('2026-11-25T00:00:00Z')
  const periods = Array.from({ length: 30 }, (_, i) => ({ date: new Date(from + i * 86400000).toISOString().slice(0, 10), total: 0 }))
  periods[0].total = 1
  periods[19].total = 10 // Monday 14 December
  periods[20].total = 2
  api.getExpirations.mockResolvedValue({ data: { from: '2026-11-25', periods } })
})

describe('the expiring figure', () => {
  it('draws the next 30 UTC days in weekly columns, names the peak day and keeps the stock already expired under it', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(metric('expiring').querySelector('svg.mini-bars')).not.toBeNull())
    expect(api.getExpirations).toHaveBeenCalledWith(30)
    const bars = [...metric('expiring').querySelectorAll('svg.mini-bars rect')]
    expect(bars).toHaveLength(5)
    expect(bars.map((r) => Number(r.getAttribute('height')) > 1.5)).toEqual([true, false, false, true, false])
    expect(metric('expiring').querySelector('small').textContent).toBe('overview.metrics.expiryPeak:10,Dec 14\u00a0· overview.metrics.alreadyExpired:55')
    fireEvent.focus(metric('expiring'))
    await waitFor(() => expect(document.querySelector('.chart-tip')?.textContent).toContain('overview.horizon.week:Nov 25'))
  })
})

describe('figures strip', () => {
  it('shows the four figures, each with what situates it', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('certificates').textContent).toBe('282'))
    expect([...document.querySelector('.metric-strip').children].map((m) => m.dataset.metric)).toEqual(['certificates', 'queue', 'expiring', 'failures'])
    // Issued over the window, signed as a gain, and the certificates still usable
    await waitFor(() => expect(metric('certificates').querySelector('.delta')).not.toBeNull())
    expect(metric('certificates').querySelector('.delta').dataset.delta).toBe('8')
    expect(metric('certificates').querySelector('small').textContent).toBe('+\u00a08\u00a0overview.metrics.issuedSub:30\u00a0· overview.metrics.active:211')
    // The gap held to the word after it by a no-break space: it never ends a narrow line alone
    expect(metric('certificates').querySelector('small .keep-with').textContent).toBe('+\u00a08\u00a0overview.metrics.issuedSub:30')
    expect(metric('certificates').querySelector('svg.spark-trend').getAttribute('aria-label')).toBe('overview.metrics.issuedAlt:3,2')
    expect(value('queue').textContent).toBe('20')
    expect(value('expiring').textContent).toBe('11')
    expect(metric('expiring').querySelector('small').textContent).toContain('overview.metrics.alreadyExpired:55')
    // Today only: the last day of each protocol series, the scheduler has none
    expect(value('failures').textContent).toBe('3')
  })

  it('splits the queue in critical, to do and to watch, the critical ones said first', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect([...metric('queue').querySelectorAll('.split-bar i')].map((i) => [i.dataset.part, i.style.flexGrow])).toEqual([['critical', '1'], ['todo', '16'], ['watch', '3']])
    expect(metric('queue').querySelector('small .delta.bad').textContent).toBe('overview.metrics.critical:1')
    // On a phone a wrapped line never starts with its separator: each mid-dot is glued to the part before it
    expect(metric('queue').querySelector('small').textContent).toBe('overview.metrics.critical:1\u00a0· overview.metrics.todo:16\u00a0· overview.metrics.watch:3')
    // The separator after the critical pill stays on its line, never starting the next one
    expect(metric('queue').querySelector('small .keep-with').textContent).toBe('overview.metrics.critical:1\u00a0·')
  })

  it('the failures carry 14 days of columns and their gap with yesterday, a rise in red', async () => {
    const series = (today, yesterday) => Array.from({ length: 20 }, (_, i) => ({ date: `d${i}`, ok: 0, failed: i === 19 ? today : i === 18 ? yesterday : 0 }))
    api.getHealth.mockResolvedValue({ data: { protocols: { acme: { periods: series(4, 1) }, scep: { periods: series(1, 0) } } } })
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('failures').textContent).toBe('5'))
    expect(metric('failures').querySelectorAll('svg.mini-bars rect')).toHaveLength(14)
    expect(metric('failures').querySelector('.delta').className).toBe('delta bad')
    expect(metric('failures').querySelector('.delta').dataset.delta).toBe('4')
    expect(api.getHealth).toHaveBeenCalledWith(30)
  })

  it('a fall of the failures is good news, no change is muted', async () => {
    const day = (failed) => ({ date: 'd', ok: 0, failed })
    api.getHealth.mockResolvedValue({ data: { protocols: { acme: { periods: [day(3), day(1)] } } } })
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('failures').textContent).toBe('1'))
    expect(metric('failures').querySelector('.delta').className).toBe('delta good')
  })

  it('shows its tooltip on focus, value first, and Escape hides it', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(metric('certificates').querySelector('.delta')).not.toBeNull())
    act(() => metric('certificates').focus())
    const tip = document.querySelector('[data-testid="chart-tip"]')
    expect(tip.getAttribute('role')).toBe('tooltip')
    expect(metric('certificates').getAttribute('aria-describedby')).toBe(tip.id)
    expect([...tip.querySelectorAll('.row')].map((r) => [r.querySelector('span').textContent, r.querySelector('b').textContent]))
      .toEqual([['overview.health.today', '2'], ['overview.metrics.tip.mean', '2.7'], ['overview.metrics.tip.peak:Nov 21', '5']])
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(document.querySelector('[data-testid="chart-tip"]')).toBeNull()
  })

  it('a figure that is a subset opens its filtered list, the inventory its whole list', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('certificates').textContent).toBe('282'))
    expect(metric('certificates').getAttribute('href')).toBe('/certificates')
    expect(metric('expiring').getAttribute('href')).toBe('/certificates?status=expiring')
  })

  it('colours a figure only when it calls for attention, the legend saying what it is', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('queue').className).toBe('value warn'))
    expect(value('failures').className).toBe('value bad')
    expect(value('certificates').className).toBe('value')
    expect(metric('failures').querySelector('.label').textContent).toBe('overview.metrics.failures')
  })

  it('the queue figure shows the whole queue, the failures figure the queue filtered on ACME (M:356)', async () => {
    const showQueue = vi.fn()
    render(<MemoryRouter><MetricStrip showQueue={showQueue} /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect(metric('queue').getAttribute('href')).toBe('#card-queue')
    fireEvent.click(metric('queue'))
    expect(showQueue).toHaveBeenLastCalledWith('')
    await waitFor(() => expect(value('failures').textContent).toBe('3'))
    expect(metric('failures').getAttribute('href')).toBe('#card-queue')
    fireEvent.click(metric('failures'))
    expect(showQueue).toHaveBeenLastCalledWith('acme')
    expect(showQueue).toHaveBeenCalledTimes(2)
  })

  it('the failures figure leads nowhere without a queue to show', async () => {
    render(<MemoryRouter><MetricStrip /></MemoryRouter>)
    await waitFor(() => expect(value('failures').textContent).toBe('3'))
    expect(metric('failures').hasAttribute('href')).toBe(false)
  })

  it('a route that fails leaves a dash, not a zero, and no link', async () => {
    api.getDashStats.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }))
    api.getHealth.mockRejectedValue(Object.assign(new Error('x'), { status: 403 }))
    render(<MemoryRouter><MetricStrip showQueue={() => {}} /></MemoryRouter>)
    await waitFor(() => expect(value('queue').textContent).toBe('20'))
    expect(value('certificates').textContent).toBe('–')
    expect(metric('certificates').hasAttribute('href')).toBe(false)
    expect(value('expiring').textContent).toBe('–')
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
