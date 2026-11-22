/**
 * The profile list reads one server page at a time: 150 profiles cost one page, and the search,
 * the CA and the state go to the server.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
// The lists keep their sort in the address
const render = (ui, options) => rtlRender(ui, { wrapper: MemoryRouter, ...options })

// Stable references: the list reloads whenever `t` or the notifier changes identity.
const mocks = vi.hoisted(() => ({
  t: (key, opts) => (opts?.name ? `${key}:${opts.name}` : key),
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() },
  list: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mocks.t,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true,
    screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))
vi.mock('../../../services', () => ({
  windowsProfilesService: { list: mocks.list, update: vi.fn(), remove: vi.fn() },
}))
import WindowsProfileList from '../WindowsProfileList'

const PROFILES = Array.from({ length: 150 }, (_, i) => ({
  id: i + 1,
  name: `profile-${String(i + 1).padStart(3, '0')}`,
  realm: `REALM${i + 1}.EXAMPLE`,
  is_default: i === 0,
  enabled: true,
  state: 'complete',
  issuing_ca_name: 'Issuing CA',
  connector_name: null,
}))

const CAS = [{ id: 1, refid: 'ca-refid-1', descr: 'Issuing CA', has_private_key: true }]

beforeEach(() => {
  mocks.list.mockReset()
  mocks.list.mockImplementation(async ({ page, per_page: perPage }) => ({
    data: PROFILES.slice((page - 1) * perPage, page * perPage),
    meta: { total: PROFILES.length, page, per_page: perPage },
  }))
})

// The server's default order, asked for by name
const BY_NAME = { sort_by: 'name', sort_order: 'asc' }

const renderList = (props = {}) => render(
  <WindowsProfileList cas={CAS} canWrite onEdit={vi.fn()} onCreate={vi.fn()} reloadKey={0} {...props} />)

describe('WindowsProfileList', () => {
  it('asks for one page of 150 profiles and renders that page only', async () => {
    renderList()
    await screen.findByText('profile-001')
    expect(mocks.list).toHaveBeenCalledTimes(1)
    expect(mocks.list).toHaveBeenCalledWith({ page: 1, per_page: 25, ...BY_NAME })
    expect(screen.queryByText('profile-026')).not.toBeInTheDocument()
    expect(screen.getAllByText(/^profile-\d{3}$/)).toHaveLength(25)
  })

  it('sends the search to the server', async () => {
    renderList()
    await screen.findByText('profile-001')
    fireEvent.change(screen.getByPlaceholderText('xcepWstep.searchPlaceholder'), { target: { value: 'realm9' } })
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 1, per_page: 25, ...BY_NAME, q: 'realm9' }), { timeout: 2000 })
  })

  it('sends the state and the CA to the server and goes back to the first page', async () => {
    renderList()
    await screen.findByText('profile-001')
    fireEvent.change(screen.getByLabelText('common.status'), { target: { value: 'keytab_missing' } })
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 1, per_page: 25, ...BY_NAME, state: 'keytab_missing' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'xcepWstep.issuingCa' }), { target: { value: 'ca-refid-1' } })
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(
      { page: 1, per_page: 25, ...BY_NAME, ca: 'ca-refid-1', state: 'keytab_missing' }))
  })

  it('sorts by the server from its headers, back to the first page, the order kept in the address (T2, T9)', async () => {
    renderList()
    await screen.findByText('profile-001')
    expect(screen.getByRole('columnheader', { name: 'atelier.name' })).toHaveAttribute('aria-sort', 'ascending')
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 2, per_page: 25, ...BY_NAME }))
    fireEvent.click(screen.getByRole('button', { name: 'xcepWstep.realm' }))
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 1, per_page: 25, sort_by: 'realm', sort_order: 'asc' }))
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 1, per_page: 25, sort_by: 'status', sort_order: 'asc' }))
    // The rows are the server's page as it came: never sorted again here
    expect(screen.getAllByRole('row').slice(1, 3).map((r) => r.querySelector('.entity-label')?.textContent)).toEqual(['profile-001', 'profile-002'])
    expect(screen.queryByRole('button', { name: 'xcepWstep.issuingCa' })).toBeNull()
  })

  it('offers the four states', async () => {
    renderList()
    await screen.findByText('profile-001')
    const options = [...screen.getByLabelText('common.status').querySelectorAll('option')].map(o => o.value).filter(Boolean)
    expect(options).toEqual(['complete', 'keytab_missing', 'connector_failing', 'disabled'])
  })

  it('says Kerberos is refused for a default profile with no realm', async () => {
    mocks.list.mockResolvedValue({
      data: [{ ...PROFILES[0], realm: null, state: 'complete' }], meta: { total: 1, page: 1, per_page: 25 },
    })
    renderList()
    expect(await screen.findByText('xcepWstep.noRealmKerberosRefused:profile-001')).toBeInTheDocument()
  })

  it('hides what the user cannot do', async () => {
    renderList({ canWrite: false })
    await screen.findByText('profile-001')
    expect(screen.queryByText('xcepWstep.addProfile')).not.toBeInTheDocument()
    expect(screen.queryAllByTitle('common.disable')).toHaveLength(0)
  })

  it('does not offer to delete the default profile', async () => {
    renderList()
    await screen.findByText('profile-001')
    // 25 rows, the default among them
    expect(screen.getAllByTitle('common.disable')).toHaveLength(25)
    expect(screen.getAllByTitle('common.delete')).toHaveLength(24)
  })

  it('offers one Add button: the empty block holds it, the list keeps it under the rows', async () => {
    mocks.list.mockImplementation(async () => ({ data: [], meta: { total: 0 } }))
    const { unmount } = renderList()
    await screen.findByText('xcepWstep.noProfiles')
    expect(screen.getAllByRole('button', { name: 'xcepWstep.addProfile' })).toHaveLength(1)
    unmount()
    mocks.list.mockImplementation(async ({ page, per_page: perPage }) => ({ data: PROFILES.slice(0, perPage), meta: { total: PROFILES.length, page } }))
    renderList()
    await screen.findByText('profile-001')
    expect(screen.getAllByRole('button', { name: 'xcepWstep.addProfile' })).toHaveLength(1)
  })
})
