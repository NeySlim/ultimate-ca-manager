/**
 * Deleting a user or one of its mTLS enrolments revokes the enrolled certificates first:
 * when their ACME CA was not told, the page says so as the user certificates page does.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const users = vi.hoisted(() => ({
  getAll: vi.fn(), delete: vi.fn(), deleteMtlsCertificate: vi.fn(), getMtlsCertificates: vi.fn(),
}))
// Stable across renders: t and the notifier are loader dependencies
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
    showConfirm: () => Promise.resolve(true), showPrompt: () => {},
  },
  ws: { muteToasts: () => {}, subscribe: () => () => {}, isConnected: false },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isLargeScreen: true, isTouch: false,
    screenWidth: 1600, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))

vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
  InspectorProvider: ({ children }) => children,
}))

vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: persisted.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    useWebSocket: () => stable.ws,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, canRead: () => true,
      hasPermission: () => true, isAdmin: () => true, permissions: ['*'],
    }),
  }
})

vi.mock('../../services', () => ({
  usersService: users,
  groupsService: { getAll: () => Promise.resolve({ data: [] }) },
  rolesService: { getAll: () => Promise.resolve({ data: [] }) },
  casService: { getAll: () => Promise.resolve({ data: [] }) },
  accountService: {},
  ssoService: { getProviders: () => Promise.resolve({ data: [] }) },
}))

vi.mock('../../components/UserSecurityKeys', () => ({ default: () => null }))
vi.mock('../../components/UserApiKeys', () => ({ default: () => null }))
vi.mock('../users/UserSecuritySection', () => ({ default: () => null }))

import UsersGroupsPage from '../UsersGroupsPage'

const ALICE = { id: 5, username: 'alice', email: 'alice@example.test', role: 'viewer', active: true }
const OWED = {
  message: 'User alice deleted successfully. Certificate #9: Certificate revoked in UCM, but the ACME CA did not confirm the revocation (HTTP 503); it is sent again automatically until the CA does.',
  meta: { acme_local_only: [9], acme_upstream_pending: [9] },
}

async function openAlice() {
  render(<MemoryRouter><UsersGroupsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('alice@example.test'))
  return screen.findByText('enrolled-alice')
}

function panelDelete() {
  // The detail panel's own button, labelled by its text; the enrolment's carries an aria-label only
  return screen.getAllByRole('button', { name: 'common.delete' })
    .find(button => !button.getAttribute('aria-label'))
}

describe('Users page: a removal the ACME CA was not told of', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    users.getAll.mockResolvedValue({ data: [ALICE] })
    users.getMtlsCertificates.mockResolvedValue({
      data: [{ id: 3, name: 'enrolled-alice', enabled: true, valid_until: '2030-01-01T00:00:00Z' }],
    })
  })

  it('says so when the user is deleted', async () => {
    users.delete.mockResolvedValue(OWED)
    await openAlice()
    fireEvent.click(panelDelete())
    await waitFor(() => expect(stable.notify.showWarning).toHaveBeenCalledWith(OWED.message))
    expect(users.delete).toHaveBeenCalledWith(5)
    expect(stable.notify.showSuccess).not.toHaveBeenCalled()
  })

  it('says so when an enrolment is removed', async () => {
    const removed = {
      message: 'Certificate revoked in UCM only: UCM no longer has the ACME order it was issued under, so it does not know which CA account to revoke it with. Revoke it with the CA directly. Certificate deleted.',
      meta: { acme_local_only: true },
    }
    users.deleteMtlsCertificate.mockResolvedValue(removed)
    const row = (await openAlice()).closest('div.flex.items-center.justify-between')
    fireEvent.click(within(row).getByLabelText('common.delete'))
    await waitFor(() => expect(stable.notify.showWarning).toHaveBeenCalledWith(removed.message))
    expect(users.deleteMtlsCertificate).toHaveBeenCalledWith(5, 3)
    expect(stable.notify.showSuccess).not.toHaveBeenCalled()
  })

  it('reports a plain success when nothing was left to the CA', async () => {
    users.deleteMtlsCertificate.mockResolvedValue(null)
    const row = (await openAlice()).closest('div.flex.items-center.justify-between')
    fireEvent.click(within(row).getByLabelText('common.delete'))
    await waitFor(() => expect(stable.notify.showSuccess).toHaveBeenCalledWith('users.mtls.deleted'))
    expect(stable.notify.showWarning).not.toHaveBeenCalled()
  })
})
