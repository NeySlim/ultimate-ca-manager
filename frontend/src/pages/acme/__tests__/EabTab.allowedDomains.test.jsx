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
  useTranslation: () => ({ t: (key) => key }),
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
  useNotification: () => ({
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
    showConfirm: vi.fn(),
  }),
}))

vi.mock('../../../hooks', () => ({
  useClipboard: () => ({ copy: vi.fn() }),
}))

import EabTab from '../EabTab'

const cred = (id, allowed_domains) => ({
  id, kid: `kid-${id}`, label: `cred-${id}`, status: 'active', notes: null,
  created_at: '2026-10-01T00:00:00Z', allowed_domains,
})

const renderTab = (props = {}) => render(
  <EabTab eabRequired={false} onToggleEabRequired={vi.fn()} showCreateModal={false}
    onCloseCreateModal={vi.fn()} canWrite canDelete {...props} />,
)

const domainsRow = async (id) => within(await screen.findByTestId(`eab-domains-${id}`))

const openEdit = async (id) => {
  fireEvent.click((await domainsRow(id)).getByTitle('acme.eab.editDomainsTitle'))
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
