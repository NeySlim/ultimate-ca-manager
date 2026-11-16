/**
 * The account page lists every provider attached to the account, attaches another one,
 * and detaches one or resets its identity behind a confirmation that says what it closes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn(), attachSso: vi.fn(), detachSso: vi.fn(),
  resetSsoIdentity: vi.fn(),
  users: [],
}))
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && opts.provider ? `${key}:${opts.provider}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: (...a) => mocks.showSuccess(...a), showError: (...a) => mocks.showError(...a),
    showWarning: () => {}, showInfo: () => {},
    showConfirm: (...a) => mocks.showConfirm(...a), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
  InspectorProvider: ({ children }) => children,
}))

vi.mock('../../components/UserSecurityKeys', () => ({ default: () => null }))
vi.mock('../../components/UserApiKeys', () => ({ default: () => null }))
vi.mock('../users/UserSecuritySection', () => ({ default: () => null }))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: actual.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

vi.mock('../../services', () => ({
  usersService: {
    getAll: () => Promise.resolve({ data: mocks.users }),
    getById: (id) => Promise.resolve({ data: mocks.users.find(u => u.id === id) }),
    attachSso: (...a) => mocks.attachSso(...a),
    detachSso: (...a) => mocks.detachSso(...a),
    resetSsoIdentity: (...a) => mocks.resetSsoIdentity(...a),
  },
  groupsService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  rolesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  accountService: {},
  ssoService: {
    getProviders: () => Promise.resolve({ data: [
      { id: 1, name: 'idp-a', provider_type: 'oauth2' },
      { id: 2, name: 'idp-b', display_name: 'IdP B', provider_type: 'saml' },
    ] }),
  },
}))

vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveLayout: ({ children, slideOverContent }) => <div>{children}{slideOverContent}</div>,
  ResponsiveDataTable: ({ data = [], onRowClick }) => data.map(row => (
    <button key={row.id} type="button" onClick={() => onRowClick(row)}>{`row-${row.id}`}</button>
  )),
  Select: ({ label, value, onChange, options = [] }) => (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">-</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import UsersGroupsPage from '../UsersGroupsPage'

const open = async (user) => {
  mocks.users = [user]
  render(<MemoryRouter><UsersGroupsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText(`row-${user.id}`))
}

const choose = async (providerId) => {
  const select = await screen.findByLabelText('users.sso.provider')
  await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(select, { target: { value: String(providerId) } })
}

const TWO = {
  id: 7, username: 'bob', email: 'b@example.com', role: 'viewer', active: true, auth_source: 'sso',
  sso_identities: [
    { id: 11, provider_id: 1, provider_name: 'idp-a', provider_type: 'oauth2', external_id: 'sub-a', state: 'bound' },
    { id: 12, provider_id: 2, provider_name: 'IdP B', provider_type: 'saml', external_id: null, state: 'pending' },
  ],
}
const ONE = { ...TWO, id: 8, username: 'carol', sso_identities: [TWO.sso_identities[0]] }
const LOCAL = { id: 9, username: 'dan', email: 'd@example.com', role: 'viewer', active: true,
  auth_source: 'local', sso_identities: [] }

describe('UsersGroupsPage single sign-on providers of an account', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(m => typeof m === 'function' && m.mockReset())
    mocks.attachSso.mockResolvedValue({ data: {} })
    mocks.detachSso.mockResolvedValue({ data: {} })
    mocks.resetSsoIdentity.mockResolvedValue({ data: {} })
  })

  it('lists each provider with its state; only a bound one offers a reset', async () => {
    await open(TWO)
    expect(await screen.findByText('idp-a')).toBeTruthy()
    expect(screen.getByText('users.sso.state.bound')).toBeTruthy()
    expect(screen.getByText('users.sso.state.pending')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /users\.sso\.detach/ })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: /users\.sso\.resetIdentity/ })).toHaveLength(1)
  })

  it('says a local account has no provider', async () => {
    await open(LOCAL)
    expect(await screen.findByText('users.sso.noProviders')).toBeTruthy()
  })

  it('attaches a provider without a confirmation, and offers only those not attached', async () => {
    await open(ONE)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.attach/ }))
    const select = await screen.findByLabelText('users.sso.provider')
    await waitFor(() => expect(select.querySelectorAll('option').length).toBe(2))
    expect([...select.querySelectorAll('option')].map(o => o.value)).toEqual(['', '2'])
    await choose(2)
    fireEvent.click(screen.getAllByRole('button', { name: /users\.sso\.attach$/ }).pop())
    await waitFor(() => expect(mocks.attachSso).toHaveBeenCalledWith(8, { provider_id: 2, remove_password: false }))
    expect(mocks.showConfirm).not.toHaveBeenCalled()
  })

  it('removes the local password only when ticked, and after a confirmation', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    await open(LOCAL)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.attach/ }))
    await choose(1)
    const box = screen.getByRole('checkbox', { name: 'users.sso.removePassword' })
    expect(box.checked).toBe(false)
    fireEvent.click(box)
    fireEvent.click(screen.getAllByRole('button', { name: /users\.sso\.attach$/ }).pop())
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'users.sso.confirmRemovePassword', expect.anything()))
    await waitFor(() => expect(mocks.attachSso).toHaveBeenCalledWith(9, { provider_id: 1, remove_password: true }))
  })

  it('attaches nothing when the password removal is declined', async () => {
    mocks.showConfirm.mockResolvedValue(false)
    await open(LOCAL)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.attach/ }))
    await choose(1)
    fireEvent.click(screen.getByRole('checkbox', { name: 'users.sso.removePassword' }))
    fireEvent.click(screen.getAllByRole('button', { name: /users\.sso\.attach$/ }).pop())
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalled())
    expect(mocks.attachSso).not.toHaveBeenCalled()
  })

  it('detaches one of two providers once confirmed', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    await open(TWO)
    fireEvent.click((await screen.findAllByRole('button', { name: /users\.sso\.detach/ }))[1])
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'users.sso.confirmDetach:IdP B', expect.anything()))
    await waitFor(() => expect(mocks.detachSso).toHaveBeenCalledWith(7, 12))
  })

  it('says the last provider makes the account local, and detaches nothing when declined', async () => {
    mocks.showConfirm.mockResolvedValue(false)
    await open(ONE)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.detach/ }))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'users.sso.confirmDetachLast:idp-a', expect.anything()))
    expect(mocks.detachSso).not.toHaveBeenCalled()
  })

  it('resets the identity of one attachment once confirmed', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    await open(TWO)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.resetIdentity/ }))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'users.sso.confirmReset:idp-a', expect.anything()))
    await waitFor(() => expect(mocks.resetSsoIdentity).toHaveBeenCalledWith(7, 11))
  })
})
