/**
 * The two chart cards: their figures are readable without the drawing (alternative text, table,
 * legend), each series keeps its own pattern, and the status ring leaves out an empty state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o && Object.keys(o).length > 0 ? `${k}:${JSON.stringify(o)}` : k) }),
}))
const api = vi.hoisted(() => ({ getTrend: vi.fn(), getDashStats: vi.fn() }))
vi.mock('../../../services', () => ({
  dashboardService: { getCertificateTrend: api.getTrend, getStats: api.getDashStats },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { TrendCard, StatesCard } from '..'

const show = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const day = (n, issued, revoked = 0, expired = 0) => ({ date: `2026-11-${String(n).padStart(2, '0')}`, name: 'x', issued, revoked, expired })
const week = [day(13, 1), day(14, 0), day(15, 4, 1), day(16, 2), day(17, 0, 0, 3), day(18, 0), day(19, 5, 1)]

beforeEach(() => { vi.clearAllMocks() })

describe('certificate activity', () => {
  it('asks for 7 days first and gives the totals in the alternative text', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    const chart = await screen.findByTestId('trend-chart')
    expect(api.getTrend).toHaveBeenCalledWith(7)
    expect(chart.getAttribute('role')).toBe('img')
    expect(chart.getAttribute('aria-label')).toBe('overview.trend.alt:{"count":7,"issued":12,"revoked":2,"expired":3}')
  })

  it('names each series in a legend with its total, and draws each with its own pattern', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    await screen.findByTestId('trend-chart')
    const legend = screen.getByTestId('card-trend').querySelector('.ov-legend')
    expect([...legend.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['common.issued12', 'common.revoked2', 'common.expired3'])
    const dashes = ['issued', 'revoked', 'expired'].map((s) => screen.getByTestId(`trend-line-${s}`).getAttribute('stroke-dasharray'))
    expect(new Set(dashes).size).toBe(3)
    for (const s of ['issued', 'revoked', 'expired']) expect(screen.getByTestId(`trend-line-${s}`).getAttribute('d')).toMatch(/^M[\d.]+,[\d.]+C/)
  })

  it('is drawn at the width it is shown, so its text keeps the size of the page text', async () => {
    const seen = []
    vi.stubGlobal('ResizeObserver', class {
      constructor(cb) { this.cb = cb }
      observe(el) { seen.push(el); Object.defineProperty(el, 'clientWidth', { value: 913, configurable: true }); this.cb() }
      disconnect() {}
    })
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    const chart = await screen.findByTestId('trend-chart')
    vi.unstubAllGlobals()
    await waitFor(() => expect(chart.getAttribute('viewBox')).toBe('0 0 913 210'))
    expect(chart.getAttribute('height')).toBe('210')
    expect(seen).toEqual([chart.parentElement])
  })

  it('labels the axis with whole numbers', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    const chart = await screen.findByTestId('trend-chart')
    const ticks = [...chart.querySelectorAll('g > text.ov-chart-axis')].map((el) => el.textContent)
    expect(ticks).toEqual(['0', '3', '6'])
  })

  it('carries the figures of every day in a table', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    await screen.findByTestId('trend-chart')
    const body = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(body).toHaveLength(7)
    expect(body[2].textContent).toBe('2026-11-15410')
    expect(body[4].textContent).toBe('2026-11-17003')
  })

  it('the 15 and 30 day buttons load that period and keep the chart meanwhile', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    await screen.findByTestId('trend-chart')
    const period = within(screen.getByRole('group', { name: 'overview.trend.period' }))
    expect(period.getAllByRole('button').map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false', 'false'])
    api.getTrend.mockReturnValue(new Promise(() => {}))
    fireEvent.click(period.getAllByRole('button')[2])
    await waitFor(() => expect(api.getTrend).toHaveBeenLastCalledWith(30))
    expect(period.getAllByRole('button')[2].getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('trend-chart')).toBeTruthy()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('reads day by day with the arrow keys, and stops reading when focus leaves', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    const reader = (await screen.findByTestId('trend-chart')).parentElement
    expect(reader.getAttribute('tabindex')).toBe('0')
    expect(screen.queryByTestId('trend-tip')).toBeNull()
    fireEvent.keyDown(reader, { key: 'ArrowLeft' })
    expect(screen.getByTestId('trend-tip').textContent).toMatch(/common\.issued5common\.revoked1common\.expired0$/)
    fireEvent.keyDown(reader, { key: 'ArrowLeft' })
    fireEvent.keyDown(reader, { key: 'ArrowLeft' })
    expect(screen.getByTestId('trend-tip').textContent).toMatch(/common\.issued0common\.revoked0common\.expired3$/)
    fireEvent.blur(reader)
    expect(screen.queryByTestId('trend-tip')).toBeNull()
  })

  it('draws nothing for a period without any event', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: [day(18, 0), day(19, 0)] } })
    show(<TrendCard />)
    expect(await screen.findByText('overview.trend.quiet:{"count":7}')).toBeTruthy()
    expect(screen.queryByTestId('trend-chart')).toBeNull()
    expect(screen.getByRole('group', { name: 'overview.trend.period' })).toBeTruthy()
  })
})

describe('status distribution', () => {
  const stats = { total_certificates: 282, valid: 205, expiring_soon: 11, expired: 55, revoked: 11 }

  it('gives every figure in the alternative text and the total in the middle', async () => {
    api.getDashStats.mockResolvedValue({ data: stats })
    show(<StatesCard />)
    const donut = await screen.findByTestId('states-donut')
    expect(donut.getAttribute('aria-label')).toBe('overview.states.alt:{"total":282,"valid":205,"expiring":11,"expired":55,"revoked":11}')
    expect(donut.parentElement.querySelector('.ov-donut-total strong').textContent).toBe('282')
  })

  it('each state is a line with its count and share that opens its list', async () => {
    api.getDashStats.mockResolvedValue({ data: stats })
    show(<StatesCard />)
    await screen.findByTestId('states-donut')
    const links = within(screen.getByTestId('card-states')).getAllByRole('link')
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/certificates?status=valid', '/certificates?status=expiring', '/certificates?status=expired', '/certificates?status=revoked',
    ])
    expect(links.map((a) => a.textContent)).toEqual([
      'overview.filterValue.valid20573%', 'overview.filterValue.expiring114%',
      'overview.filterValue.expired5520%', 'overview.filterValue.revoked114%',
    ])
  })

  it('draws one slice per state that has certificates, in a fixed order, whose lengths fill the ring', async () => {
    api.getDashStats.mockResolvedValue({ data: { valid: 30, expiring_soon: 0, expired: 10, revoked: 0 } })
    show(<StatesCard />)
    const donut = await screen.findByTestId('states-donut')
    const slices = [...donut.querySelectorAll('.ov-donut-seg')]
    expect(slices.map((s) => s.getAttribute('data-series'))).toEqual(['valid', 'expired'])
    const [a, b] = slices.map((s) => Number(s.getAttribute('stroke-dasharray').split(' ')[0]))
    const ring = 2 * Math.PI * 58
    expect(a + b).toBeCloseTo(ring - 4, 1)
    expect(a / b).toBeCloseTo((ring * 0.75 - 2) / (ring * 0.25 - 2), 2)
    expect(slices[0].querySelector('title').textContent).toBe('overview.filterValue.valid: 30')
  })

  it('a state under one percent is not rounded to nothing', async () => {
    api.getDashStats.mockResolvedValue({ data: { valid: 999, expiring_soon: 1, expired: 0, revoked: 0 } })
    show(<StatesCard />)
    await screen.findByTestId('states-donut')
    expect(screen.getByText('overview.filterValue.expiring').closest('a').textContent).toContain('<1%')
    expect(screen.getByText('overview.filterValue.expired').closest('a').textContent).toContain('0%')
  })
})
