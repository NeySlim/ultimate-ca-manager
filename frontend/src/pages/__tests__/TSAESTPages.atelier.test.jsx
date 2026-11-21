/**
 * TSA and EST as the mockup's tsa and est modules draw them: the list of what the product really
 * serves (the one TSA service, the default EST endpoint and one per CA label), the one-object
 * dock, and the configuration in the settings form (draft, save of what changed, reset, rights).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() }))
const perms = vi.hoisted(() => ({ list: ['*'] }))
vi.mock('../../contexts', () => ({ useNotification: () => notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ hasPermission: (p) => perms.list.includes('*') || perms.list.includes(p), canWrite: () => true }),
    useClipboard: () => ({ copy: vi.fn().mockResolvedValue(true) }),
  }
})
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../../lib/policyAlgorithms', () => ({ useKeyPlatform: () => ({ fips: false, fipsKeys: null }), useFipsMode: () => false }))

const tsa = vi.hoisted(() => ({ getConfig: vi.fn(), updateConfig: vi.fn(), getStats: vi.fn(), getSignerCandidates: vi.fn(), issueSignerCertificate: vi.fn() }))
const est = vi.hoisted(() => ({ getConfig: vi.fn(), updateConfig: vi.fn(), getStats: vi.fn() }))
const cas = vi.hoisted(() => ({ getAll: vi.fn() }))
vi.mock('../../services', () => ({ tsaService: tsa, estService: est, casService: cas }))
// The first-run state is useSetup's own subject: here it is given
const setup = vi.hoisted(() => ({ state: { visible: false } }))
vi.mock('../../components/shell/useSetup', async (actual) => ({ ...(await actual()), useSetup: () => setup.state }))

import { renderAtUrl } from '../../test/dockUrl'
import TSAPage from '../TSAPage'
import ESTPage from '../ESTPage'

const CAS = [
  { id: 1, refid: 'ca-1', name: 'Services CA', has_private_key: true },
  { id: 2, refid: 'ca-2', name: 'IoT CA', has_private_key: true },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  perms.list = ['*']
  setup.state = { visible: false }
  cas.getAll.mockResolvedValue({ data: CAS })
  tsa.getConfig.mockResolvedValue({ data: { enabled: true, ca_refid: 'ca-1', policy_oid: '1.3.6.1.4.1.55555.1', require_dedicated_cert: true, signer_cert_refid: '', signer: { configured: false } } })
  tsa.updateConfig.mockResolvedValue({})
  tsa.getStats.mockResolvedValue({ data: { total: 5, successful: 4, failed: 1 } })
  tsa.getSignerCandidates.mockResolvedValue({ data: [] })
  est.getConfig.mockResolvedValue({ data: { enabled: true, ca_id: 1, validity_days: 90, username: 'estuser', password_set: true, labels: { iot: { ca_refid: 'ca-2', ca_name: 'IoT CA' } } } })
  est.updateConfig.mockResolvedValue({})
  est.getStats.mockResolvedValue({ data: { total: 2, successful: 2, failed: 0 } })
})

const at = (path, Page) => render(<MemoryRouter initialEntries={[path]}><Page /></MemoryRouter>)

describe('the TSA page', () => {
  it('lists the one service with the mockup columns and opens its dock', async () => {
    at('/tsa-config', TSAPage)
    const name = await screen.findByRole('button', { name: 'tsa.serviceName' })
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'tsa.columns.ca', 'tsa.columns.digest', 'tsa.columns.policy', 'atelier.state', 'common.actions'])
    const row = screen.getAllByRole('row')[1]
    expect(row).toHaveTextContent('Services CA')
    expect(row).toHaveTextContent('SHA-256, SHA-384, SHA-512')
    expect(row).toHaveTextContent('1.3.6.1.4.1.55555.1')
    fireEvent.click(name)
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(dock).toHaveTextContent('tsa.summaryTotals {"total":5,"successful":4,"failed":1}')
    expect(dock).toHaveTextContent('tsa.strictNoSigner')
  })

  it('saves only through the form once a field changed, and puts the draft back on reset', async () => {
    at('/tsa-config?tab=config', TSAPage)
    const oid = await screen.findByRole('textbox', { name: 'tsa.policyOid' })
    expect(screen.getByRole('button', { name: 'common.save' })).toBeDisabled()
    fireEvent.change(oid, { target: { value: '1.3.6.1.4.1.55555.2' } })
    expect(document.getElementById('settings-state')).toHaveTextContent('tsa.policyOid')
    fireEvent.click(screen.getByRole('button', { name: 'sectioned.undo' }))
    expect(oid).toHaveValue('1.3.6.1.4.1.55555.1')
    fireEvent.change(oid, { target: { value: '1.3.6.1.4.1.55555.2' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(tsa.updateConfig).toHaveBeenCalledWith(expect.objectContaining({ policy_oid: '1.3.6.1.4.1.55555.2', require_dedicated_cert: true })))
  })

  it('leaves the form read only without write:settings', async () => {
    perms.list = ['read:settings']
    at('/tsa-config?tab=config', TSAPage)
    expect(await screen.findByRole('textbox', { name: 'tsa.policyOid' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'tsa.enableTsa' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'tsa.signerGenerate' })).toBeDisabled()
  })
})

describe('the EST page', () => {
  it('lists the default endpoint and one per CA label, with the authentication the server accepts', async () => {
    at('/est-config', ESTPage)
    await screen.findByRole('button', { name: 'est.defaultEndpoint' })
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Services CA')
    expect(rows[1]).toHaveTextContent('iot')
    expect(rows[1]).toHaveTextContent('IoT CA')
    // mTLS or Basic, never both at once (RFC 7030 §3.2.3)
    expect(rows[0]).toHaveTextContent('est.auth.certOrPassword')
    fireEvent.click(within(rows[1]).getByRole('button', { name: 'iot' }))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(dock).toHaveTextContent('/.well-known/est/iot/simpleenroll')
  })

  it('gives the focus back to the default endpoint row when its dock closes', async () => {
    // jsdom draws no box: every element is said to be on screen
    const rects = vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([{ width: 10, height: 10 }])
    try {
      at('/est-config', ESTPage)
      fireEvent.click(await screen.findByRole('button', { name: 'est.defaultEndpoint' }))
      const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
      fireEvent.click(within(dock).getByRole('button', { name: 'inspector.close' }))
      await waitFor(() => expect(document.activeElement).toHaveAttribute('data-open', ''))
      expect(document.activeElement.closest('tr')).toHaveTextContent('Services CA')
    } finally {
      rects.mockRestore()
    }
  })

  it('says client certificate only when no Basic credentials are saved', async () => {
    est.getConfig.mockResolvedValue({ data: { enabled: true, ca_id: 1, labels: {} } })
    at('/est-config', ESTPage)
    await screen.findByRole('button', { name: 'est.defaultEndpoint' })
    expect(screen.getAllByRole('row')[1]).toHaveTextContent('est.auth.cert')
    expect(screen.getAllByRole('row')[1]).not.toHaveTextContent('est.auth.certOrPassword')
  })

  it('keeps the saved password unless one is typed, and sends the labels flat', async () => {
    at('/est-config?tab=config', ESTPage)
    const validity = await screen.findByRole('textbox', { name: 'est.validityDays' })
    fireEvent.change(validity, { target: { value: '120' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(est.updateConfig).toHaveBeenCalled())
    const sent = est.updateConfig.mock.calls[0][0]
    expect(sent.validity_days).toBe(120)
    expect(sent).not.toHaveProperty('password')
    expect(sent.labels).toEqual({ iot: 'ca-2' })
    fireEvent.change(screen.getByLabelText('est.password'), { target: { value: 's3cret' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(est.updateConfig).toHaveBeenCalledTimes(2))
    expect(est.updateConfig.mock.calls[1][0].password).toBe('s3cret')
  })
})

describe('the EST and TSA docks in the URL', () => {
  it('writes the endpoint opened, the default one by name, and reopens it on reload', async () => {
    const r = renderAtUrl(<ESTPage />, '/est-config')
    fireEvent.click(await screen.findByRole('button', { name: 'est.defaultEndpoint' }))
    expect(r.where()).toBe('/est-config?item=default')
    fireEvent.click(screen.getByRole('button', { name: 'iot' }))
    expect(r.where()).toBe('/est-config?item=iot')
    r.unmount()
    const again = renderAtUrl(<ESTPage />, '/est-config?item=default')
    expect(await again.dock()).toHaveTextContent('/.well-known/est/simpleenroll')
  })

  it('writes the time-stamping service opened and reopens it on reload', async () => {
    const r = renderAtUrl(<TSAPage />, '/tsa-config')
    fireEvent.click(await screen.findByRole('button', { name: 'tsa.serviceName' }))
    expect(r.where()).toBe('/tsa-config?item=tsa')
    r.unmount()
    const again = renderAtUrl(<TSAPage />, '/tsa-config?item=tsa')
    expect(within(await again.dock()).getByRole('heading', { level: 2 })).toHaveTextContent('tsa.serviceName')
  })
})

describe('nothing configured yet (the mockup\'s emptyBlock)', () => {
  const NONE_TSA = { data: { enabled: false, ca_refid: '', policy_oid: '', require_dedicated_cert: true, signer_cert_refid: '', signer: { configured: false } } }
  const NONE_EST = { data: { enabled: false, ca_id: null, validity_days: 365, username: '', password_set: false, labels: {} } }

  it('TSA: says what a service needs and leads to the assistant while its steps remain', async () => {
    tsa.getConfig.mockResolvedValue(NONE_TSA)
    setup.state = { visible: true, complete: false }
    at('/tsa-config', TSAPage)
    const block = await waitFor(() => { const b = document.getElementById('empty-tsa'); expect(b).not.toBeNull(); return b })
    expect(block).toHaveClass('empty', 'empty-hint')
    expect(within(block).getByRole('heading', { level: 3 })).toHaveTextContent('tsa.emptyTitle')
    expect(block.querySelector('p')).toHaveTextContent('tsa.emptyText')
    expect(within(block).getByRole('link', { name: 'shell.setup.open' })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('button', { name: 'tsa.serviceName' })).toBeNull()
  })

  it('TSA: the steps done, the empty block opens the configuration', async () => {
    tsa.getConfig.mockResolvedValue(NONE_TSA)
    const r = renderAtUrl(<TSAPage />, '/tsa-config')
    const block = await waitFor(() => { const b = document.getElementById('empty-tsa'); expect(b).not.toBeNull(); return b })
    fireEvent.click(within(block).getByRole('button', { name: 'tsa.configure' }))
    expect(r.where()).toBe('/tsa-config?tab=config')
  })

  it('TSA: a service with its CA set, even off, stays a row', async () => {
    tsa.getConfig.mockResolvedValue({ data: { ...NONE_TSA.data, ca_refid: 'ca-1' } })
    at('/tsa-config', TSAPage)
    expect(await screen.findByRole('button', { name: 'tsa.serviceName' })).toBeTruthy()
    expect(document.getElementById('empty-tsa')).toBeNull()
  })

  it('EST: says what an endpoint needs and leads to the assistant while its steps remain', async () => {
    est.getConfig.mockResolvedValue(NONE_EST)
    setup.state = { visible: true, complete: false }
    at('/est-config', ESTPage)
    const block = await waitFor(() => { const b = document.getElementById('empty-est'); expect(b).not.toBeNull(); return b })
    expect(within(block).getByRole('heading', { level: 3 })).toHaveTextContent('est.emptyTitle')
    expect(block.querySelector('p')).toHaveTextContent('est.emptyText')
    expect(within(block).getByRole('link', { name: 'shell.setup.open' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'est.defaultEndpoint' })).toBeNull()
  })

  it('EST: the steps done, the empty block opens the configuration; a label alone keeps the rows', async () => {
    est.getConfig.mockResolvedValue(NONE_EST)
    const r = renderAtUrl(<ESTPage />, '/est-config')
    const block = await waitFor(() => { const b = document.getElementById('empty-est'); expect(b).not.toBeNull(); return b })
    fireEvent.click(within(block).getByRole('button', { name: 'tsa.configure' }))
    expect(r.where()).toBe('/est-config?tab=config')
    r.unmount()
    est.getConfig.mockResolvedValue({ data: { ...NONE_EST.data, labels: { iot: { ca_refid: 'ca-2' } } } })
    at('/est-config', ESTPage)
    expect(await screen.findByRole('button', { name: 'iot' })).toBeTruthy()
    expect(document.getElementById('empty-est')).toBeNull()
  })
})
