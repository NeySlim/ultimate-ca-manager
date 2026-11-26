/**
 * Editing your own account on the Users page asks for the current password, which the
 * server requires to change it; another user's account does not.
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
  showSuccess: vi.fn(), showWarning: vi.fn(), showError: vi.fn(), update: vi.fn(), reset: vi.fn(), prompt: vi.fn(),
}))
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: (...a) => mocks.showSuccess(...a), showError: (...a) => mocks.showError(...a),
    showWarning: (...a) => mocks.showWarning(...a), showInfo: () => {},
    showConfirm: () => Promise.resolve(true), showPrompt: (...a) => mocks.prompt(...a),
  },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useAuth: () => ({ user: { id: 7 } }),
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
    getAll: vi.fn().mockResolvedValue({ data: [
      { id: 7, username: 'me', email: 'me@example.com', role: 'admin', active: true },
      { id: 9, username: 'alice', email: 'a@example.com', role: 'viewer', active: true },
    ] }),
    update: (...a) => mocks.update(...a),
    resetPassword: (...a) => mocks.reset(...a),
  },
  groupsService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  rolesService: { getAll: vi.fn().mockResolvedValue({ data: [] }), listRoles: vi.fn().mockResolvedValue({ data: [] }) },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  accountService: {},
  ssoService: {},
}))

vi.mock('../../components', async (orig) => ({
  ...(await orig()),
}))

import UsersGroupsPage from '../UsersGroupsPage'

const deleteUser = async () => {
  render(<MemoryRouter><UsersGroupsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'alice' }))
  fireEvent.click(await screen.findByRole('button', { name: /common\.delete/ }))
}

const open = async (row) => {
  render(<MemoryRouter><UsersGroupsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: row === 7 ? 'me' : 'alice' }))
}
const typeInto = (container, type, value) => {
  const inputs = [...container.querySelectorAll(`input[type="${type}"]`)]
  fireEvent.change(inputs[inputs.length - 1], { target: { value } })
}

describe('UsersGroupsPage editing your own account', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(m => m.mockReset())
    mocks.update.mockResolvedValue({})
    mocks.reset.mockResolvedValue({})
  })

  it('asks for the current password with a new one and sends it', async () => {
    await open(7)
    fireEvent.click(await screen.findByRole('button', { name: /common\.edit/ }))
    expect(screen.queryByLabelText(/common\.currentPassword/)).not.toBeInTheDocument()
    const password = await screen.findByLabelText(/common\.newPassword/)
    fireEvent.change(password, { target: { value: 'Brand-New-Passw0rd!' } })
    fireEvent.change(await screen.findByLabelText(/common\.currentPassword/), { target: { value: 'old-pass' } })
    fireEvent.click(screen.getAllByRole('button', { name: /common\.save/ }).pop())
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][0]).toBe(7)
    expect(mocks.update.mock.calls[0][1]).toMatchObject({ password: 'Brand-New-Passw0rd!', current_password: 'old-pass' })
  })

  it('asks for the password before moving your own email, where your reset link goes', async () => {
    mocks.prompt.mockResolvedValueOnce('old-pass')
    await open(7)
    fireEvent.click(await screen.findByRole('button', { name: /common\.edit/ }))
    fireEvent.change(await screen.findByLabelText(/common\.email/), { target: { value: 'moved@example.com' } })
    fireEvent.click(screen.getAllByRole('button', { name: /common\.save/ }).pop())
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.prompt).toHaveBeenCalledWith('account.confirmWithPassword', expect.objectContaining({ type: 'password' }))
    expect(mocks.update.mock.calls[0][1]).toMatchObject({ email: 'moved@example.com', current_password: 'old-pass' })
  })

  it('moves nothing when that prompt is cancelled, and asks nothing for another user', async () => {
    mocks.prompt.mockResolvedValueOnce(null)
    await open(7)
    fireEvent.click(await screen.findByRole('button', { name: /common\.edit/ }))
    fireEvent.change(await screen.findByLabelText(/common\.email/), { target: { value: 'moved@example.com' } })
    fireEvent.click(screen.getAllByRole('button', { name: /common\.save/ }).pop())
    await waitFor(() => expect(mocks.prompt).toHaveBeenCalled())
    expect(mocks.update).not.toHaveBeenCalled()
  })

  it('does not ask for it for another user', async () => {
    await open(9)
    fireEvent.click(await screen.findByRole('button', { name: /common\.edit/ }))
    fireEvent.change(await screen.findByLabelText(/common\.newPassword/), { target: { value: 'Brand-New-Passw0rd!' } })
    expect(screen.queryByLabelText(/common\.currentPassword/)).not.toBeInTheDocument()
  })

  it('asks for the current password before resetting your own password', async () => {
    mocks.prompt.mockResolvedValueOnce('New-Passw0rd-123!').mockResolvedValueOnce('old-pass')
    await open(7)
    fireEvent.click(await screen.findByRole('button', { name: /users\.resetPassword/ }))
    await waitFor(() => expect(mocks.reset).toHaveBeenCalledWith(7, 'New-Passw0rd-123!', 'old-pass'))
  })

  it('does not ask for it when resetting another user', async () => {
    mocks.prompt.mockResolvedValueOnce('New-Passw0rd-123!')
    await open(9)
    fireEvent.click(await screen.findByRole('button', { name: /users\.resetPassword/ }))
    await waitFor(() => expect(mocks.reset).toHaveBeenCalledWith(9, 'New-Passw0rd-123!', undefined))
    expect(mocks.prompt).toHaveBeenCalledTimes(1)
  })
})
