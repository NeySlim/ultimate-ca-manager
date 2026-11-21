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
