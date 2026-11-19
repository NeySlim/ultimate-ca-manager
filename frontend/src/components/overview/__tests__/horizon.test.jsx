/** Expiry horizon: the certificates that carry a service are marked as such. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k, o) => (typeof o === 'string' ? o : (o?.defaultValue ?? k)) }) }))
const api = vi.hoisted(() => ({ getStats: vi.fn(), getNext: vi.fn() }))
vi.mock('../../../services', () => ({
  certificatesService: { getStats: api.getStats },
  dashboardService: { getNextExpirations: api.getNext },
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

describe('expiry horizon markers', () => {
  it('marks the TSA signer and the OCSP responder, and only them', async () => {
    api.getStats.mockResolvedValue({ data: { total: 3, expiring: 3, expired: 0 } })
    api.getNext.mockResolvedValue({ data: [
      cert(1, { is_tsa_signer: true }), cert(2, { is_ocsp_responder: true }), cert(3, {}),
    ] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    const items = await screen.findAllByRole('listitem')
    const text = (i) => items[i].textContent
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

  it('each row carries a pill with the days left and a bar as long as the validity spent, coloured by urgency', async () => {
    api.getStats.mockResolvedValue({ data: { total: 3, expiring: 2, expired: 0 } })
    api.getNext.mockResolvedValue({ data: [soon(1, 5, 100), soon(2, 25, 100), soon(3, 200, 400)] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    const items = await screen.findAllByRole('listitem')
    expect(items.map((li) => li.getAttribute('data-urgency'))).toEqual(['bad', 'warn', 'good'])
    expect(items.map((li) => li.querySelector('.ov-meter span').style.width)).toEqual(['95%', '75%', '50%'])
    expect(items.map((li) => li.querySelector('.ov-meter').className)).toEqual(['ov-meter is-bad', 'ov-meter is-warn', 'ov-meter is-good'])
    for (const li of items) {
      expect(li.querySelector('.ov-pill').textContent).toBe('overview.horizon.expiresIn')
      expect(li.querySelector('.ov-pill svg')).not.toBeNull()
      expect(li.querySelector('.ov-meter').getAttribute('aria-label')).toBe('overview.horizon.elapsed')
    }
    expect(items[0].querySelector('.ov-pill').className).toContain('is-bad')
  })

  it('a row without its start date has the pill and no bar; one without an end date has neither', async () => {
    api.getStats.mockResolvedValue({ data: { total: 2, expiring: 0, expired: 0 } })
    api.getNext.mockResolvedValue({ data: [{ id: 1, common_name: 'a', valid_to: at(40) }, { id: 2, common_name: 'b', valid_to: null }] })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    const items = await screen.findAllByRole('listitem')
    expect(items[0].querySelector('.ov-pill')).not.toBeNull()
    expect(items[0].querySelector('.ov-meter')).toBeNull()
    expect(items[1].querySelector('.ov-pill')).toBeNull()
    expect(items[1].textContent).toContain('–')
  })

  it('lists six rows at most and links to the whole list', async () => {
    api.getStats.mockResolvedValue({ data: { total: 20, expiring: 9, expired: 0 } })
    api.getNext.mockResolvedValue({ data: Array.from({ length: 9 }, (_, i) => soon(i + 1, 10 + i, 90)) })
    render(<MemoryRouter><HorizonCard /></MemoryRouter>)
    expect(await screen.findAllByRole('listitem')).toHaveLength(6)
    expect(api.getNext).toHaveBeenCalledWith(6)
    expect(screen.getByText('common.viewAll').getAttribute('href')).toBe('/certificates?status=expiring')
  })
})
