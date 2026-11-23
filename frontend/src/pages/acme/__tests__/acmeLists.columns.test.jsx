/**
 * The columns of the ACME views drawn by their own components (COLONNES-SPEC T1, T2, T4, T9, L7, L8, R5): which column
 * takes the room left, which headers sort, the one sorted from the first render, the sort kept in the address; the
 * server's local orders sorted by the server, the EAB credentials read page after page before a sort in memory; the
 * phone's facts by priority, a date after its label.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ get: vi.fn(), listEab: vi.fn(), mobile: { isMobile: false } }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../services', () => ({ apiClient: { get: mocks.get, delete: vi.fn(), post: vi.fn() }, acmeService: { listEabCredentials: mocks.listEab } }))
vi.mock('../../../services/apiClient', () => ({
  buildQueryString: (params) => `?${new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]))}`,
}))
vi.mock('../../../contexts', () => ({
  useMobile: () => mocks.mobile,
  useNotification: () => ({ showConfirm: vi.fn(), showSuccess: vi.fn(), showError: vi.fn() }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => mocks.mobile }))
vi.mock('../../../hooks', async () => ({
  usePersistedState: (await vi.importActual('../../../hooks/usePersistedState')).usePersistedState,
  useClipboard: () => ({ copy: vi.fn() }),
  usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true }),
}))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../DnsUpdateKeysPanel', () => ({ default: () => null }))

import { renderAtUrl } from '../../../test/dockUrl'
import { absorbers, headersOf, recordFacts, rowNames, sortedHeaders, sortKeys } from '../../../test/listContract'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'
import LocalOrdersTab from '../LocalOrdersTab'
import LetsEncryptOrdersTab from '../LetsEncryptOrdersTab'
import DomainsTab from '../DomainsTab'
import LocalDomainsTab from '../LocalDomainsTab'
import DnsProvidersTab from '../DnsProvidersTab'
import CaAccountsManager from '../CaAccountsManager'
import EabTab from '../EabTab'

const at = (ui, url) => renderAtUrl(<WithDockSlot>{ui}</WithDockSlot>, url)
const lastQuery = () => Object.fromEntries(new URLSearchParams(mocks.get.mock.calls.at(-1)[0].split('?')[1]))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.mobile.isMobile = false
})

describe('the local orders of the ACME server', () => {
  const ORDERS = [
    { id: 3, domain: 'c.example.com', account: 'https://acme.example/acct/3', status: 'Valid', method: 'HTTP-01', expires: '2026-12-01', created_at: '2026-11-03T00:00:00Z' },
    { id: 1, domain: 'a.example.com', account: 'https://acme.example/acct/1', status: 'Pending', method: 'DNS-01', expires: '2026-12-03', created_at: '2026-11-01T00:00:00Z' },
    { id: 2, domain: 'b.example.com', account: 'https://acme.example/acct/2', status: 'Invalid', method: 'DNS-01', expires: '2026-12-02', created_at: '2026-11-02T00:00:00Z' },
  ]
  beforeEach(() => { mocks.get.mockResolvedValue({ data: { items: ORDERS, meta: { page: 1, per_page: 50, total: 3 } } }) })

  it('asks the server for the newest first and keeps its order; the name takes the room left', async () => {
    const view = at(<LocalOrdersTab />, '/acme?tab=localorders')
    await screen.findByRole('button', { name: 'c.example.com' })
    expect(lastQuery()).toMatchObject({ page: '1', sort_by: 'created_at', sort_order: 'desc' })
    expect(sortedHeaders(view.container)).toEqual([['common.created', 'descending']])
    expect(absorbers(view.container)).toEqual(['atelier.name'])
    expect(sortKeys(view.container)).toEqual(['domain', 'account', 'expires', 'created_at', 'status'])
    // A header asks the server again, from page one, and the rows stay as the server gives them
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: '1', sort_by: 'domain', sort_order: 'asc' }))
    expect(view.where()).toBe('/acme?tab=localorders&sort=domain&order=asc')
    expect(rowNames(view.container)).toEqual(['c.example.com', 'a.example.com', 'b.example.com'])
    // The account, a long URL, keeps its whole value in its title
    expect(view.container.querySelector('td[title="https://acme.example/acct/1"]')).not.toBeNull()
  })

  it('opens on the sort the address holds', async () => {
    const view = at(<LocalOrdersTab />, '/acme?tab=localorders&sort=expires&order=asc')
    await screen.findByRole('button', { name: 'c.example.com' })
    expect(lastQuery()).toMatchObject({ sort_by: 'expires', sort_order: 'asc' })
    expect(sortedHeaders(view.container)).toEqual([['common.expires', 'ascending']])
  })

  it('names the dates of a phone record', async () => {
    mocks.mobile.isMobile = true
    const view = at(<LocalOrdersTab />, '/acme?tab=localorders')
    await screen.findAllByRole('button', { name: 'c.example.com' })
    const [facts] = recordFacts(view.container)
    expect(facts[0]).toMatch(/^table\.fullExpires /)
    expect(facts[1]).toMatch(/^table\.fullCreated /)
  })
})

describe('the orders of the ACME client', () => {
  const ORDERS = [
    { id: 1, primary_domain: 'a.example.com', status: 'valid', environment: 'production', challenge_type: 'http-01', created_at: '2026-01-01T00:00:00Z', renewal_failures: 0 },
    { id: 2, primary_domain: 'b.example.com', status: 'pending', environment: 'staging', challenge_type: 'dns-01', created_at: '2026-03-01T00:00:00Z', renewal_failures: 2 },
    { id: 3, primary_domain: 'c.example.com', status: 'valid', environment: 'production', challenge_type: 'dns-01', created_at: '2026-02-01T00:00:00Z', renewal_failures: 0 },
  ]
  const tab = () => <LetsEncryptOrdersTab clientOrders={ORDERS} selectedClientOrder={null} onSelectOrder={vi.fn()} onRefresh={vi.fn()} />

  it('opens on the newest order, the name taking the room left, the failures a number under a short header', () => {
    const view = at(tab(), '/acme?tab=letsencryptorders')
    expect(rowNames(view.container)).toEqual(['b.example.com', 'c.example.com', 'a.example.com'])
    expect(sortedHeaders(view.container)).toEqual([['common.created', 'descending']])
    expect(absorbers(view.container)).toEqual(['atelier.name'])
    expect(sortKeys(view.container)).toEqual(['name', 'account', 'env', 'method', 'created', 'failures', 'state'])
    const failures = headersOf(view.container).find((h) => h.sort === 'failures')
    expect(failures).toMatchObject({ label: 'acme.columns.failures', number: true })
    expect(screen.getByRole('button', { name: 'acme.renewalFailuresLabel' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'acme.renewalFailuresLabel' }))
    fireEvent.click(screen.getByRole('button', { name: 'acme.renewalFailuresLabel' }))
    expect(view.where()).toBe('/acme?tab=letsencryptorders&sort=failures&order=desc')
    expect(rowNames(view.container)[0]).toBe('b.example.com')
  })
})

describe('the domains, providers and upstream CAs of the ACME client, the domains of the server', () => {
  const DOMAINS = [
    { id: 1, domain: 'zeta.test', dns_provider_name: 'cf', issuing_ca_name: 'B CA', is_wildcard_allowed: true, auto_approve: false },
    { id: 2, domain: 'alpha.test', dns_provider_name: 'route53', issuing_ca_name: 'A CA', is_wildcard_allowed: false, auto_approve: true },
  ]
  const PROVIDERS = [
    { id: 1, name: 'Zone B', provider_type: 'route53', enabled: true },
    { id: 2, name: 'Zone A', provider_type: 'cloudflare', enabled: true, is_default: true },
  ]
  const UPSTREAM = [
    { id: 1, label: 'ZeroSSL', directory_url: 'https://acme.zerossl.com/v2/DV90', email: 'z@example.com', is_registered: true },
    { id: 2, label: 'Actalis', directory_url: 'https://acme-api.actalis.com/acme/directory', email: 'a@example.com', is_registered: false, is_default: true },
  ]
  const noop = vi.fn()

  it.each([
    ['domains', () => <DomainsTab acmeDomains={DOMAINS} onAdd={noop} onEdit={noop} onDelete={noop} onTest={noop} canWrite canDelete />,
      ['alpha.test', 'zeta.test'], ['atelier.name'], ['name', 'provider', 'ca', 'wildcard', 'state'], 'provider'],
    ['localdomains', () => <LocalDomainsTab localDomains={DOMAINS} onAdd={noop} onEdit={noop} onDelete={noop} canWrite canDelete />,
      ['alpha.test', 'zeta.test'], ['atelier.name'], ['name', 'ca', 'state'], 'ca'],
    ['dns', () => <DnsProvidersTab dnsProviders={PROVIDERS} onAddProvider={noop} onEditProvider={noop} onTestProvider={noop} onDeleteProvider={noop} canWrite canDelete />,
      ['Zone A', 'Zone B'], ['atelier.name'], ['name', 'type', 'default', 'state'], 'type'],
    ['upstream', () => <CaAccountsManager accounts={UPSTREAM} canWrite canDelete onCreate={noop} onUpdate={noop} onDelete={noop} />,
      ['Actalis', 'ZeroSSL'], ['acme.directoryUrl'], ['name', 'directory', 'email', 'default', 'proxy', 'state'], 'directory'],
  ])('%s: by name from the first render, every column sorting, the sort in the address', (tabName, ui, names, grows, keys, second) => {
    const view = at(ui(), `/acme?tab=${tabName}`)
    expect(rowNames(view.container)).toEqual(names)
    expect(sortedHeaders(view.container)).toEqual([['atelier.name', 'ascending']])
    expect(absorbers(view.container)).toEqual(grows)
    expect(sortKeys(view.container)).toEqual(keys)
    fireEvent.click(view.container.querySelector(`thead button[data-sort="${second}"]`))
    expect(view.where()).toBe(`/acme?tab=${tabName}&sort=${second}&order=asc`)
    fireEvent.click(view.container.querySelector('thead button[data-sort="name"]'))
    fireEvent.click(view.container.querySelector('thead button[data-sort="name"]'))
    expect(rowNames(view.container)).toEqual([...names].reverse())
  })

  it('says a DNS provider is the default in words, its state pill saying only active or disabled', () => {
    const view = at(<DnsProvidersTab dnsProviders={[{ id: 1, name: 'Zone A', provider_type: 'hetzner', is_default: true }]} onAddProvider={noop}
      providerTypes={[{ type: 'hetzner', name: 'Hetzner' }]} onEditProvider={noop} onTestProvider={noop} onDeleteProvider={noop} canWrite canDelete />, '/acme?tab=dns')
    const row = view.container.querySelector('tbody tr')
    expect(row.querySelector('.badge')).toHaveTextContent('common.active')
    expect(row).toHaveTextContent('common.yes')
    // The type by its provider's name, never its code
    expect(row).toHaveTextContent('Hetzner')
    expect(row).not.toHaveTextContent('hetzner')
  })

  it('reads a sort from the address and keeps a whole URL in its title', () => {
    const view = at(<CaAccountsManager accounts={UPSTREAM} canWrite canDelete onCreate={noop} onUpdate={noop} onDelete={noop} />, '/acme?tab=upstream&sort=state&order=asc')
    expect(sortedHeaders(view.container)).toEqual([['atelier.state', 'ascending']])
    expect(rowNames(view.container)).toEqual(['ZeroSSL', 'Actalis'])
    expect(view.container.querySelector('td[title="https://acme-api.actalis.com/acme/directory"]')).not.toBeNull()
  })

  it('names every fact of a phone record whose value does not say what it is', () => {
    mocks.mobile.isMobile = true
    const view = at(<DomainsTab acmeDomains={DOMAINS} onAdd={noop} onEdit={noop} onDelete={noop} onTest={noop} canWrite canDelete />, '/acme?tab=domains')
    expect(recordFacts(view.container)[0]).toEqual(['acme.provider route53', 'acme.issuingCA A CA', 'acme.wildcard common.no'])
  })
})

describe('the EAB credentials', () => {
  const cred = (i) => ({
    id: i, kid: `kid-${String(i).padStart(3, '0')}`, label: `cred-${String(i).padStart(3, '0')}`, status: 'active', allowed_domains: ['*'],
    created_at: new Date(Date.UTC(2026, 0, 1) + i * 3600e3).toISOString(),
  })
  const ALL = Array.from({ length: 230 }, (_, i) => cred(i + 1))
  const tab = () => <EabTab eabRequired={false} onToggleEabRequired={vi.fn()} showCreateModal={false} onCloseCreateModal={vi.fn()} canWrite canDelete />

  beforeEach(() => {
    mocks.listEab.mockImplementation(async (_status, { page = 1, per_page = 200 } = {}) => ({
      data: ALL.slice((page - 1) * per_page, page * per_page), meta: { total: ALL.length, page, per_page },
    }))
  })

  it('reads every page and opens on the newest credential, the allowed domains taking the room left', async () => {
    const view = at(tab(), '/acme?tab=eab')
    await screen.findByRole('button', { name: 'cred-230' })
    expect(mocks.listEab.mock.calls.map(([, p]) => p.page).sort()).toEqual([1, 2])
    expect(rowNames(view.container)[0]).toBe('cred-230')
    expect(sortedHeaders(view.container)).toEqual([['acme.eab.created', 'descending']])
    expect(absorbers(view.container)).toEqual(['acme.eab.allowedDomains'])
    expect(sortKeys(view.container)).toEqual(['name', 'kid', 'domains', 'created', 'state'])
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    expect(view.where()).toBe('/acme?tab=eab&sort=name&order=asc')
    expect(rowNames(view.container)[0]).toBe('cred-001')
  })

  it('says the list is partial when a page cannot be read', async () => {
    const whole = mocks.listEab.getMockImplementation()
    mocks.listEab.mockImplementation(async (s, p) => (p.page === 2 ? Promise.reject(new Error('gone')) : whole(s, p)))
    at(tab(), '/acme?tab=eab')
    expect(await screen.findByText('acme.eab.listPartial')).toBeInTheDocument()
  })
})
