/**
 * Discovery as the mockup's discovery module draws it: the analyses (Plage, Trouvés, Dernière
 * analyse, État) read off the profiles and their last run, the analysis dock and its actions, the
 * analysis and quick scan dialogs and the targets they refuse, then the product's found
 * certificates and run history, the removal a permission allows, and the read failure.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: ['*'] }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && opts.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'fr', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn() }))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useAuth: () => ({ user: { id: 1, username: 'probe' }, permissions: authState.permissions }),
  useMobile: () => ({ isMobile: false }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: authState.permissions }) }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => vi.fn() }))
vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))
const svc = vi.hoisted(() => ({
  getStats: vi.fn(), getProfiles: vi.fn(), getAll: vi.fn(), getRuns: vi.fn(), getById: vi.fn(),
  scan: vi.fn(), scanProfile: vi.fn(), delete: vi.fn(), deleteAll: vi.fn(),
  createProfile: vi.fn(), updateProfile: vi.fn(), deleteProfile: vi.fn(), bulkResolveDns: vi.fn(), export: vi.fn(),
}))
vi.mock('../../services', () => ({ discoveryService: svc }))

import { renderAtUrl } from '../../test/dockUrl'
import DiscoveryPage from '../DiscoveryPage'
import { targetProblem } from '../discovery/discoveryModel'

const PROFILES = [
  { id: 1, name: 'Réseau A', targets: ['192.0.2.0/24'], ports: [443], schedule_enabled: true, schedule_interval_minutes: 1440, description: 'Serveurs du site' },
  { id: 2, name: 'Réseau B', targets: ['198.51.100.0/24', 'web.example.com', 'mail.example.com'], ports: [443, 8443], schedule_enabled: true, next_scan_at: '2026-12-09T04:00:00Z' },
  { id: 3, name: 'Sous-domaines', targets: ['www.example.com'], ports: [443], schedule_enabled: false },
]
const RUNS = [
  { id: 10, scan_profile_id: 1, profile_name: 'Réseau A', status: 'completed', certs_found: 14, new_certs: 2, targets_scanned: 254, started_at: '2026-11-08T04:00:00Z' },
  { id: 9, scan_profile_id: 1, profile_name: 'Réseau A', status: 'failed', certs_found: 0, started_at: '2026-11-07T04:00:00Z' },
  { id: 11, scan_profile_id: 3, profile_name: 'Sous-domaines', status: 'failed', certs_found: 0, started_at: '2026-11-08T05:00:00Z' },
  { id: 12, scan_profile_id: null, profile_name: null, status: 'completed', certs_found: 1, started_at: '2026-11-09T05:00:00Z' },
]
const FOUND = [
  { id: 5, target: '192.0.2.10', port: 443, status: 'unmanaged', subject: 'CN=intranet.example.com,O=Example', issuer: 'CN=Old CA', not_after: '2027-01-01T00:00:00Z' },
  { id: 6, target: '192.0.2.11', port: 443, status: 'error', scan_error: 'Connection refused' },
]
const names = () => [...document.querySelectorAll('tbody .entity-name')].map((b) => b.textContent)
const renderAt = (url = '/discovery') => render(<MemoryRouter initialEntries={[url]}><DiscoveryPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  authState.permissions = ['*']
  svc.getProfiles.mockResolvedValue({ data: PROFILES })
  svc.getRuns.mockResolvedValue({ data: RUNS })
  svc.getAll.mockResolvedValue({ data: { items: FOUND, total: 2 } })
  svc.getStats.mockResolvedValue({ data: { total: 2, managed: 0, unmanaged: 1, errors: 1 } })
  svc.getById.mockResolvedValue({ data: {} })
  for (const k of ['scan', 'scanProfile', 'delete', 'deleteAll', 'createProfile', 'updateProfile', 'deleteProfile']) svc[k].mockResolvedValue({ data: {} })
})

describe('DiscoveryPage analyses (the mockup module list)', () => {
  it('lists the analyses with their range, findings, last analysis and the state of their last run', async () => {
    renderAt()
    await screen.findByRole('button', { name: 'Réseau A' })
    expect(screen.getByRole('heading', { level: 1, name: 'shell.moduleLabel.discovery' })).toBeInTheDocument()
    expect(screen.getByText('discovery.scans.unit:3')).toBeInTheDocument()
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual(
      ['atelier.name', 'discovery.form.range', 'discovery.scans.found', 'discovery.scans.last', 'atelier.state', 'common.actions'])
    const row = (name) => screen.getByRole('button', { name }).closest('tr')
    // The newest run counts: Réseau A's failure of the 7th is behind its completion of the 8th
    expect(row('Réseau A')).toHaveTextContent('discovery.scans.foundNew:14')
    expect(row('Réseau A')).toHaveTextContent('discovery.scans.state.done')
    expect(row('Réseau B')).toHaveTextContent('198.51.100.0/24, web.example.com +1')
    expect(row('Réseau B')).toHaveTextContent('discovery.scans.notScanned')
    expect(row('Réseau B')).toHaveTextContent('discovery.scans.state.scheduled')
    expect(row('Sous-domaines')).toHaveTextContent('discovery.scans.interrupted')
    const chips = within(screen.getByRole('group', { name: 'discovery.filterByState' })).getAllByRole('button')
    expect(chips.map((b) => b.textContent)).toEqual(['common.all3', 'discovery.scans.state.done1', 'discovery.scans.state.failed1', 'discovery.scans.state.scheduled1'])
    fireEvent.click(chips[2])
    expect(names()).toEqual(['Sous-domaines'])
  })

  it('opens an analysis in its dock, runs it and deletes it after the confirmation', async () => {
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'Réseau A' }))
    const dock = screen.getByRole('complementary', { name: 'atelier.detailOf' })
    expect(within(dock).getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['atelier.overview', 'discovery.scans.runsTab'])
    expect(within(dock).getByText('Serveurs du site')).toBeInTheDocument()
    fireEvent.click(within(dock).getByRole('button', { name: 'discovery.scans.runNow' }))
    await waitFor(() => expect(svc.scanProfile).toHaveBeenCalledWith(1))
    fireEvent.click(within(dock).getByRole('tab', { name: 'discovery.scans.runsTab' }))
    expect(within(dock).getAllByRole('listitem')).toHaveLength(2)
    fireEvent.click(within(dock).getByRole('button', { name: 'common.delete…' }))
    const dialog = await screen.findByTestId('discovery-remove-dialog')
    expect(svc.deleteProfile).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(svc.deleteProfile).toHaveBeenCalledWith(1))
  })

  it('creates an analysis, refusing a DNS wildcard, an IPv6 range and a range past the scanner cap', async () => {
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'discovery.scans.create' }))
    const dialog = await screen.findByTestId('scan-profile-dialog')
    const targets = within(dialog).getByLabelText('discovery.form.range')
    fireEvent.change(within(dialog).getByLabelText('common.name'), { target: { value: 'DMZ' } })
    for (const [value, problem] of [['*.example.com', 'wildcard'], ['2001:db8::/64', 'ipv6Range'], ['10.0.0.0/8', 'tooWide']]) {
      fireEvent.change(targets, { target: { value } })
      expect(within(dialog).getByText(`discovery.form.problem.${problem}`)).toBeInTheDocument()
      expect(targets).toHaveAttribute('aria-invalid', 'true')
      expect(within(dialog).getByRole('button', { name: 'common.create' })).toBeDisabled()
    }
    fireEvent.change(targets, { target: { value: '192.0.2.0/24\nweb.example.com' } })
    fireEvent.change(within(dialog).getByLabelText('discovery.form.preset'), { target: { value: 'alt' } })
    fireEvent.change(within(dialog).getByLabelText('discovery.schedule'), { target: { value: '1440' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.create' }))
    await waitFor(() => expect(svc.createProfile).toHaveBeenCalled())
    expect(svc.createProfile.mock.calls[0][0]).toMatchObject({
      name: 'DMZ', targets: ['192.0.2.0/24', 'web.example.com'], ports: [443, 8443], schedule_interval_minutes: 1440, schedule_enabled: true,
    })
  })

  it('runs a quick scan once, saved nowhere', async () => {
    renderAt()
    fireEvent.click((await screen.findAllByRole('button', { name: 'discovery.quickScanAsk' }))[0])
    const dialog = await screen.findByTestId('quick-scan-dialog')
    expect(within(dialog).queryByLabelText('common.name')).toBeNull()
    fireEvent.change(within(dialog).getByLabelText('discovery.form.range'), { target: { value: 'web.example.com, 192.0.2.7' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'discovery.startScan' }))
    await waitFor(() => expect(svc.scan).toHaveBeenCalled())
    expect(svc.scan.mock.calls[0][0]).toMatchObject({ targets: ['web.example.com', '192.0.2.7'], ports: [443] })
    expect(svc.createProfile).not.toHaveBeenCalled()
  })

  it('offers no scan, analysis or change without admin:system', async () => {
    authState.permissions = ['read:certificates']
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'Réseau A' }))
    expect(screen.queryByRole('button', { name: 'discovery.scans.create' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'discovery.quickScanAsk' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'discovery.scans.runNow' })).toBeNull()
  })

  it('says why the list is empty, and shows a read failure with Réessayer', async () => {
    svc.getProfiles.mockResolvedValueOnce({ data: [] })
    svc.getRuns.mockResolvedValueOnce({ data: [] })
    const { unmount } = renderAt()
    expect(await screen.findByText('discovery.scans.empty')).toBeInTheDocument()
    unmount()
    svc.getProfiles.mockRejectedValueOnce(Object.assign(new Error('Service Unavailable'), { status: 503 }))
    renderAt()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('discovery.errors.loadFailed')
    expect(within(alert).getByRole('link', { name: /work.viewLog/ })).toHaveAttribute('href', '/audit')
    fireEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    expect(await screen.findByRole('button', { name: 'Réseau A' })).toBeInTheDocument()
  })
})

describe('DiscoveryPage found certificates and history (the product views)', () => {
  it('switches to the found certificates, names them by CN or by host when unreachable, and filters on the server', async () => {
    renderAt()
    fireEvent.click((await screen.findAllByRole('button', { name: 'discovery.views.discovered' }))[0])
    expect(await screen.findByRole('button', { name: 'intranet.example.com' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '192.0.2.11:443' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('group', { name: 'discovery.filterByState' })).getByRole('button', { name: /discovery.found.state.unmanaged/ }))
    await waitFor(() => expect(svc.getAll.mock.calls.at(-1)[0].status).toEqual(['unmanaged']))
  })

  it('offers the removal of a found certificate on delete:certificates only', async () => {
    authState.permissions = ['read:certificates']
    const { unmount } = renderAt('/discovery?tab=discovered')
    fireEvent.click(await screen.findByRole('button', { name: 'intranet.example.com' }))
    expect(screen.queryByRole('button', { name: /common.delete/ })).toBeNull()
    unmount()
    authState.permissions = ['read:certificates', 'delete:certificates']
    renderAt('/discovery?tab=discovered')
    fireEvent.click(await screen.findByRole('button', { name: 'intranet.example.com' }))
    fireEvent.click(within(screen.getByRole('complementary', { name: 'atelier.detailOf' })).getByRole('button', { name: 'common.delete…' }))
    fireEvent.click(within(await screen.findByTestId('discovery-remove-dialog')).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(svc.delete).toHaveBeenCalledWith(5))
  })

  it('explains an unreachable target in its dock and retries it for admin:system', async () => {
    renderAt('/discovery?tab=discovered')
    fireEvent.click(await screen.findByRole('button', { name: '192.0.2.11:443' }))
    const dock = screen.getByRole('complementary', { name: 'atelier.detailOf' })
    expect(within(dock).getByRole('note')).toHaveTextContent('discovery.errorHintRefused')
    fireEvent.click(within(dock).getByRole('button', { name: 'discovery.retry' }))
    await waitFor(() => expect(svc.scan).toHaveBeenCalledWith({ targets: ['192.0.2.11:443'], ports: [443], timeout: 10 }))
  })

  it('lists the runs newest first, a quick scan under its own name', async () => {
    renderAt('/discovery?tab=history')
    await screen.findByRole('button', { name: 'discovery.adHocScan' })
    expect(names()).toEqual(['discovery.adHocScan', 'Sous-domaines', 'Réseau A', 'Réseau A'])
  })
})

describe('targetProblem', () => {
  it('lets hosts, addresses, ports and IPv4 ranges within the scanner cap through', () => {
    for (const ok of ['web.example.com', '192.0.2.7', 'mail.example.com:465', '192.0.2.0/24', '10.0.0.0/16', '[2001:db8::1]:443']) expect(targetProblem(ok)).toBeNull()
  })
  it('names what it refuses', () => {
    expect(targetProblem('*.example.com')).toBe('wildcard')
    expect(targetProblem('2001:db8::/64')).toBe('ipv6Range')
    expect(targetProblem('10.0.0.0/15')).toBe('tooWide')
    expect(targetProblem('192.0.2.0/33')).toBe('format')
    expect(targetProblem('web example')).toBe('format')
  })
})

describe('the discovery dock in the URL', () => {
  it('reopens the scan and section of the URL, writes the one opened, and a view change closes it', async () => {
    const r = renderAtUrl(<DiscoveryPage />, '/discovery?item=2&section=runs')
    const dock = await r.dock()
    expect(within(dock).getByRole('tab', { name: 'discovery.scans.runsTab' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Réseau B')
    fireEvent.click(screen.getByRole('button', { name: 'Réseau A' }))
    expect(r.where()).toBe('/discovery?item=1')
    fireEvent.click(r.container.querySelector('[data-view="history"]'))
    await waitFor(() => expect(r.where()).toBe('/discovery?tab=history'))
  })
})
