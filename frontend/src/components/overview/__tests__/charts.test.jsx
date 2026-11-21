/**
 * The activity chart: its figures are readable without the drawing (alternative text, table,
 * legend), and each series keeps its own pattern.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
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

import { TrendCard } from '..'

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
    const legend = document.querySelector('#card-trend .horizon-legend')
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
    await waitFor(() => expect(chart.getAttribute('viewBox')).toBe('0 0 913 210'), { timeout: 5000 })
    expect(chart.getAttribute('height')).toBe('210')
    expect(seen).toEqual([chart.parentElement])
  })

  it('labels the axis with whole numbers', async () => {
    api.getTrend.mockResolvedValue({ data: { trend: week } })
    show(<TrendCard />)
    const chart = await screen.findByTestId('trend-chart')
    const ticks = [...chart.querySelectorAll('g > text.trend-axis')].map((el) => el.textContent)
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
