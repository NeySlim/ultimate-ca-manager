/** Expiry horizon: the soonest expiries as the mockup's rows (name, delay, validity spent), then the states. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ Trans: ({ i18nKey }) => i18nKey, useTranslation: () => ({ t: (k, o) => (typeof o === 'string' ? o : (o?.defaultValue ?? k)) }) }))
const api = vi.hoisted(() => ({ getStats: vi.fn(), getNext: vi.fn() }))
vi.mock('../../../services', () => ({
  dashboardService: { getNextExpirations: api.getNext, getStats: api.getStats },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))

vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { HorizonCard } from '..'

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

const cert = (id, over) => ({ id, common_name: `cert-${id}`, valid_to: '2027-01-01T00:00:00Z', ...over })

const rows = () => [...document.querySelectorAll('#card-horizon .algo-list > li')]

describe('expiry horizon markers', () => {
  it('marks the TSA signer and the OCSP responder, and only them', async () => {
    api.getStats.mockResolvedValue({ data: { total_certificates: 3, expiring_soon: 3, expired: 0 } })
    api.getNext.mockResolvedValue({ data: [
      cert(1, { is_tsa_signer: true }), cert(2, { is_ocsp_responder: true }), cert(3, {}),
    ] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    await screen.findByText('cert-1')
    const text = (i) => rows()[i].textContent
    expect(text(0)).toContain('overview.horizon.tsaSigner')
    expect(text(0)).not.toContain('overview.horizon.ocspResponder')
    expect(text(1)).toContain('overview.horizon.ocspResponder')
    expect(text(2)).not.toMatch(/tsaSigner|ocspResponder/)
  })
})

describe('expiry horizon rows', () => {
  const DAY = 86400000
  const at = (days) => new Date(Date.now() + days * DAY).toISOString()
  const soon = (id, left, lifetime) => ({ id, common_name: `cert-${id}`, valid_from: at(left - lifetime), valid_to: at(left) })

  it('each row gives its delay and a bar as long as the validity spent, the delay coloured by urgency', async () => {
    api.getStats.mockResolvedValue({ data: { total_certificates: 3, expiring_soon: 2, expired: 0 } })
    api.getNext.mockResolvedValue({ data: [soon(1, -1, 100), soon(2, 5, 100), soon(3, 200, 400)] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    await screen.findByText('cert-1')
    const items = rows()
    expect(items.map((li) => li.getAttribute('data-urgency'))).toEqual(['bad', 'warn', 'good'])
    expect(items.map((li) => li.querySelector('.algo-bar > span').style.width)).toEqual(['100%', '95%', '50%'])
    expect(items.map((li) => li.querySelector('.algo-row strong').className)).toEqual(['bad', 'warn', ''])
    expect(items.map((li) => li.querySelector('.algo-row strong').textContent)).toEqual(['time.compact.overdueDays', 'time.compact.inDays', 'time.compact.inDays'])
    for (const li of items) {
      expect(li.querySelector('a.algo-row').getAttribute('href')).toMatch(/^\/certificates\/\d$/)
      expect(li.querySelector('.algo-bar').getAttribute('aria-label')).toBe('overview.horizon.elapsed')
    }
  })

  it('a row without its start date has its delay and no bar; one without an end date has neither', async () => {
    api.getStats.mockResolvedValue({ data: { total_certificates: 2, expiring_soon: 0, expired: 0 } })
    api.getNext.mockResolvedValue({ data: [{ id: 1, common_name: 'a', valid_to: at(40) }, { id: 2, common_name: 'b', valid_to: null }] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    await screen.findByText('a')
    const items = rows()
    expect(items[0].querySelector('strong').textContent).toBe('time.compact.inDays')
    expect(items[0].querySelector('.algo-bar')).toBeNull()
    expect(items[1].querySelector('strong').textContent).toBe('–')
    expect(items[1].querySelector('.algo-bar')).toBeNull()
  })

  it('lists six rows at most and links to the whole list', async () => {
    api.getStats.mockResolvedValue({ data: { total_certificates: 20, expiring_soon: 9, expired: 0 } })
    api.getNext.mockResolvedValue({ data: Array.from({ length: 9 }, (_, i) => soon(i + 1, 10 + i, 90)) })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    await screen.findByText('cert-1')
    expect(rows()).toHaveLength(6)
    expect(api.getNext).toHaveBeenCalledWith(6)
    expect(screen.getByText('common.viewAll').closest('a').getAttribute('href')).toBe('/certificates?status=expiring')
  })
})

describe('expiry horizon states', () => {
  it('gives the four states of the mockup, each with its dot, figure and list', async () => {
    api.getStats.mockResolvedValue({ data: { total_certificates: 20, valid: 12, expiring_soon: 3, expired: 4, revoked: 1 } })
    api.getNext.mockResolvedValue({ data: [] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    await screen.findByText('overview.horizon.state.valid')
    const states = [...document.querySelectorAll('#card-horizon .status-list > div')]
    expect(states.map((d) => [d.querySelector('.dot').className, d.querySelector('strong').textContent, d.querySelector('a').getAttribute('href')])).toEqual([
      ['dot good', '12', '/certificates?status=valid'], ['dot warn', '3', '/certificates?status=expiring'],
      ['dot bad', '4', '/certificates?status=expired'], ['dot muted', '1', '/certificates?status=revoked'],
    ])
  })
})
