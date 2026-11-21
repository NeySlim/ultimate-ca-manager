/**
 * Allowed domains of EAB credentials: shown in the list, set at creation
 * ("all domains" by default) and edited from the stored state.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  patch: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../../services', () => ({
  acmeService: {
    listEabCredentials: mocks.list,
    createEabCredential: mocks.create,
    patchEabCredential: mocks.patch,
  },
}))

vi.mock('../../../contexts', () => ({
  useMobile: () => ({ isMobile: false }),
  useNotification: () => ({
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
    showConfirm: vi.fn(),
  }),
}))

vi.mock('../../../hooks', () => ({
  useClipboard: () => ({ copy: vi.fn() }),
}))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

import EabTab from '../EabTab'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'

const cred = (id, allowed_domains) => ({
  id, kid: `kid-${id}`, label: `cred-${id}`, status: 'active', notes: null,
  created_at: '2026-10-01T00:00:00Z', allowed_domains,
})

const renderTab = (props = {}) => render(
  <WithDockSlot>
    <EabTab eabRequired={false} onToggleEabRequired={vi.fn()} showCreateModal={false}
      onCloseCreateModal={vi.fn()} canWrite canDelete {...props} />
  </WithDockSlot>,
)

const domainsRow = async (id) => within(await screen.findByTestId(`eab-domains-${id}`))

// The credential opens its dock; Modifier les domaines opens the dialog
const openEdit = async (id) => {
  fireEvent.click(await screen.findByRole('button', { name: `cred-${id}` }))
  fireEvent.click(await screen.findByRole('button', { name: 'acme.eab.editDomainsTitle' }))
  return screen.findByRole('dialog')
}

describe('EabTab allowed domains', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.patch.mockResolvedValue({ data: {} })
    mocks.create.mockResolvedValue({ data: { kid: 'new', hmac_key: 'secret' } })
  })

  it('lists null and "*" as all domains, [] as none, patterns otherwise', async () => {
    mocks.list.mockResolvedValue({ data: [
      cred(1, null), cred(2, ['*']), cred(3, []), cred(4, ['a.example.com', '*.b.example.com']),
    ] })
    renderTab()
    expect((await domainsRow(1)).getByText('acme.eab.allDomains')).toBeInTheDocument()
    expect((await domainsRow(2)).getByText('acme.eab.allDomains')).toBeInTheDocument()
    expect((await domainsRow(3)).getByText('acme.eab.noDomains')).toBeInTheDocument()
    expect((await domainsRow(4)).getByText('a.example.com, *.b.example.com')).toBeInTheDocument()
  })

  it('opens a null credential as all domains and saves ["*"] unchanged', async () => {
    mocks.list.mockResolvedValue({ data: [cred(1, null)] })
    renderTab()
    const dialog = await openEdit(1)
    expect(within(dialog).getByRole('checkbox')).toBeChecked()
    expect(within(dialog).getByRole('textbox')).toHaveValue('')
    fireEvent.click(within(dialog).getByText('common.save'))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(1, { allowed_domains: ['*'] }))
  })

  it('opens a restricted credential on its patterns and sends the edited list', async () => {
    mocks.list.mockResolvedValue({ data: [cred(7, ['a.example.com', '*.b.example.com'])] })
    renderTab()
    const dialog = await openEdit(7)
    expect(within(dialog).getByRole('checkbox')).not.toBeChecked()
    const box = within(dialog).getByRole('textbox')
    expect(box).toHaveValue('a.example.com\n*.b.example.com')
    fireEvent.change(box, { target: { value: 'a.example.com, c.example.com\n\n d.example.com ' } })
    fireEvent.click(within(dialog).getByText('common.save'))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(7, {
      allowed_domains: ['a.example.com', 'c.example.com', 'd.example.com'],
    }))
  })

  it('keeps patterns stored next to "*" while showing all domains', async () => {
    mocks.list.mockResolvedValue({ data: [cred(8, ['*', 'a.example.com'])] })
    renderTab()
    const dialog = await openEdit(8)
    expect(within(dialog).getByRole('checkbox')).toBeChecked()
    expect(within(dialog).getByRole('textbox')).toHaveValue('a.example.com')
  })

  it('sends [] only when all domains is unchecked and the list left empty', async () => {
    mocks.list.mockResolvedValue({ data: [cred(9, ['*'])] })
    renderTab()
    const dialog = await openEdit(9)
    fireEvent.click(within(dialog).getByRole('checkbox'))
    fireEvent.click(within(dialog).getByText('common.save'))
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(9, { allowed_domains: [] }))
  })

  it('creates with all domains by default', async () => {
    mocks.list.mockResolvedValue({ data: [] })
    renderTab({ showCreateModal: true })
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('checkbox')).toBeChecked()
    fireEvent.click(within(dialog).getByText('acme.eab.generate'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(
      expect.objectContaining({ allowed_domains: ['*'] })))
  })

  it('creates with the typed patterns once all domains is unchecked', async () => {
    mocks.list.mockResolvedValue({ data: [] })
    renderTab({ showCreateModal: true })
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('checkbox'))
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'acme.eab.allowedDomains' }),
      { target: { value: '*.corp.example.net,api.corp.example.net' } })
    fireEvent.click(within(dialog).getByText('acme.eab.generate'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      allowed_domains: ['*.corp.example.net', 'api.corp.example.net'],
    })))
  })
})

describe('EabTab list', () => {
  const many = () => Array.from({ length: 30 }, (_, i) => ({
    ...cred(i + 1, ['*']), label: `cred-${i + 1}`, kid: `kid-${String(30 - i).padStart(2, '0')}`,
    status: i % 3 === 0 ? 'revoked' : 'active', created_at: `2026-10-${String(i + 1).padStart(2, '0')}T00:00:00Z`,
  }))

  it('searches, sorts from the headers and pages by 25', async () => {
    mocks.list.mockResolvedValue({ data: many() })
    const { container } = renderTab()
    await screen.findByRole('button', { name: 'cred-1' })
    const footer = container.querySelector('footer.table-footer')
    const bodyRows = () => container.querySelectorAll('tbody tr')
    expect(bodyRows()).toHaveLength(25)
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(bodyRows()).toHaveLength(5)
    fireEvent.click(screen.getByRole('button', { name: 'acme.eab.kid' }))
    expect(footer).toHaveTextContent('1 / 2')
    expect(bodyRows()[0]).toHaveTextContent('kid-01')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    expect(bodyRows()[0]).toHaveTextContent('acme.eab.statusRevoked')
    for (const name of ['atelier.name', 'acme.eab.allowedDomains', 'acme.eab.created']) expect(screen.getByRole('button', { name })).toBeInTheDocument()
    // The search reads the key id; the chips count what it kept
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    fireEvent.change(screen.getByRole('searchbox', { name: 'acme.eab.search' }), { target: { value: 'cred' } })
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.change(screen.getByRole('searchbox', { name: 'acme.eab.search' }), { target: { value: 'kid-0' } })
    expect(bodyRows()).toHaveLength(9)
    expect(within(footer).queryByRole('button', { name: 'table.nextPage' })).toBeNull()
    expect(within(screen.getByRole('group', { name: 'acme.filterByState' })).getByRole('button', { name: /common.all/ })).toHaveTextContent('9')
    fireEvent.change(screen.getByRole('searchbox', { name: 'acme.eab.search' }), { target: { value: 'nothing' } })
    fireEvent.click(await screen.findByRole('button', { name: 'table.clearFilters' }))
    expect(bodyRows()).toHaveLength(25)
  })
})
