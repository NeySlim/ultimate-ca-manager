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
