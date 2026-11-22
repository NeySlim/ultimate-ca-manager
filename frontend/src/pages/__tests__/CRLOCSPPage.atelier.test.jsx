/**
 * CRL / OCSP as the mockup's crl module draws it: the list (CRL, Publiée, Prochaine mise à jour,
 * OCSP, État) with states read from the CRL's real dates, the responder's figures in the filters'
 * aside, the one-object dock with its tabs, and the actions each permission allows.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts === 'object' ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: 'fr', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn().mockResolvedValue(true),
}))
const perms = vi.hoisted(() => ({ crl: true, cas: true }))
const mobile = vi.hoisted(() => ({ isMobile: false }))
vi.mock('../../contexts', () => ({ useNotification: () => notify, useMobile: () => mobile }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ canWrite: (r) => perms[r] ?? true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
    useClipboard: () => ({ copy: vi.fn().mockResolvedValue(true) }),
  }
})
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../../components/CRLDeploySection', () => ({ CRLDeploySection: () => <section data-testid="deploy" /> }))

const NOW = Date.parse('2026-11-08T12:00:00Z')
const CAS = vi.hoisted(() => [
  { id: 1, refid: 'r1', descr: 'Services CA', has_private_key: true, ocsp_enabled: true, cdp_enabled: true, crl_digest: 'sha256', cdp_urls: ['http://cdp.example/1.crl'] },
  { id: 2, refid: 'r2', descr: 'Internal CA', has_private_key: true, ocsp_enabled: false, cdp_enabled: true },
  { id: 3, refid: 'r3', descr: 'Old CA', has_private_key: true, ocsp_enabled: false },
  { id: 4, refid: 'r4', descr: 'New CA', has_private_key: false, ocsp_enabled: false },
])
const svc = vi.hoisted(() => ({
  getAll: vi.fn(), getOcspStatus: vi.fn(), getOcspStats: vi.fn(), getForCA: vi.fn(), getOcspResponder: vi.fn(),
  regenerate: vi.fn(), toggleAutoRegen: vi.fn(), configureCrl: vi.fn(), getEligibleOcspResponders: vi.fn(), setOcspResponder: vi.fn(),
}))
const cas = vi.hoisted(() => ({ getAll: vi.fn(), update: vi.fn() }))
vi.mock('../../services', () => ({ casService: cas, crlService: svc }))

import { renderAtUrl } from '../../test/dockUrl'
// The first-run state is useSetup's own subject: here it is given
const setup = vi.hoisted(() => ({ state: { visible: false } }))
vi.mock('../../components/shell/useSetup', async (actual) => ({ ...(await actual()), useSetup: () => setup.state }))
import CRLOCSPPage from '../CRLOCSPPage'
import { crlState } from '../protocols/protocolStates'

beforeEach(() => {
  vi.clearAllMocks()
  mobile.isMobile = false
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  localStorage.clear()
  setup.state = { visible: false }
  perms.crl = true
  perms.cas = true
  cas.getAll.mockResolvedValue({ data: CAS })
  cas.update.mockResolvedValue({ data: {} })
  svc.getAll.mockResolvedValue({ data: [
    { ca_id: 1, crl_number: 1842, revoked_count: 3, this_update: '2026-11-08T06:00:00Z', next_update: '2026-11-15T06:00:00Z' },
    { ca_id: 2, crl_number: 611, revoked_count: 0, this_update: '2026-11-08T06:00:00Z', next_update: '2026-11-09T06:00:00Z' },
    { ca_id: 3, crl_number: 4, revoked_count: 1, this_update: '2026-10-01T06:00:00Z', next_update: '2026-11-01T06:00:00Z' },
  ] })
  svc.getOcspStatus.mockResolvedValue({ data: { enabled: true, running: true } })
  svc.getOcspStats.mockResolvedValue({ data: { total_requests: 10, cache_hits: 4 } })
  svc.getForCA.mockResolvedValue({ data: { crl_pem: '-----BEGIN X509 CRL-----' } })
  svc.getOcspResponder.mockResolvedValue({ data: { responder: null } })
  svc.regenerate.mockResolvedValue({})
  svc.getEligibleOcspResponders.mockResolvedValue({ data: [{ id: 7, common_name: 'OCSP signer', serial_number: '0A' }] })
  svc.setOcspResponder.mockResolvedValue({})
})
afterEach(() => vi.useRealTimers())

const page = () => render(<MemoryRouter><CRLOCSPPage /></MemoryRouter>)
const rowOf = (name) => screen.getAllByRole('row').find((r) => within(r).queryByRole('button', { name }))

describe('the CRL / OCSP list', () => {
  it('draws the mockup columns and a state per CRL from its real dates', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: 'Services CA' })
    expect(container.querySelector('.atl h1#main-title')).toHaveTextContent('shell.moduleLabel.crlOcsp')
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'crlOcsp.columns.crlNumber', 'crlOcsp.columns.publication', 'crlOcsp.nextUpdate', 'OCSP', 'atelier.state', 'common.actions'])
    // Under its column's name the CRL number reads alone (G8)
    expect(rowOf('Services CA').children[1]).toHaveTextContent(/^1842$/)
    expect(rowOf('New CA').children[1]).toHaveTextContent(/^—$/)
    expect(rowOf('Services CA')).toHaveTextContent('crlOcsp.states.current')
    expect(rowOf('Services CA')).toHaveTextContent('crlOcsp.ocspActive')
    expect(rowOf('Internal CA')).toHaveTextContent('crlOcsp.states.soon')
    expect(rowOf('Old CA')).toHaveTextContent('crlOcsp.states.expired')
    expect(rowOf('New CA')).toHaveTextContent('crlOcsp.states.none')
    expect(container.querySelector('.active-filters')).toHaveTextContent('crlOcsp.responderAside')
    expect(container.querySelector('.active-filters')).toHaveTextContent('"count":10,"rate":40')
  })

  it('filters by a state chip and by the search', async () => {
    page()
    await screen.findByRole('button', { name: 'Services CA' })
    const chips = within(screen.getByRole('group', { name: 'crlOcsp.filterByState' }))
    fireEvent.click(chips.getByRole('button', { name: /crlOcsp.states.soon/ }))
    expect(screen.queryByRole('button', { name: 'Services CA' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Internal CA' })).toBeInTheDocument()
    fireEvent.click(chips.getByRole('button', { name: /common.all/ }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'old' } })
    expect(screen.getAllByRole('button', { name: /Old CA/ }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Services CA' })).toBeNull()
  })

  it('sorts every column from its header and pages a long list by 25', async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ id: 100 + i, refid: `m${i}`, descr: `Branch CA ${i + 1}`, has_private_key: true, ocsp_enabled: i === 7 }))
    cas.getAll.mockResolvedValue({ data: [...CAS, ...many] })
    const { container } = page()
    await screen.findByRole('button', { name: 'Services CA' })
    const footer = container.querySelector('footer.table-footer')
    expect(container.querySelectorAll('tbody tr')).toHaveLength(25)
    expect(footer).toHaveTextContent('crlOcsp.range {"shown":"1–25","count":34}')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(container.querySelectorAll('tbody tr')).toHaveLength(9)
    // A header sorts from page one; the second click reverses
    fireEvent.click(screen.getByRole('button', { name: 'crlOcsp.columns.crlNumber' }))
    expect(screen.getByRole('columnheader', { name: 'crlOcsp.columns.crlNumber' })).toHaveAttribute('aria-sort', 'ascending')
    expect(footer).toHaveTextContent('"shown":"1–25"')
    expect(container.querySelector('tbody tr').children[1]).toHaveTextContent(/^4$/)
    fireEvent.click(screen.getByRole('button', { name: 'crlOcsp.columns.crlNumber' }))
    expect(container.querySelector('tbody tr').children[1]).toHaveTextContent(/^1842$/)
    fireEvent.click(screen.getByRole('button', { name: 'OCSP' }))
    expect(container.querySelectorAll('tbody tr')[1]).toHaveTextContent('crlOcsp.ocspActive')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    expect(container.querySelector('tbody tr')).toHaveTextContent('crlOcsp.states.current')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    expect([...container.querySelectorAll('tbody tr .entity-name')].slice(0, 3).map((n) => n.textContent))
      .toEqual(['Branch CA 1', 'Branch CA 2', 'Branch CA 3'])
    for (const name of ['crlOcsp.columns.publication', 'crlOcsp.nextUpdate']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    // A search shorter than a page has no page controls
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'old' } })
    expect(within(footer).queryByRole('button', { name: 'table.nextPage' })).toBeNull()
    expect(footer).toHaveTextContent('crlOcsp.range {"shown":1,"count":34}')
  })

  it('opens on the nearest next update, keeps the sort in the address, and reads it back', async () => {
    const at = renderAtUrl(<CRLOCSPPage />, '/crl-ocsp')
    await screen.findByRole('button', { name: 'Services CA' })
    const sorted = () => screen.getAllByRole('columnheader').filter((h) => /ending/.test(h.getAttribute('aria-sort') || ''))
    expect(sorted().map((h) => [h.textContent, h.getAttribute('aria-sort')])).toEqual([['crlOcsp.nextUpdate', 'ascending']])
    // Old CA's CRL is overdue (1 Nov), Internal CA's is due tomorrow: the nearest first, the CA without a CRL last
    expect([...at.container.querySelectorAll('tbody tr .entity-name')].map((n) => n.textContent)).toEqual(['Old CA', 'Internal CA', 'Services CA', 'New CA'])
    fireEvent.click(screen.getByRole('button', { name: 'crlOcsp.columns.publication' }))
    expect(at.where()).toBe('/crl-ocsp?sort=published&order=asc')
    at.unmount()
    const again = renderAtUrl(<CRLOCSPPage />, '/crl-ocsp?sort=number&order=desc')
    await screen.findByRole('button', { name: 'Services CA' })
    expect(screen.getByRole('columnheader', { name: 'crlOcsp.columns.crlNumber' })).toHaveAttribute('aria-sort', 'descending')
    expect(again.container.querySelector('tbody tr').children[1]).toHaveTextContent(/^1842$/)
  })

  it('draws the facts of a record by priority, the dates after their label', async () => {
    mobile.isMobile = true
    const { container } = page()
    await screen.findAllByRole('button', { name: 'Services CA' })
    const facts = [...container.querySelectorAll('article.mobile-record')[2].querySelectorAll('.row-meta > span')].map((s) => s.textContent)
    expect(facts[0]).toMatch(/^crlOcsp\.nextUpdate /)
    // The CRL number named by its column (G9)
    expect(facts[1]).toBe('crlOcsp.columns.crlNumber 1842')
    expect(facts[2]).toMatch(/^crlOcsp\.columns\.publication /)
    expect(screen.getByRole('combobox', { name: 'table.sortBy' })).toHaveValue('next')
  })

  it('computes the state on the CRL dates (M12), never on the publish cadence', () => {
    expect(crlState({ has_crl: false }, NOW)).toBe('none')
    expect(crlState({ has_crl: true, crl_next_update: '2026-11-08T11:00:00Z', crl_next_publish: '2026-12-01T00:00:00Z' }, NOW)).toBe('expired')
    expect(crlState({ has_crl: true, crl_next_update: '2026-11-08T20:00:00Z' }, NOW)).toBe('soon')
    expect(crlState({ has_crl: true, crl_next_update: '2026-11-12T20:00:00Z', crl_next_publish: '2026-11-08T13:00:00Z' }, NOW)).toBe('current')
  })
})

describe('the CRL / OCSP dock', () => {
  it('opens on Aperçu with the properties and the summary, then regenerates the CRL', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Services CA' }))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(within(dock).getAllByRole('tab').map((t) => t.textContent)).toEqual(['atelier.overview', 'crlOcsp.tabs.publication', 'OCSP', 'crlOcsp.cdpNote'])
    expect(dock).toHaveTextContent('crlOcsp.summaryRevoked {"count":3,"number":1842}')
    fireEvent.click(within(dock).getByRole('button', { name: 'crlOcsp.regenerateCRL' }))
    await waitFor(() => expect(svc.regenerate).toHaveBeenCalledWith(1))
    expect(within(dock).getByRole('button', { name: 'common.download' })).toBeInTheDocument()
  })

  it('keeps the regeneration and the switches from an operator without write:crl', async () => {
    perms.crl = false
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Services CA' }))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(within(dock).queryByRole('button', { name: 'crlOcsp.regenerateCRL' })).toBeNull()
    fireEvent.click(within(dock).getByRole('tab', { name: 'crlOcsp.tabs.publication' }))
    expect(within(dock).getByRole('checkbox', { name: 'crlOcsp.autoRegen' })).toBeDisabled()
    fireEvent.click(within(dock).getByRole('tab', { name: 'crlOcsp.cdpNote' }))
    expect(within(dock).queryByRole('button', { name: 'crlOcsp.addUrl' })).toBeNull()
  })

  it('toggles the automatic regeneration in Publication', async () => {
    svc.toggleAutoRegen.mockResolvedValue({ data: { cdp_enabled: false } })
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Services CA' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'crlOcsp.tabs.publication' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'crlOcsp.autoRegen' }))
    await waitFor(() => expect(svc.toggleAutoRegen).toHaveBeenCalledWith(1, false))
  })

  it('adds a CDP URL and removes one in the distribution points', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Services CA' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'crlOcsp.cdpNote' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'crlOcsp.addUrl' })[0])
    fireEvent.change(screen.getByRole('textbox', { name: /protocols.newUrl/ }), { target: { value: 'http://cdp.example/2.crl' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'crlOcsp.addUrl' })[0])
    await waitFor(() => expect(cas.update).toHaveBeenCalledWith(1, { cdp_urls: ['http://cdp.example/1.crl', 'http://cdp.example/2.crl'] }))
    fireEvent.click(screen.getByRole('button', { name: /protocols.removeUrl/ }))
    await waitFor(() => expect(cas.update).toHaveBeenCalledWith(1, { cdp_urls: [] }))
  })

  it('assigns a delegated OCSP responder, a choice kept from an operator without write:cas', async () => {
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Services CA' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'OCSP' }))
    fireEvent.click(screen.getByRole('button', { name: 'crlOcsp.selectResponder' }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'crlOcsp.selectResponder' }), { target: { value: '7' } })
    await waitFor(() => expect(svc.setOcspResponder).toHaveBeenCalledWith(1, 7))
  })

  it('hides the responder choice without write:cas', async () => {
    perms.cas = false
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Services CA' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'OCSP' }))
    expect(screen.queryByRole('button', { name: 'crlOcsp.selectResponder' })).toBeNull()
  })
})

describe('the CRL / OCSP states', () => {
  it('shows the read error with the request and Réessayer', async () => {
    cas.getAll.mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }))
    page()
    expect(await screen.findByRole('alert')).toHaveTextContent('messages.errors.loadFailed.crl')
    fireEvent.click(screen.getByRole('button', { name: /common.retry|atelier|retry/i }))
    await waitFor(() => expect(cas.getAll).toHaveBeenCalledTimes(2))
  })

  it('says why the list is empty and links to the authorities', async () => {
    cas.getAll.mockResolvedValue({ data: [] })
    svc.getAll.mockResolvedValue({ data: [] })
    page()
    expect(await screen.findByText('crlOcsp.emptyTitle')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'crlOcsp.createCa' })).toHaveAttribute('href', '/cas')
  })

  it('leads the empty list to the setup assistant while its steps remain', async () => {
    cas.getAll.mockResolvedValue({ data: [] })
    svc.getAll.mockResolvedValue({ data: [] })
    setup.state = { visible: true, complete: false }
    page()
    expect(await screen.findByText('crlOcsp.emptyTitle')).toBeInTheDocument()
    const block = document.getElementById('empty-crl')
    expect(within(block).getByRole('link', { name: 'shell.setup.open' })).toHaveAttribute('href', '/')
    expect(within(block).queryByRole('link', { name: 'crlOcsp.createCa' })).toBeNull()
  })
})

describe('the CRL dock in the URL', () => {
  it('reopens the authority and section of the URL with its CRL, then writes the one opened', async () => {
    const r = renderAtUrl(<CRLOCSPPage />, '/crl-ocsp?item=2&section=distribution')
    const dock = await r.dock()
    expect(within(dock).getByRole('tab', { name: 'crlOcsp.cdpNote' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Internal CA')
    await waitFor(() => expect(svc.getForCA).toHaveBeenCalledWith(2))
    fireEvent.click(screen.getByRole('button', { name: 'Services CA' }))
    expect(r.where()).toBe('/crl-ocsp?item=1')
  })

  it('turns the work queue\'s ?ca= into the dock\'s item on the publication section', async () => {
    const r = renderAtUrl(<CRLOCSPPage />, '/crl-ocsp?ca=3')
    await waitFor(() => expect(r.where()).toBe('/crl-ocsp?item=3&section=publication'))
    expect(within(await r.dock()).getByRole('tab', { name: 'crlOcsp.tabs.publication' })).toHaveAttribute('aria-selected', 'true')
  })
})
