/**
 * The columns of the SCEP views (COLONNES-SPEC T1, T2, T4, T9, L7, R5): the name takes the room left in each, one column
 * sorted from the first render and kept in the address of its own view; the requests, paged by the server, are sorted by
 * it and shown in its order; a phone record names its dates.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const mobile = vi.hoisted(() => ({ isMobile: false }))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() }))
vi.mock('../../contexts', () => ({ useNotification: () => notify, useMobile: () => mobile }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../hooks', async () => ({
  usePersistedState: (await vi.importActual('../../hooks/usePersistedState')).usePersistedState,
  usePermission: () => ({ hasPermission: () => true, canWrite: () => true }),
  useClipboard: () => ({ copy: vi.fn() }),
}))
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
const scep = vi.hoisted(() => ({
  getConfig: vi.fn(), getStats: vi.fn(), getProfiles: vi.fn(), getRequests: vi.fn(), getRequest: vi.fn(), getIntuneApps: vi.fn(), getChallenge: vi.fn(),
}))
vi.mock('../../services', () => ({
  scepService: scep,
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 3, refid: 'ca-3', descr: 'IoT CA', name: 'IoT CA', subject: 'CN=IoT CA' }, { id: 4, refid: 'ca-4', name: 'Branch CA', subject: 'CN=Branch CA' }] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))
const setup = vi.hoisted(() => ({ state: { visible: false } }))
vi.mock('../../components/shell/useSetup', async (actual) => ({ ...(await actual()), useSetup: () => setup.state }))

import { renderAtUrl } from '../../test/dockUrl'
import { absorbers, recordFacts, rowNames, sortedHeaders, sortKeys } from '../../test/listContract'
import SCEPPage from '../SCEPPage'

const PROFILES = [
  { id: 1, name: 'Postes nomades', ca_refid: 'ca-3', ca_name: 'IoT CA', template_name: null, enabled: false, intune_enabled: true },
  { id: 2, name: 'Équipements réseau', ca_refid: 'ca-3', ca_name: 'IoT CA', template_name: 'Réseau', enabled: true, intune_enabled: false },
]
// The server's order, deliberately not one a sort here would give
const REQUESTS = [
  { id: 9, subject: 'CN=beta,O=Lab', transaction_id: 'tx-9', status: 'pending', created_at: '2026-11-08T10:00:00Z', ca_refid: 'ca-3', profile_id: 2 },
  { id: 7, subject: 'CN=alpha,O=Lab', transaction_id: 'tx-7', status: 'approved', created_at: '2026-11-09T10:00:00Z', ca_refid: 'ca-3' },
  { id: 8, subject: 'CN=gamma,O=Lab', transaction_id: 'tx-8', status: 'rejected', created_at: '2026-11-07T10:00:00Z', ca_refid: 'ca-3' },
]

beforeEach(() => {
  vi.clearAllMocks()
  mobile.isMobile = false
  scep.getConfig.mockResolvedValue({ data: { enabled: true } })
  scep.getStats.mockResolvedValue({ data: { pending: 1, approved: 1, rejected: 1, total: 3 } })
  scep.getProfiles.mockResolvedValue({ data: PROFILES })
  scep.getRequests.mockResolvedValue({ data: REQUESTS, meta: { total: 3 } })
  scep.getChallenge.mockImplementation(async (id) => ({ data: { challenge: id === 3 ? 'secret' : null } }))
  scep.getIntuneApps.mockResolvedValue({ data: [
    { id: 7, name: 'Lab Intune', tenant_id: 'lab.onmicrosoft.com', client_id: 'client-8', profile_count: 0, last_test_at: '2026-11-01T00:00:00Z' },
    { id: 8, name: 'Corp Intune', tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7', profile_count: 2 },
  ] })
})

describe('the SCEP lists', () => {
  it('profiles: by name from the first render, every column sorting, the sort in the address', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config')
    await screen.findByRole('button', { name: 'Postes nomades' })
    expect(rowNames(at.container)).toEqual(['Équipements réseau', 'Postes nomades'])
    expect(sortedHeaders(at.container)).toEqual([['atelier.name', 'ascending']])
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual(['name', 'ca', 'template', 'intune', 'state'])
    fireEvent.click(screen.getByRole('button', { name: 'Intune' }))
    expect(at.where()).toBe('/scep-config?sort=intune&order=asc')
    expect(rowNames(at.container)).toEqual(['Postes nomades', 'Équipements réseau'])
  })

  it('requests: the newest first asked of the server, its order kept, a header asks again from page one', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=requests')
    await screen.findByRole('button', { name: 'beta' })
    expect(scep.getRequests.mock.calls.at(-1)[0]).toMatchObject({ page: 1, sort_by: 'created_at', sort_order: 'desc' })
    expect(sortedHeaders(at.container)).toEqual([['scep.requested', 'descending']])
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual(['subject', 'transaction_id', 'created_at', 'status'])
    expect(at.container.querySelector('td[title="tx-7"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    await waitFor(() => expect(scep.getRequests.mock.calls.at(-1)[0]).toMatchObject({ page: 1, sort_by: 'subject', sort_order: 'asc' }))
    expect(at.where()).toBe('/scep-config?tab=requests&sort=subject&order=asc')
    expect(rowNames(at.container)).toEqual(['beta', 'alpha', 'gamma'])
  })

  it('requests: a sort asked from page two goes back to page one', async () => {
    scep.getRequests.mockImplementation(async ({ page }) => ({ data: [{ ...REQUESTS[0], id: page, subject: `CN=p${page}` }], meta: { total: 60 } }))
    renderAtUrl(<SCEPPage />, '/scep-config?tab=requests')
    await screen.findByRole('button', { name: 'p1' })
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await screen.findByRole('button', { name: 'p2' })
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    await waitFor(() => expect(scep.getRequests.mock.calls.at(-1)[0]).toMatchObject({ page: 1, sort_by: 'status', sort_order: 'asc' }))
    expect(await screen.findByRole('button', { name: 'p1' })).toBeInTheDocument()
  })

  it('requests: drawn once the profiles and authorities their cells name are read', async () => {
    let release
    scep.getProfiles.mockReturnValue(new Promise((resolve) => { release = () => resolve({ data: PROFILES }) }))
    renderAtUrl(<SCEPPage />, '/scep-config?tab=requests')
    await waitFor(() => expect(scep.getRequests).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 0))
    // The columns are measured on their first rows: a row drawn before its profile would keep "#2" widths
    expect(screen.queryByRole('button', { name: 'beta' })).toBeNull()
    release()
    await screen.findByRole('button', { name: 'beta' })
    expect(screen.getByText('Équipements réseau')).toBeInTheDocument()
  })

  it('requests: open on the sort the address holds; a change of view drops it', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=requests&sort=status&order=desc')
    await screen.findByRole('button', { name: 'beta' })
    expect(scep.getRequests.mock.calls.at(-1)[0]).toMatchObject({ sort_by: 'status', sort_order: 'desc' })
    expect(sortedHeaders(at.container)).toEqual([['atelier.state', 'descending']])
    fireEvent.change(screen.getByRole('combobox', { name: 'protocols.view' }), { target: { value: 'intune' } })
    expect(at.where()).toBe('/scep-config?tab=intune')
  })

  it('challenges: by name, the subject taking the room left', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges')
    await screen.findByRole('button', { name: 'Branch CA' })
    expect(rowNames(at.container)).toEqual(['Branch CA', 'IoT CA'])
    expect(sortedHeaders(at.container)).toEqual([['atelier.name', 'ascending']])
    expect(absorbers(at.container)).toEqual(['common.subject'])
    expect(sortKeys(at.container)).toEqual(['name', 'subject', 'state'])
  })

  it('Intune apps: by name, the name taking the room left, the last test under a short header', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=intune')
    await screen.findByRole('button', { name: 'Lab Intune' })
    expect(rowNames(at.container)).toEqual(['Corp Intune', 'Lab Intune'])
    expect(sortedHeaders(at.container)).toEqual([['atelier.name', 'ascending']])
    expect(absorbers(at.container)).toEqual(['atelier.name'])
    expect(sortKeys(at.container)).toEqual(['name', 'tenant', 'client', 'test', 'state'])
    fireEvent.click(screen.getByRole('button', { name: 'scep.intuneAppLastTest' }))
    expect(at.where()).toBe('/scep-config?tab=intune&sort=test&order=asc')
    // A missing date comes last
    expect(rowNames(at.container)).toEqual(['Lab Intune', 'Corp Intune'])
  })

  it('a phone record of a request names its date', async () => {
    mobile.isMobile = true
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=requests')
    await screen.findAllByRole('button', { name: 'beta' })
    expect(recordFacts(at.container)[0][0]).toMatch(/^scep\.requested /)
  })
})
