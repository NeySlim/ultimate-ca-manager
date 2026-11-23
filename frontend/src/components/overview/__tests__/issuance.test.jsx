/** Issuances by source: stacked columns per UTC day, the window against the previous one, a day opens its list. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, configure } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('react-i18next', async () => {
  const { cloneElement } = await vi.importActual('react')
  return {
  // As i18next with « <0>{{count}}</0> <1>word</1> »: the count in the first component, the key in the second
  Trans: ({ i18nKey, count, components }) => (components ? <>{cloneElement(components[0], {}, count)}{cloneElement(components[1], {}, i18nKey)}</> : i18nKey),
  useTranslation: () => ({ t: (k, o) => (o && typeof o === 'object' && Object.keys(o).length > 0 ? `${k}:${JSON.stringify(o)}` : k), i18n: { language: 'en' } }),
  }
})
const api = vi.hoisted(() => ({ getIssuance: vi.fn() }))
vi.mock('../../../services', () => ({ overviewService: { getIssuance: api.getIssuance } }))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
const perms = vi.hoisted(() => ({ list: true }))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: (p) => p !== 'read:certificates' || perms.list }) }))

import { IssuanceCard } from '..'

configure({ asyncUtilTimeout: 5000 })

const p = (date, over = {}) => ({ date, acme: 0, scep: 0, est: 0, wstep: 0, import: 0, manual: 0, ...over })
const FLOW = {
  periods: [p('2026-11-20', { acme: 3, scep: 1, manual: 2 }), p('2026-11-21'), p('2026-11-22', { est: 2, wstep: 1, import: 1 })],
  previous: { total: 8 },
}

const Where = () => <output data-testid="where">{useLocation().pathname + useLocation().search}</output>
const show = async () => {
  render(<MemoryRouter><IssuanceCard /><Where /></MemoryRouter>)
  return screen.findByTestId('flow-chart')
}
const col = (date) => document.querySelector(`#card-issuance g[data-day="${date}"]`)

beforeEach(() => {
  perms.list = true
  api.getIssuance.mockReset().mockResolvedValue({ data: { days: 30, flow: FLOW } })
})

describe('issuances by source', () => {
  it('asks 30 days first and stacks the sources of each day bottom-up, one segment per source that counts', async () => {
    await show()
    expect(api.getIssuance).toHaveBeenCalledWith(30)
    expect([...col('2026-11-20').querySelectorAll('rect[data-series]')].map((r) => r.dataset.series)).toEqual(['acme', 'scep', 'manual'])
    expect(col('2026-11-21').querySelectorAll('rect[data-series]')).toHaveLength(0)
    const [acme, scep] = col('2026-11-20').querySelectorAll('rect[data-series]')
    expect(Number(acme.getAttribute('y'))).toBeGreaterThan(Number(scep.getAttribute('y')))
    // The busiest day carries its total
    expect(col('2026-11-20').querySelector('text.lab').textContent).toBe('6')
  })

  it('hatches WSTEP and import over the colour they share with EST and manual', async () => {
    await show()
    const fill = (k) => col('2026-11-22').querySelector(`rect[data-series="${k}"]`).style.fill
    expect(fill('wstep')).toMatch(/^url\(#/)
    expect(fill('import')).toMatch(/^url\(#/)
    expect(fill('est')).toBe('var(--s3)')
  })

  it('heads the card with the window, its gap to the previous window and the automated share', async () => {
    await show()
    expect(document.querySelector('.flow-head .fig').textContent).toBe('10')
    const trend = document.querySelector('.flow-head [data-trend]')
    expect(trend.dataset.trend).toBe('25')
    expect(trend.className).toContain('good')
    expect(document.querySelector('.flow-head').textContent).toContain('overview.flow.automatic:{"pct":70}')
  })

  it('keeps ACME, SCEP, EST and manual in the legend, WSTEP and import once they count, each with its total', async () => {
    await show()
    const items = [...document.querySelectorAll('.flow-legend li')]
    expect(items.map((li) => li.dataset.series)).toEqual(['acme', 'scep', 'est', 'wstep', 'import', 'manual'])
    expect(items.map((li) => li.querySelector('b').textContent)).toEqual(['3', '1', '2', '1', '1', '2'])
    api.getIssuance.mockResolvedValue({ data: { flow: { periods: [p('2026-11-22', { acme: 1 })], previous: { total: 0 } } } })
    fireEvent.click(screen.getByRole('button', { name: 'overview.days:{"count":90}' }))
    await waitFor(() => expect(api.getIssuance).toHaveBeenLastCalledWith(90))
    await waitFor(() => expect([...document.querySelectorAll('.flow-legend li')].map((li) => li.dataset.series)).toEqual(['acme', 'scep', 'est', 'manual']))
    expect(document.querySelector('.flow-head [data-trend]')).toBeNull()
  })

  it('opens Certificates created that UTC day, by the pointer or by Enter on the chart', async () => {
    await show()
    fireEvent.click(col('2026-11-20'))
    expect(screen.getByTestId('where').textContent).toBe('/certificates?created_from=2026-11-20&created_to=2026-11-21')
    const frame = document.querySelector('.flow-frame')
    fireEvent.focus(frame)
    fireEvent.keyDown(frame, { key: 'Enter' })
    expect(screen.getByTestId('where').textContent).toBe('/certificates?created_from=2026-11-22&created_to=2026-11-23')
  })

  it('reads the day under the cursor in the tooltip, every source of it', async () => {
    await show()
    const frame = document.querySelector('.flow-frame')
    fireEvent.focus(frame)
    fireEvent.keyDown(frame, { key: 'Home' })
    const tip = await screen.findByRole('tooltip')
    expect(tip).toHaveTextContent('overview.horizon.total6')
    expect(tip).toHaveTextContent('overview.flow.openDay')
  })

  it('opens nothing for a principal who cannot read the list', async () => {
    perms.list = false
    await show()
    fireEvent.click(col('2026-11-20'))
    expect(screen.getByTestId('where').textContent).toBe('/')
  })

  it('says in one line that nothing was issued', async () => {
    api.getIssuance.mockResolvedValue({ data: { flow: { periods: [p('2026-11-22')], previous: { total: 0 } } } })
    render(<MemoryRouter><IssuanceCard /></MemoryRouter>)
    expect(await screen.findByText('overview.flow.quiet:{"count":30}')).toBeTruthy()
  })
})

describe('issuances by source: the chart fills its card', () => {
  it('measures its frame once the card has loaded, the skeleton gone', async () => {
    const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(900)
    const observers = []
    vi.stubGlobal('ResizeObserver', class { constructor(cb) { this.cb = cb; observers.push(this) } observe() {} disconnect() {} })
    try {
      let answer
      api.getIssuance.mockReturnValue(new Promise((done) => { answer = done }))
      render(<MemoryRouter><IssuanceCard /></MemoryRouter>)
      answer({ data: { days: 30, flow: FLOW } })
      const svg = await screen.findByTestId('flow-chart')
      await waitFor(() => expect(svg.getAttribute('viewBox')).toBe('0 0 900 230'))
    } finally {
      width.mockRestore()
      vi.unstubAllGlobals()
    }
  })
})

describe('the dates under the columns', () => {
  const month = { periods: Array.from({ length: 30 }, (_, i) => p(`2026-11-${String(i + 1).padStart(2, '0')}`, { acme: i % 3 })), previous: { total: 0 } }
  const ticks = () => [...document.querySelectorAll('#card-issuance g[data-day] > text:not(.lab)')].map((el) => el.closest('g').dataset.day)
  const atWidth = async (width) => {
    const ro = globalThis.ResizeObserver
    const cw = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')
    globalThis.ResizeObserver = class { observe() {} disconnect() {} }
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get() { return width } })
    try {
      api.getIssuance.mockResolvedValue({ data: { days: 30, flow: month } })
      await show()
      return ticks()
    } finally {
      globalThis.ResizeObserver = ro
      if (cw) Object.defineProperty(HTMLElement.prototype, 'clientWidth', cw)
      else delete HTMLElement.prototype.clientWidth
    }
  }

  it('keeps a weekly date a week before today on a wide card', async () => {
    expect(await atWidth(560)).toEqual(['2026-11-02', '2026-11-09', '2026-11-16', '2026-11-23', '2026-11-30'])
  })

  it('drops the weekly date that would run into « today » on a phone', async () => {
    expect(await atWidth(330)).toEqual(['2026-11-02', '2026-11-09', '2026-11-16', '2026-11-30'])
  })
})
