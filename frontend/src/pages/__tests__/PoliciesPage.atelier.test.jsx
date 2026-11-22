/**
 * Policies as the mockup's policies module draws them: the list (Portée, then the product's
 * operations, priority and approval, État) by priority, its state chips, search and operation
 * filter, the one-object dock (Aperçu) with the actions each permission allows, the removal
 * confirmation, the empty and error states.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render as rtl, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && opts.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'fr', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn() }))
const perms = vi.hoisted(() => ({ write: true, del: true }))
vi.mock('../../contexts', () => ({ useNotification: () => notify }))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ canRead: () => true, canWrite: () => perms.write, canDelete: () => perms.del, hasPermission: () => true }),
  }
})
vi.mock('../../lib/policyAlgorithms', () => ({ useKeyPlatform: () => ({ fips: false, fipsKeys: null }) }))
const svc = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn(), toggle: vi.fn(), delete: vi.fn() }))
vi.mock('../../services', () => ({
  policiesService: svc,
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  groupsService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

import { renderAtUrl } from '../../test/dockUrl'
import PoliciesPage from '../PoliciesPage'

const render = (ui) => rtl(<MemoryRouter>{ui}</MemoryRouter>)

const P = [
  { id: 1, name: 'Serveurs TLS', priority: 50, is_active: true, operations: ['issuance', 'renewal'], ca_name: 'Services CA G2', requires_approval: true, min_approvers: 2, approval_group_name: 'pki', rules: { max_validity_days: 397, allowed_key_types: ['RSA-3072'] } },
  { id: 2, name: 'Révocations', priority: 10, is_active: false, operations: ['revocation'], rules: {} },
  { id: 3, name: 'Clients', priority: 50, is_active: true, operations: ['issuance'], description: 'Postes nomades', rules: {} },
]
const names = () => [...document.querySelectorAll('tbody .entity-name')].map((b) => b.textContent)
const sortedHeads = () => screen.getAllByRole('columnheader').filter((h) => /ending/.test(h.getAttribute('aria-sort') || '')).map((h) => [h.textContent, h.getAttribute('aria-sort')])
const sortableHeads = () => screen.getAllByRole('columnheader').filter((h) => h.querySelector('button[data-sort]')).map((h) => h.textContent)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  perms.write = true
  perms.del = true
  svc.list.mockResolvedValue({ data: P })
})

describe('PoliciesPage on the mockup module list', () => {
  it('heads with the total and lists by priority, then name, with the state chips of the states present', async () => {
    render(<PoliciesPage />)
    await screen.findByRole('button', { name: 'Clients' })
    expect(screen.getByRole('heading', { level: 1, name: 'common.policies' })).toBeInTheDocument()
    expect(screen.getByText('policies.unit:3')).toBeInTheDocument()
    expect(names()).toEqual(['Révocations', 'Clients', 'Serveurs TLS'])
    const chips = within(screen.getByRole('group', { name: 'policies.filterByState' })).getAllByRole('button')
    expect(chips.map((b) => b.textContent)).toEqual(['common.all3', 'policies.state.applied2', 'policies.state.inactive1'])
    fireEvent.click(chips[2])
    expect(names()).toEqual(['Révocations'])
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual(
      ['atelier.name', 'policies.scope', 'policies.operations', 'policies.priority', 'policies.approval', 'atelier.state', 'common.actions'])
  })

  it('searches and filters by operation, and resets both from the no-match block', async () => {
    render(<PoliciesPage />)
    await screen.findByRole('button', { name: 'Clients' })
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'nomades' } })
    expect(names()).toEqual(['Clients'])
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'policies.operations' }), { target: { value: 'renewal' } })
    expect(names()).toEqual(['Serveurs TLS'])
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })
    fireEvent.click(screen.getByRole('button', { name: 'table.clearFilters' }))
    expect(names()).toHaveLength(3)
  })

  it('opens a policy in the dock: properties, rules and approval, edit, disable and remove', async () => {
    svc.toggle.mockResolvedValue({})
    svc.delete.mockResolvedValue({})
    render(<PoliciesPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Serveurs TLS' }))
    const dock = screen.getByRole('complementary', { name: 'atelier.detailOf' })
    expect(within(dock).getByRole('heading', { level: 2, name: 'Serveurs TLS' })).toBeInTheDocument()
    expect(within(dock).getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['atelier.overview'])
    const value = (term) => within(dock).getByText(term, { selector: 'dt' }).nextElementSibling
    expect(value('policies.scope')).toHaveTextContent('Services CA G2')
    expect(value('policies.allowedKeyTypes')).toHaveTextContent('RSA-3072')
    expect(value('policies.allowedDigests')).toHaveTextContent('policies.anyDigest')
    expect(value('policies.minApprovers')).toHaveTextContent('2')
    // Its state in a pill, a rule it does not set in grey
    expect(dock.querySelector('dl.props')).toBeNull()
    expect(value('atelier.state').querySelector('.badge')).toHaveTextContent('policies.state.applied')
    expect(value('policies.allowedDigests')).toHaveClass('absent')
    expect(value('policies.allowedKeyTypes')).toHaveClass('v')
    fireEvent.click(within(dock).getByRole('button', { name: 'policies.disable' }))
    await waitFor(() => expect(svc.toggle).toHaveBeenCalledWith(1))
    fireEvent.click(within(dock).getByRole('button', { name: 'policies.deletePolicy…' }))
    const dialog = await screen.findByRole('dialog')
    expect(svc.delete).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(svc.delete).toHaveBeenCalledWith(1))
  })

  it('offers neither creation nor changes without write:policies, nor removal without delete:policies', async () => {
    perms.write = false
    perms.del = false
    render(<PoliciesPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Clients' }))
    const dock = screen.getByRole('complementary', { name: 'atelier.detailOf' })
    expect(screen.queryByRole('button', { name: 'policies.createPolicy' })).toBeNull()
    expect(within(dock).queryByRole('button', { name: 'common.edit' })).toBeNull()
    expect(within(dock).queryByRole('button', { name: 'policies.disable' })).toBeNull()
    expect(within(dock).queryByRole('button', { name: 'policies.deletePolicy…' })).toBeNull()
  })

  it('says why the list is empty and offers the creation to who may create', async () => {
    svc.list.mockResolvedValue({ data: [] })
    render(<PoliciesPage />)
    const empty = await screen.findByText('policies.noPolicies')
    expect(empty.closest('#empty-policies')).toBeInTheDocument()
    fireEvent.click(within(empty.closest('#empty-policies')).getByRole('button', { name: 'policies.createPolicy' }))
    expect(await screen.findByRole('dialog')).toHaveTextContent('policies.policyName')
  })

  it('shows a read failure with its request and Réessayer, which reads again', async () => {
    svc.list.mockRejectedValueOnce(Object.assign(new Error('Service Unavailable'), { status: 503 }))
    render(<PoliciesPage />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('policies.loadFailed')
    expect(within(alert).getByRole('link', { name: /work.viewLog/ })).toHaveAttribute('href', '/audit')
    fireEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    expect(await screen.findByRole('button', { name: 'Clients' })).toBeInTheDocument()
  })
})

describe('the policy dock in the URL', () => {
  it('reopens the policy of the URL, writes the one opened and drops one that is gone', async () => {
    const r = renderAtUrl(<PoliciesPage />, '/policies?item=3')
    expect(within(await r.dock()).getByRole('heading', { level: 2 })).toHaveTextContent('Clients')
    fireEvent.click(screen.getByRole('button', { name: 'Serveurs TLS' }))
    expect(r.where()).toBe('/policies?item=1')
    r.unmount()
    const gone = renderAtUrl(<PoliciesPage />, '/policies?item=99')
    await screen.findByRole('button', { name: 'Clients' })
    await waitFor(() => expect(gone.where()).toBe('/policies'))
  })

  it('opens by priority, sorts every column from its header, keeps the sort in the address and reads it back (T1, T4, T9)', async () => {
    const r = renderAtUrl(<PoliciesPage />, '/policies')
    await screen.findByRole('button', { name: 'Clients' })
    expect(sortedHeads()).toEqual([['policies.priority', 'ascending']])
    expect(names()).toEqual(['Révocations', 'Clients', 'Serveurs TLS'])
    expect(sortableHeads()).toEqual(['atelier.name', 'policies.scope', 'policies.operations', 'policies.priority', 'policies.approval', 'atelier.state'])
    // The priority is a number, at the right; the name takes the room left
    expect(screen.getByRole('columnheader', { name: 'policies.priority' })).toHaveClass('num')
    fireEvent.click(screen.getByRole('button', { name: 'policies.approval' }))
    fireEvent.click(screen.getByRole('button', { name: 'policies.approval' }))
    expect(names()[0]).toBe('Serveurs TLS')
    expect(r.where()).toBe('/policies?sort=approval&order=desc')
    r.unmount()
    renderAtUrl(<PoliciesPage />, '/policies?sort=name&order=desc')
    await screen.findByRole('button', { name: 'Clients' })
    expect(sortedHeads()).toEqual([['atelier.name', 'descending']])
    expect(names()).toEqual(['Serveurs TLS', 'Révocations', 'Clients'])
  })
})
