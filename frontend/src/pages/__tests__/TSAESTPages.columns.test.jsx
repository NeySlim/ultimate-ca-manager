/**
 * The columns of the TSA and EST lists: the name takes the room left, never the
 * authority; the one TSA service has no sort, the EST endpoints sort by name from the first render, kept in the address.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'

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
import { absorbers, headersOf, rowNames, sortedHeaders, sortKeys } from '../../test/listContract'
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

describe('the TSA and EST lists', () => {
  it('TSA: one row by construction, no sort, the name taking the room left', async () => {
    const at = renderAtUrl(<TSAPage />, '/tsa-config')
    await screen.findByRole('button', { name: 'tsa.serviceName' })
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual([])
    expect(headersOf(at.container).filter((h) => h.aria)).toEqual([])
  })

  it('EST: by name from the first render, every column sorting, the sort in the address', async () => {
    const at = renderAtUrl(<ESTPage />, '/est-config')
    await screen.findByRole('button', { name: 'iot' })
    expect(rowNames(at.container)).toEqual(['est.defaultEndpoint', 'iot'])
    expect(sortedHeaders(at.container)).toEqual([['atelier.name', 'ascending']])
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual(['name', 'ca', 'auth', 'state'])
    // The authentication under a short header, its whole name for a screen reader and in the title
    expect(headersOf(at.container).find((h) => h.sort === 'auth').label).toBe('est.columns.authShort')
    expect(screen.getByRole('button', { name: 'est.columns.auth' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    expect(at.where()).toBe('/est-config?sort=name&order=desc')
    expect(rowNames(at.container)).toEqual(['iot', 'est.defaultEndpoint'])
    at.unmount()
    const again = renderAtUrl(<ESTPage />, '/est-config?sort=ca&order=asc')
    await screen.findByRole('button', { name: 'iot' })
    expect(sortedHeaders(again.container)).toEqual([['tsa.columns.ca', 'ascending']])
    expect(rowNames(again.container)).toEqual(['iot', 'est.defaultEndpoint'])
  })
})
