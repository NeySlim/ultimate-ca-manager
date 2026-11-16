/**
 * Link to SSO is offered on an account already linked (move it to another
 * provider, or reset its SSO identity), behind a confirmation.
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
  showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn(), linkSso: vi.fn(), unlinkSso: vi.fn(),
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
    linkSso: (...a) => mocks.linkSso(...a),
    unlinkSso: (...a) => mocks.unlinkSso(...a),
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

const LINKED = {
  id: 7, username: 'bob', email: 'b@example.com', role: 'viewer', active: true,
  auth_source: 'oauth2', sso_provider_id: 1, sso_provider_name: 'idp-a',
}

describe('UsersGroupsPage Link to SSO on a linked account', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(m => typeof m === 'function' && m.mockReset())
    mocks.linkSso.mockResolvedValue({ data: {} })
  })

  it('offers to change the provider or reset the identity beside Unlink', async () => {
    await open(LINKED)
    expect(await screen.findByRole('button', { name: /users\.sso\.unlink/ })).toBeTruthy()
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.relink/ }))
    expect(await screen.findByText('users.sso.relinkHelp')).toBeTruthy()
  })

  it('moves the account only once the administrator confirms', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    await open(LINKED)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.relink/ }))
    await choose(2)
    fireEvent.click(screen.getByRole('button', { name: /users\.sso\.relink$/ }))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'users.sso.confirmRelink:IdP B users.sso.relinkKeeps', expect.anything()))
    await waitFor(() => expect(mocks.linkSso).toHaveBeenCalledWith(7, { provider_id: 2, remove_password: false }))
  })

  it('changes nothing when the confirmation is declined', async () => {
    mocks.showConfirm.mockResolvedValue(false)
    await open(LINKED)
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.relink/ }))
    await choose(1)
    fireEvent.click(screen.getByRole('button', { name: /users\.sso\.relink$/ }))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalled())
    expect(mocks.linkSso).not.toHaveBeenCalled()
  })

  it('links a local account without a confirmation', async () => {
    await open({ id: 8, username: 'carol', email: 'c@example.com', role: 'viewer', active: true,
      auth_source: 'local', sso_provider_id: null })
    expect(screen.queryByRole('button', { name: /users\.sso\.relink/ })).toBeNull()
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.link/ }))
    await choose(1)
    fireEvent.click(screen.getAllByRole('button', { name: /users\.sso\.link$/ }).pop())
    await waitFor(() => expect(mocks.linkSso).toHaveBeenCalledWith(8, { provider_id: 1, remove_password: false }))
    expect(mocks.showConfirm).not.toHaveBeenCalled()
  })

  it('removes the local password only when the administrator ticks the box', async () => {
    await open({ id: 9, username: 'dan', email: 'd@example.com', role: 'viewer', active: true,
      auth_source: 'local', sso_provider_id: null })
    fireEvent.click(await screen.findByRole('button', { name: /users\.sso\.link/ }))
    await choose(1)
    const box = screen.getByRole('checkbox', { name: 'users.sso.removePassword' })
    expect(box.checked).toBe(false)
    fireEvent.click(box)
    fireEvent.click(screen.getAllByRole('button', { name: /users\.sso\.link$/ }).pop())
    await waitFor(() => expect(mocks.linkSso).toHaveBeenCalledWith(9, { provider_id: 1, remove_password: true }))
  })
})
