/** Expiry horizon (maquette-2): weekly columns on a calendar of UTC days, the side list of the day or week picked. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, configure, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({ t: (k, o) => (o && typeof o === 'object' && 'count' in o ? `${k}:${o.count}` : k), i18n: { language: 'en' } }),
}))
const api = vi.hoisted(() => ({ getExpirations: vi.fn(), getAll: vi.fn() }))
vi.mock('../../../services', async () => {
  const { overviewService } = await vi.importActual('../../../services/overview.service')
  return {
    overviewService: { getExpirations: api.getExpirations, expirationQuery: overviewService.expirationQuery },
    certificatesService: { getAll: api.getAll },
  }
})
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { HorizonCard } from '..'
import { horizonDays } from '../../../lib/overviewHorizon'

configure({ asyncUtilTimeout: 5000 })

const FROM = '2026-11-25' // a Wednesday: Monday and Tuesday of the first week are outside the window
const days = (count) => Array.from({ length: count }, (_, i) => new Date(Date.parse(`${FROM}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10))
const period = (date, manual = 0, automatic = 0, over = {}) => ({ date, total: manual + automatic, manual, automatic, signers: 0, cas: 0, infrastructure: false, ...over })

function answer() {
  const list = days(horizonDays(3, FROM)).map((d) => period(d))
  list[0] = period(FROM, 1, 0) // Wednesday, today
  list[6] = period('2026-12-01', 3, 2) // Tuesday of the second week
  list[12] = period('2026-12-07', 0, 1, { cas: 1, infrastructure: true }) // Monday of the third week
  const total = list.reduce((s, p) => s + p.total, 0)
  return { data: { days: list.length, from: FROM, to: list.at(-1).date, total, periods: list,
    automatic_sources: ['acme'], filter_hint: { status: ['valid', 'expiring'], expires_to: '2026-12-14' } } }
}

const card = () => document.getElementById('card-horizon')
const weeks = () => [...card().querySelectorAll('button.wk')]
const day = (date) => card().querySelector(`button.day[data-date="${date}"]`)
const side = () => screen.getByTestId('horizon-side')

beforeEach(() => {
  api.getExpirations.mockReset().mockResolvedValue(answer())
  api.getAll.mockReset().mockResolvedValue({ data: [{ id: 4, common_name: 'web.example.com', source: 'manual', issuer: 'CN=Issuing' }] })
})

const show = async () => {
  render(<MemoryRouter><HorizonCard /></MemoryRouter>)
  await waitFor(() => expect(weeks().length).toBeGreaterThan(0))
}

describe('expiry horizon: the calendar', () => {
  it('asks the days that end on the Sunday of the thirteenth week', async () => {
    await show()
    const today = new Date().toISOString().slice(0, 10)
    expect(api.getExpirations).toHaveBeenCalledWith(horizonDays(13, today))
  })

  it('lays the window out in Monday-first UTC weeks, one column and seven cells each, the days before today blank', async () => {
    await show()
    expect(weeks().map((w) => w.dataset.week)).toEqual(['2026-11-23', '2026-11-30', '2026-12-07'])
    expect(card().querySelectorAll('.day.out')).toHaveLength(2)
    expect(card().querySelectorAll('button.day')).toHaveLength(19)
    expect(day('2026-11-24')).toBeNull()
  })

  it('sums each week of its days, manual under automatic, the busiest week labelled', async () => {
    await show()
    const [, second] = weeks()
    expect(second.getAttribute('aria-label')).toBe('overview.horizon.weekAlt:5')
    expect(second.querySelector('b').textContent).toBe('5')
    expect([...second.querySelectorAll('i')].map((i) => i.className)).toEqual(['auto', 'manual'])
    expect(weeks()[0].querySelector('b')).toBeNull()
  })

  it('shades each day on five steps of the busiest day and marks the day an authority expires', async () => {
    await show()
    expect(day('2026-12-01').dataset.l).toBe('4')
    expect(day(FROM).dataset.l).toBe('1')
    expect(day('2026-11-26').dataset.l).toBe('0')
    expect(day('2026-12-07').querySelector('.mark')).not.toBeNull()
    expect(day('2026-12-01').querySelector('.mark')).toBeNull()
  })
})

describe('expiry horizon: a day or a week opens its list', () => {
  it('starts on the busiest day and opens Certificates on exactly that UTC day', async () => {
    await show()
    expect(day('2026-12-01').getAttribute('aria-pressed')).toBe('true')
    const link = await within(side()).findByRole('link', { name: /overview\.horizon\.open/ })
    expect(link.getAttribute('href')).toBe('/certificates?status=valid&status=expiring&expires_from=2026-12-01&expires_to=2026-12-02')
    expect(api.getAll).toHaveBeenLastCalledWith(expect.objectContaining({
      status: ['valid', 'expiring'], expires_from: '2026-12-01', expires_to: '2026-12-02', per_page: 5, sort_by: 'valid_to',
    }))
    expect(side().querySelector('.fig').textContent).toBe('5')
  })

  it('a week of the first column starts today, not on its Monday, and ends after its Sunday', async () => {
    await show()
    fireEvent.click(weeks()[0])
    const link = await within(side()).findByRole('link', { name: /overview\.horizon\.open/ })
    expect(link.getAttribute('href')).toBe('/certificates?status=valid&status=expiring&expires_from=2026-11-25&expires_to=2026-11-30')
  })

  it('a day picked replaces the week, and a day without expiry offers no list', async () => {
    await show()
    fireEvent.click(day('2026-11-26'))
    await waitFor(() => expect(day('2026-11-26').getAttribute('aria-pressed')).toBe('true'))
    expect(side().querySelector('.fig').textContent).toBe('0')
    expect(within(side()).queryByRole('link', { name: /overview\.horizon\.open/ })).toBeNull()
  })
})

describe('expiry horizon: keyboard', () => {
  it('keeps one tab stop, moves a day up and down and a week left and right, and shows the tooltip on focus', async () => {
    await show()
    const stops = [...card().querySelectorAll('button.day')].filter((b) => b.tabIndex === 0)
    expect(stops.map((b) => b.dataset.date)).toEqual(['2026-12-01'])
    day('2026-12-01').focus()
    expect(await screen.findByRole('tooltip')).toHaveTextContent('overview.horizon.total')
    fireEvent.keyDown(day('2026-12-01'), { key: 'ArrowRight' })
    expect(document.activeElement).toBe(day('2026-12-08'))
    fireEvent.keyDown(day('2026-12-08'), { key: 'ArrowUp' })
    expect(document.activeElement).toBe(day('2026-12-07'))
    fireEvent.keyDown(day('2026-12-07'), { key: 'Home' })
    expect(document.activeElement).toBe(day(FROM))
    // Back past today stays where it is: those days are outside the window
    fireEvent.keyDown(day(FROM), { key: 'ArrowUp' })
    expect(document.activeElement).toBe(day(FROM))
    fireEvent.keyDown(day(FROM), { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).toBeNull()
  })
})

describe('expiry horizon: horizon and table', () => {
  it('asks five or fifty-two weeks for 30 days or a year', async () => {
    await show()
    const today = new Date().toISOString().slice(0, 10)
    fireEvent.click(screen.getByRole('button', { name: 'overview.horizon.year' }))
    await waitFor(() => expect(api.getExpirations).toHaveBeenLastCalledWith(horizonDays(52, today)))
    fireEvent.click(screen.getByRole('button', { name: 'overview.trend.short:30' }))
    await waitFor(() => expect(api.getExpirations).toHaveBeenLastCalledWith(horizonDays(5, today)))
  })

  it('says in one line that nothing expires', async () => {
    api.getExpirations.mockResolvedValue({ data: { ...answer().data, total: 0, periods: days(10).map((d) => period(d)) } })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    expect(await screen.findByText('overview.horizon.quiet')).toBeTruthy()
  })
})
