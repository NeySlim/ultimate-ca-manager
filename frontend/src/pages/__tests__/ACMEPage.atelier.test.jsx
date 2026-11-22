/**
 * ACME as the mockup's acme module draws it: the accounts list (Contact, Créé le, État, Commandes)
 * with its chips and search, Copier l'URL du répertoire in the head, the account dock on its three
 * tabs, the page switch to the product's other views (kept in ?tab=), and the rights.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { notificationSpies } from './pageRenderingSetup.jsx'
import { acmeService } from '../../services/acme.service'

const perms = vi.hoisted(() => ({ write: true }))
const clip = vi.hoisted(() => ({ copy: vi.fn().mockResolvedValue(true) }))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ hasPermission: () => perms.write, canRead: () => true, canWrite: () => perms.write, canDelete: () => perms.write, isAdmin: () => perms.write }),
}))
vi.mock('../../hooks/useClipboard', () => ({ useClipboard: () => clip }))

import ACMEPage from '../ACMEPage'
import { paletteViews } from '../../navigation/registry'

const ok = (data) => vi.fn().mockResolvedValue({ data })
const ACCOUNTS = [
  { id: 5, account_id: 'abcdefghijklmnop', contact: ['mailto:ops@example.com'], status: 'valid', orders_count: 2, key_type: 'EC-P256', created_at: '2026-01-15T00:00:00Z' },
  { id: 6, account_id: 'zyxwvutsrqponmlk', contact: [], status: 'deactivated', orders_count: 0, created_at: '2026-02-01T00:00:00Z' },
]
const ORDERS = [{ id: 40, order_id: 'ord-123456789012345', domain: 'www.example.com', status: 'Invalid', method: 'HTTP-01', created_at: '2026-11-08T05:40:00Z' }]
const CHALLENGES = [
  { id: 1, type: 'DNS-01', domain: 'www.example.com', status: 'Valid' },
  { id: 2, type: 'HTTP-01', domain: 'www.example.com', status: 'Invalid' },
]

let location
const Where = () => { location = useLocation(); return null }
const at = (path) => render(<MemoryRouter initialEntries={[path]}><Where /><ACMEPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  perms.write = true
  notificationSpies.showConfirm = vi.fn().mockResolvedValue(true)
  Object.assign(acmeService, {
    getSettings: ok({ acme_public_base_url: 'https://pki.example.com/acme' }), getHistory: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    getClientSettings: ok({}), getDnsProviders: ok([]), getDnsProviderTypes: ok([]), getDomains: ok([]), getLocalDomains: ok([]),
    getEabRequired: ok({ eab_required: false }), getCaAccounts: ok([]), getClientOrders: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    getAccounts: ok(ACCOUNTS), getAccountById: vi.fn(async (id) => ({ data: ACCOUNTS.find((a) => a.id === id) })),
    getOrders: ok(ORDERS), getChallenges: ok(CHALLENGES), deleteAccount: vi.fn().mockResolvedValue({}),
  })
})

describe('the ACME accounts', () => {
  it('draws the mockup list: the account short name, chips with counters, the columns the product has', async () => {
    at('/acme')
    await screen.findByRole('button', { name: 'acct/abcdefghijkl' })
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'acme.contact', 'acme.createdOn', 'atelier.state', 'acme.columns.orders', 'common.actions'])
    const chips = within(screen.getByRole('group', { name: 'acme.filterByState' })).getAllByRole('button').map((b) => b.textContent)
    expect(chips).toEqual(['common.all2', 'acme.accountStates.valid1', 'acme.accountStates.deactivated1'])
    const row = screen.getByRole('button', { name: 'acct/abcdefghijkl' }).closest('tr')
    expect(row).toHaveTextContent('ops@example.com')
    expect(row).toHaveTextContent('acme.accountState.valid')
    expect(row).toHaveTextContent('2')
  })

  it('filters by chip and by search', async () => {
    at('/acme')
    await screen.findByRole('button', { name: 'acct/abcdefghijkl' })
    fireEvent.click(within(screen.getByRole('group', { name: 'acme.filterByState' })).getByRole('button', { name: /deactivated/ }))
    expect(screen.queryByRole('button', { name: 'acct/abcdefghijkl' })).toBeNull()
    fireEvent.click(within(screen.getByRole('group', { name: 'acme.filterByState' })).getByRole('button', { name: /common.all/ }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ops@' } })
    expect(screen.getByRole('button', { name: 'acct/abcdefghijkl' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'acct/zyxwvutsrqpo' })).toBeNull()
  })

  it('sorts its columns from their headers and pages a long list by 25', async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({
      id: 100 + i, account_id: `bulk${String(i).padStart(12, '0')}`, contact: [`mailto:a${i}@example.com`], status: 'valid', orders_count: i + 3, created_at: `2026-03-${String(i + 1).padStart(2, '0')}T00:00:00Z`,
    }))
    acmeService.getAccounts = ok([...ACCOUNTS, ...many])
    const { container } = at('/acme')
    // The newest account first: the two of January and February are on the second page
    await screen.findAllByRole('button', { name: 'acct/bulk00000000' })
    const footer = container.querySelector('footer.table-footer')
    const bodyRows = () => container.querySelectorAll('tbody tr')
    expect(bodyRows()).toHaveLength(25)
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(bodyRows()).toHaveLength(7)
    fireEvent.click(screen.getByRole('button', { name: 'acme.orders' }))
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.click(screen.getByRole('button', { name: 'acme.orders' }))
    expect(screen.getByRole('button', { name: 'acme.orders' }).closest('th')).toHaveAttribute('aria-sort', 'descending')
    expect(bodyRows()[0]).toHaveTextContent('a29@example.com')
    fireEvent.click(screen.getByRole('button', { name: 'acme.createdOn' }))
    expect(bodyRows()[0]).toHaveTextContent('ops@example.com')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    expect(bodyRows()[0]).toHaveTextContent('acme.accountState.deactivated')
    for (const name of ['atelier.name', 'acme.contact']) expect(screen.getByRole('button', { name })).toBeInTheDocument()
    // A search goes back to page one, and a short result has no page controls
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'bulk' } })
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ops@' } })
    expect(within(footer).queryByRole('button', { name: 'table.nextPage' })).toBeNull()
  })

  it('shows a read error in place of the list, with a retry and the journal for who may read it', async () => {
    acmeService.getAccounts = vi.fn().mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 503 })).mockResolvedValue({ data: ACCOUNTS })
    at('/acme')
    const error = await screen.findByRole('alert')
    expect(error).toHaveTextContent('messages.errors.loadFailed.acme')
    expect(within(error).getByRole('link')).toHaveAttribute('href', '/audit')
    fireEvent.click(within(error).getByRole('button', { name: 'table.retry' }))
    expect(await screen.findByRole('button', { name: 'acct/abcdefghijkl' })).toBeInTheDocument()
  })

  it('offers the directory URL from the empty list, as the mockup does', async () => {
    acmeService.getAccounts = ok([])
    at('/acme')
    const empty = await screen.findByText('acme.emptyAccountsTitle')
    fireEvent.click(within(empty.closest('.empty')).getByRole('button', { name: 'acme.copyDirectory' }))
    await waitFor(() => expect(clip.copy).toHaveBeenCalledWith('https://pki.example.com/acme/directory'))
  })

  it('copies the directory URL from the head', async () => {
    at('/acme')
    fireEvent.click(await screen.findByRole('button', { name: 'acme.copyDirectory' }))
    await waitFor(() => expect(clip.copy).toHaveBeenCalledWith('https://pki.example.com/acme/directory'))
  })

  it('opens the account dock on Compte, then its orders and challenges', async () => {
    at('/acme')
    fireEvent.click(await screen.findByRole('button', { name: 'acct/abcdefghijkl' }))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(within(dock).getAllByRole('tab').map((t) => t.textContent)).toEqual(['acme.tabs.account', 'acme.orders', 'common.challenges'])
    expect(await within(dock).findByText(/acme.ordersFailing/)).toBeInTheDocument()
    fireEvent.click(within(dock).getByRole('tab', { name: 'acme.orders' }))
    expect(within(dock).getByText(/www.example.com/)).toBeInTheDocument()
    fireEvent.click(within(dock).getByRole('tab', { name: 'common.challenges' }))
    expect(within(dock).getByText('acme.challengeTxt')).toBeInTheDocument()
    expect(within(dock).getByText('http://www.example.com/.well-known/acme-challenge/')).toBeInTheDocument()
  })

  it('keeps the account actions and the new account from an operator without write:acme', async () => {
    perms.write = false
    at('/acme')
    fireEvent.click(await screen.findByRole('button', { name: 'acct/abcdefghijkl' }))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(within(dock).queryByRole('button', { name: 'acme.disableAccount' })).toBeNull()
    expect(within(dock).queryByRole('button', { name: 'common.delete' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'acme.newAccount' })).toBeNull()
  })

  it('removes an account after its confirmation', async () => {
    at('/acme')
    fireEvent.click(await screen.findByRole('button', { name: 'acct/abcdefghijkl' }))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    fireEvent.click(within(dock).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(acmeService.deleteAccount).toHaveBeenCalledWith(5))
  })
})

describe('the ACME views', () => {
  it('shows its views as tabs under the head, grouped, the accounts counted', async () => {
    at('/acme')
    const list = await screen.findByRole('tablist', { name: 'protocols.view' })
    expect(within(list).getAllByRole('tab').map((b) => b.id.replace('acme-view-tab-', ''))).toEqual([
      'accounts', 'localorders', 'localdomains', 'eab', 'config', 'letsencrypt', 'letsencryptorders', 'upstream', 'dns', 'domains', 'history',
    ])
    await waitFor(() => expect(within(list).getByRole('tab', { name: /^acme\.views\.accounts/ })).toHaveTextContent('acme.views.accounts2'))
    expect(within(list).getByRole('tab', { name: /^acme\.views\.dns/ })).toHaveAccessibleDescription('acme.groups.client')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'acme-view-tab-accounts')
    // The head keeps its actions only: no select left in it
    expect(document.querySelector('.page-head select')).toBeNull()
  })

  it('keeps the view in the address, the former tab names included', async () => {
    at('/acme')
    fireEvent.click(await screen.findByRole('tab', { name: /^acme\.views\.history/ }))
    expect(location.search).toBe('?tab=history')
    expect(await screen.findByRole('button', { name: 'table.exportData' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /^acme\.views\.accounts/ }))
    expect(location.search).toBe('')
  })

  it('opens a view named by a former tab', async () => {
    at('/acme?tab=localdomains')
    expect(await screen.findByRole('tab', { name: /^acme\.views\.localdomains/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('moves between its views with the arrows', async () => {
    at('/acme?tab=domains')
    const tab = await screen.findByRole('tab', { name: /^acme\.views\.domains/ })
    fireEvent.keyDown(tab, { key: 'ArrowRight' })
    expect(location.search).toBe('?tab=history')
    fireEvent.keyDown(screen.getByRole('tab', { name: /^acme\.views\.history/ }), { key: 'Home' })
    expect(location.search).toBe('')
  })

  it('the palette offers each view past the first, as the tabs name and order them', async () => {
    at('/acme')
    const tabs = within(await screen.findByRole('tablist', { name: 'protocols.view' })).getAllByRole('tab')
    expect(paletteViews().filter((v) => v.path.startsWith('/acme?')).map((v) => [v.path, v.labelKey]))
      .toEqual(tabs.slice(1).map((b) => {
        const tab = b.id.replace('acme-view-tab-', '')
        return [`/acme?tab=${tab}`, `acme.views.${tab}`]
      }))
  })
})

describe('the ACME docks in the URL', () => {
  it('writes the account opened and its section', async () => {
    at('/acme')
    fireEvent.click(await screen.findByRole('button', { name: 'acct/abcdefghijkl' }))
    await waitFor(() => expect(location.search).toBe('?item=5'))
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    fireEvent.click(within(dock).getByRole('tab', { name: 'acme.orders' }))
    expect(location.search).toBe('?item=5&section=orders')
  })

  it('reopens an account and its section on reload', async () => {
    at('/acme?item=5&section=challenges')
    const dock = await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    expect(within(dock).getByRole('tab', { name: 'common.challenges' })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(acmeService.getAccountById).toHaveBeenCalledWith(5))
    expect(await within(dock).findByText('acme.challengeTxt')).toBeInTheDocument()
  })

  it('a view change closes the dock', async () => {
    at('/acme?item=5')
    await screen.findByRole('complementary', { name: /atelier.detailOf/ })
    fireEvent.click(screen.getByRole('tab', { name: /^acme\.views\.history/ }))
    await waitFor(() => expect(location.search).toBe('?tab=history'))
    expect(screen.queryByRole('complementary', { name: /atelier.detailOf/ })).toBeNull()
  })
})
