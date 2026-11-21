/**
 * HSM page as the mockup's hsm module draws it: the list (Type, Clés, Dernier contrôle, État)
 * with its state chips, search and type filter, the one-object dock with its tabs and actions,
 * the empty and error states, and the actions each permission allows.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: 'fr', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(true),
}))
const perms = vi.hoisted(() => ({ write: true, del: true }))
vi.mock('../../contexts', () => ({ useNotification: () => notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ canWrite: () => perms.write, canDelete: () => perms.del, hasPermission: () => true, canRead: () => true }),
    useClipboard: () => ({ copy: vi.fn(), isCopied: () => false }),
  }
})
vi.mock('../../lib/policyAlgorithms', () => ({ useFipsMode: () => false, useKeyPlatform: () => ({ fips: false, fipsKeys: null }) }))
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

const svc = vi.hoisted(() => ({
  getProviders: vi.fn(), getStatus: vi.fn(), getKeys: vi.fn(), getProvider: vi.fn(), testProvider: vi.fn(), deleteKey: vi.fn(), deleteProvider: vi.fn(),
}))
vi.mock('../../services', () => ({ hsmService: svc }))

import { renderAtUrl } from '../../test/dockUrl'
import HSMPage from '../HSMPage'

const P = [
  { id: 1, name: 'Partition 1', provider_type: 'pkcs11', status: 'connected', key_count: 2, last_tested_at: '2026-11-08T11:58:00Z', error_message: null },
  { id: 2, name: 'Bao transit', provider_type: 'openbao', status: 'error', key_count: 0, last_tested_at: null, error_message: 'connection refused',
    openbao_url: 'https://bao.example:8200' },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  perms.write = true
  perms.del = true
  svc.getProviders.mockResolvedValue({ data: P })
  svc.getStatus.mockResolvedValue({ data: { ready: true } })
  svc.getKeys.mockResolvedValue({ data: [{ id: 9, label: 'ca-root', algorithm: 'RSA-3072', purpose: 'signing' }] })
  notify.showConfirm.mockResolvedValue(true)
})

const rowOf = (name) => screen.getAllByRole('row').find((r) => within(r).queryByRole('button', { name }))

describe('the HSM list', () => {
  it('draws the head, the state chips and the four columns of the mockup', async () => {
    const { container } = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Partition 1' })
    expect(container.querySelector('.atl h1#main-title')).toHaveTextContent('shell.moduleLabel.hsm')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('hsm.unit {"count":2}')
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'hsm.columns.type', 'hsm.columns.keys', 'hsm.columns.checked', 'atelier.state', 'common.actions'])
    const chips = within(screen.getByRole('group', { name: 'hsm.filterByState' })).getAllByRole('button').map((b) => b.textContent)
    expect(chips).toEqual(['common.all2', 'hsm.states.connected1', 'hsm.states.error1'])
    expect(container.querySelector('footer.table-footer')).toHaveTextContent('hsm.range {"shown":2,"count":2}')
  })

  it('reads the last test date and the state the server records (last_tested_at, status)', async () => {
    render(<MemoryRouter><HSMPage /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Partition 1' })
    expect(rowOf('Partition 1')).toHaveTextContent('8 nov. 2026, 11:58')
    expect(rowOf('Partition 1')).toHaveTextContent('hsm.states.connected')
    expect(rowOf('Bao transit')).toHaveTextContent('hsm.never')
    expect(rowOf('Bao transit')).toHaveTextContent('hsm.states.error')
  })

  it('filters by state, by type and by search, and puts everything back from the no-match block', async () => {
    render(<MemoryRouter><HSMPage /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Partition 1' })
    fireEvent.click(screen.getByRole('button', { name: /hsm\.states\.error/ }))
    expect(screen.queryByRole('button', { name: 'Partition 1' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Bao transit' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /common\.all/ }))
    fireEvent.change(screen.getByRole('combobox', { name: 'hsm.filterByType' }), { target: { value: 'pkcs11' } })
    expect(screen.queryByRole('button', { name: 'Bao transit' })).toBeNull()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })
    expect(screen.getByText('table.noResults')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'table.clearFilters' }))
    expect(screen.getByRole('button', { name: 'Partition 1' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Bao transit' })).toBeTruthy()
  })

  it('says why the list is empty and offers the creation to who may write', async () => {
    svc.getProviders.mockResolvedValue({ data: [] })
    const { unmount } = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    expect(await screen.findByText('hsm.noHSM')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'hsm.newProvider' })).toHaveLength(2)
    unmount()
    perms.write = false
    render(<MemoryRouter><HSMPage /></MemoryRouter>)
    await screen.findByText('hsm.noHSM')
    expect(screen.queryByRole('button', { name: 'hsm.newProvider' })).toBeNull()
  })

  it('shows a failed read with its cause and reads again on Réessayer', async () => {
    svc.getProviders.mockRejectedValueOnce(Object.assign(new Error('down'), { status: 503 }))
    render(<MemoryRouter><HSMPage /></MemoryRouter>)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('messages.errors.loadFailed.hsmProviders')
    fireEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    expect(await screen.findByRole('button', { name: 'Partition 1' })).toBeTruthy()
    expect(svc.getProviders).toHaveBeenCalledTimes(2)
  })

  it('warns about the missing PKCS#11 dependencies only when a local PKCS#11 provider exists', async () => {
    svc.getStatus.mockResolvedValue({ data: { ready: false, pkcs11_installed: false, softhsm_found: true, install_command: 'pip install python-pkcs11' } })
    const { container, unmount } = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    await waitFor(() => expect(container.querySelector('#hsm-pkcs11-notice')).toHaveTextContent('hsm.pkcs11Missing'))
    unmount()
    svc.getProviders.mockResolvedValue({ data: [P[1]] })
    const second = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Bao transit' })
    expect(second.container.querySelector('#hsm-pkcs11-notice')).toBeNull()
  })
})

describe('the HSM dock', () => {
  it('opens a provider with its overview, the server error, its keys and its configuration', async () => {
    const { container } = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Bao transit' }))
    const dock = container.querySelector('aside#inspector')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Bao transit')
    expect(dock.querySelector('#hsm-error')).toHaveTextContent('connection refused')
    expect(within(dock).getAllByRole('tab').map((x) => x.textContent)).toEqual(['atelier.overview', 'hsm.hsmKeys', 'common.config'])
    await waitFor(() => expect(dock.querySelector('.summary')).toHaveTextContent('hsm.summaryKeys {"names":"ca-root"}'))
    fireEvent.click(within(dock).getByRole('tab', { name: 'hsm.hsmKeys' }))
    expect(within(dock).getByText('ca-root')).toBeTruthy()
    expect(within(dock).getByText('RSA-3072 · signing')).toBeTruthy()
    fireEvent.click(within(dock).getByRole('button', { name: 'hsm.deleteKey {"name":"ca-root"}' }))
    await waitFor(() => expect(svc.deleteKey).toHaveBeenCalledWith(9))
    fireEvent.click(within(dock).getByRole('tab', { name: 'common.config' }))
    expect(within(dock).getByText('https://bao.example:8200')).toBeTruthy()
    expect(rowOf('Bao transit')).toHaveClass('opened')
  })

  it('gives each action to the permission it needs', async () => {
    perms.write = false
    perms.del = false
    const { container } = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Partition 1' }))
    const dock = container.querySelector('aside#inspector')
    expect(within(dock).getByRole('button', { name: 'common.test' })).toBeTruthy()
    for (const name of ['common.syncKeys', 'common.edit', 'hsm.deleteProvider']) expect(within(dock).queryByRole('button', { name })).toBeNull()
    fireEvent.click(within(dock).getByRole('tab', { name: 'hsm.hsmKeys' }))
    await within(dock).findByText('ca-root')
    expect(within(dock).queryByRole('button', { name: 'common.generate' })).toBeNull()
    expect(within(dock).queryByRole('button', { name: /hsm\.deleteKey/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'hsm.newProvider' })).toBeNull()
  })

  it('tests a provider and shows what the server read, then closes on Fermer', async () => {
    svc.testProvider.mockResolvedValue({ data: { success: true, message: 'ok' } })
    svc.getProvider.mockResolvedValue({ data: { ...P[0], module_info: { library: 'SoftHSM', manufacturer: 'OpenDNSSEC', library_version: '2.6', firmware_version: '2.6' } } })
    const { container } = render(<MemoryRouter><HSMPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Partition 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'common.test' }))
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('ok'))
    expect(await screen.findByText('OpenDNSSEC')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'inspector.close' }))
    expect(container.querySelector('aside#inspector')).toBeNull()
  })
})

describe('the provider dock in the URL', () => {
  it('reopens the provider and section of the URL with its keys, then writes the one opened', async () => {
    const r = renderAtUrl(<HSMPage />, '/hsm?item=2&section=config')
    const dock = await r.dock()
    expect(within(dock).getByRole('tab', { name: 'common.config' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Bao transit')
    fireEvent.click(screen.getByRole('button', { name: 'Partition 1' }))
    expect(r.where()).toBe('/hsm?item=1')
    fireEvent.click(within(await r.dock()).getByRole('tab', { name: 'hsm.hsmKeys' }))
    expect(r.where()).toBe('/hsm?item=1&section=keys')
  })
})
