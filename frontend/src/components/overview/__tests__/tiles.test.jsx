/** Authorities and HSM tiles, revocation coverage, over the routes they are composed from. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, configure, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({ t: (k, o) => (o && typeof o === 'object' && Object.keys(o).length > 0 ? `${k}:${JSON.stringify(o)}` : k), i18n: { language: 'en' } }),
}))
const api = vi.hoisted(() => ({
  cas: vi.fn(), crls: vi.fn(), providers: vi.fn(), test: vi.fn(), issuance: vi.fn(), revocation: vi.fn(), regenerate: vi.fn(),
}))
vi.mock('../../../services', () => ({
  casService: { getAll: api.cas },
  crlService: { getAll: api.crls, regenerate: api.regenerate },
  hsmService: { getProviders: api.providers, testProvider: api.test },
  overviewService: { getIssuance: api.issuance, getRevocation: api.revocation },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
const perms = vi.hoisted(() => ({ denied: [] }))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: (p) => !perms.denied.includes(p) }) }))

import { AuthoritiesCard, RevocationCard } from '..'
import { OverviewContext } from '../shared'

configure({ asyncUtilTimeout: 5000 })

const DAY = 86400000
const at = (days) => new Date(Date.now() + days * DAY).toISOString()
const notify = { showSuccess: vi.fn(), showError: vi.fn() }
const show = (ui) => render(
  <MemoryRouter><OverviewContext.Provider value={{ notify, share: (k, run) => run() }}>{ui}</OverviewContext.Provider></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  perms.denied = []
  api.cas.mockResolvedValue({ data: [
    { id: 1, refid: 'r1', descr: 'Racine Production', status: 'active', valid_from: at(-300), valid_to: at(3000), cdp_enabled: true, offline: true,
      uses_hsm: true, hsm_provider_id: 7, hsm_provider_name: 'Luna 7', key_type: 'EC P-384' },
    { id: 2, refid: 'r2', descr: 'Intermédiaire Lab', status: 'active', valid_from: at(-500), valid_to: at(400), cdp_enabled: true, has_private_key: true, key_type: 'RSA 2048' },
  ] })
  api.crls.mockResolvedValue({ data: [{ ca_id: 1, next_update: at(23), is_stale: false }, { ca_id: 2, next_update: at(-192.5), is_stale: true }] })
  api.providers.mockResolvedValue({ data: [{ id: 7, name: 'Luna 7', status: 'connected', key_count: 6, provider_type: 'pkcs11', last_tested_at: at(-1) }] })
  api.issuance.mockResolvedValue({ data: { by_ca: [{ caref: 'r2', periods: [{ issued: 1, renewed: 0 }, { issued: 0, renewed: 2 }] }] } })
  api.test.mockResolvedValue({})
  api.revocation.mockResolvedValue({ data: { total: 136, current: 126, stale: 2, missing: 1, no_cdp: 7, to_publish: 3, items: [
    { ca_id: 12, name: 'Intermédiaire Tests', state: 'missing', next_update: null, ocsp_enabled: false, offline: false, can_publish: true, href_hint: '/crl-ocsp?ca=12' },
    { ca_id: 4, name: 'Racine de recette 2', state: 'stale', next_update: at(-194.5), ocsp_enabled: false, offline: true, can_publish: false, href_hint: '/crl-ocsp?ca=4' },
    { ca_id: 1, name: 'Racine Production', state: 'current', next_update: at(3), ocsp_enabled: true, offline: true, can_publish: false, href_hint: '/crl-ocsp?ca=1' },
  ] } })
  api.regenerate.mockResolvedValue({})
})

const tile = (kind, id) => document.querySelector(`[data-tile="${kind}"][data-tile-id="${id}"]`)

describe('authority and HSM tiles', () => {
  it('puts the authority in alert first, its state in a word and its CRL overdue for so many days', async () => {
    show(<AuthoritiesCard />)
    await waitFor(() => expect(tile('ca', 2)).not.toBeNull())
    const tiles = [...document.querySelectorAll('[data-tile]')]
    expect(tiles.map((x) => `${x.dataset.tile}-${x.dataset.tileId}`)).toEqual(['ca-2', 'ca-1', 'hsm-7'])
    expect(tile('ca', 2).dataset.tone).toBe('bad')
    expect(tile('ca', 2).textContent).toContain('overview.tiles.state.crlStale')
    expect(tile('ca', 2).textContent).toContain('overview.tiles.crlStaleSince:{"count":192}')
    expect(tile('ca', 2).getAttribute('href')).toBe('/cas/2')
  })

  it('names the key guard and the validity spent, and draws the issuances of 7 days', async () => {
    show(<AuthoritiesCard />)
    await waitFor(() => expect(tile('ca', 1)).not.toBeNull())
    expect(tile('ca', 1).textContent).toContain('overview.tiles.hsmKey:{"name":"Luna 7"}')
    expect(tile('ca', 1).textContent).toContain('overview.tiles.state.offline')
    expect(tile('ca', 2).querySelector('.track').getAttribute('aria-label')).toContain('"pct":56')
    expect(tile('ca', 2).querySelector('svg.spark-trend').getAttribute('aria-label')).toBe('overview.tiles.activityAlt:{"count":3}')
    expect(tile('ca', 1).textContent).toContain('overview.tiles.noActivity')
  })

  it('reads an expired authority red to its life bar, as its pill, and keeps amber for one late in its life', async () => {
    api.cas.mockResolvedValue({ data: [
      { id: 3, refid: 'r3', descr: 'R3 expirée', status: 'active', valid_from: at(-400), valid_to: at(-5), cdp_enabled: false, key_type: 'RSA 2048' },
      { id: 4, refid: 'r4', descr: 'Presque finie', status: 'active', valid_from: at(-950), valid_to: at(50), cdp_enabled: false, key_type: 'RSA 2048' },
    ] })
    show(<AuthoritiesCard />)
    await waitFor(() => expect(tile('ca', 3)).not.toBeNull())
    expect(tile('ca', 3).querySelector('.life b')).toHaveClass('bad')
    expect(tile('ca', 3).querySelector('.track')).toHaveClass('expired')
    expect(tile('ca', 3).querySelector('.track')).not.toHaveClass('late')
    expect(tile('ca', 4).querySelector('.life b')).toHaveClass('warn')
    expect(tile('ca', 4).querySelector('.track')).toHaveClass('late')
  })

  it('says there is no authority with the hierarchy\'s block, not the green tick of an empty card', async () => {
    api.cas.mockResolvedValue({ data: [] })
    api.providers.mockResolvedValue({ data: [] })
    show(<AuthoritiesCard />)
    const block = await waitFor(() => { const el = document.querySelector('#card-authorities #tiles-empty'); expect(el).not.toBeNull(); return el })
    expect(block.textContent).toContain('overview.hierarchy.emptyTitle')
    expect(document.querySelector('#card-authorities .empty-line')).toBeNull()
  })

  it('counts the authorities a module serves and tests it from its tile', async () => {
    show(<AuthoritiesCard />)
    await waitFor(() => expect(tile('hsm', 7)).not.toBeNull())
    expect(within(tile('hsm', 7)).getByText('6')).toBeTruthy()
    expect(tile('hsm', 7).querySelectorAll('.life b')[1].textContent).toBe('1')
    fireEvent.click(within(tile('hsm', 7)).getByRole('button', { name: 'overview.tiles.test' }))
    await waitFor(() => expect(api.test).toHaveBeenCalledWith(7))
    expect(notify.showSuccess).toHaveBeenCalled()
  })

  it('offers no test without the right to write HSM, and no module without the right to read them', async () => {
    perms.denied = ['write:hsm']
    show(<AuthoritiesCard />)
    await waitFor(() => expect(tile('hsm', 7)).not.toBeNull())
    expect(within(tile('hsm', 7)).queryByRole('button')).toBeNull()
  })

  it('leaves the modules out without the right to read them', async () => {
    perms.denied = ['read:hsm']
    show(<AuthoritiesCard />)
    await waitFor(() => expect(tile('ca', 1)).not.toBeNull())
    expect(api.providers).not.toHaveBeenCalled()
    expect(document.querySelector('[data-tile="hsm"]')).toBeNull()
  })
})

describe('revocation coverage', () => {
  it('heads with the share of current CRLs, rounded down, and splits the whole in three named parts', async () => {
    show(<RevocationCard />)
    await screen.findByText('overview.compliance.pct:{"pct":92}')
    expect([...document.querySelectorAll('.cover i')].map((i) => [i.dataset.part, i.style.flexGrow])).toEqual([['current', '126'], ['toPublish', '3'], ['noCdp', '7']])
    expect([...document.querySelectorAll('.cover-legend b')].map((b) => b.textContent)).toEqual(['126', '3', '7'])
  })

  it('lists the authorities to publish first, with Publish where the authority can, and publishes', async () => {
    show(<RevocationCard />)
    await waitFor(() => expect(document.querySelectorAll('.rev-list li')).toHaveLength(3))
    const rows = [...document.querySelectorAll('.rev-list li')]
    expect(rows.map((li) => li.dataset.state)).toEqual(['missing', 'stale', 'current'])
    expect(rows[1].textContent).toContain('overview.tiles.crlStaleSince:{"count":194}')
    expect(within(rows[1]).queryByRole('button')).toBeNull()
    expect(rows[1].textContent).toContain('overview.hierarchy.offline')
    expect(within(rows[0]).getByRole('link').getAttribute('href')).toBe('/crl-ocsp?ca=12')
    fireEvent.click(within(rows[0]).getByRole('button', { name: 'overview.revocation.publish' }))
    await waitFor(() => expect(api.regenerate).toHaveBeenCalledWith(12))
    expect(notify.showSuccess).toHaveBeenCalled()
  })

  it('offers no publication without the right to write CRLs', async () => {
    perms.denied = ['write:crl']
    show(<RevocationCard />)
    await waitFor(() => expect(document.querySelectorAll('.rev-list li')).toHaveLength(3))
    expect(document.querySelector('.rev-list button')).toBeNull()
  })
})
