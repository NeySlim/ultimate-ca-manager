/**
 * Setting a password: same word, four contracts (DUP-CONTRACT-003).
 *
 * Two of them did not line up with the server at all.
 *
 * 1. Admin reset. POST /api/v2/users/<id>/reset-password reads new_password
 *    (backend/api/v2/users/management.py) and refuses 400 without it. The
 *    service sent no body whatsoever, so the button could only ever fail; and
 *    the page then read `res.password`, which that route never returns — its
 *    answer carries a message and nothing else, and success_response nests any
 *    payload under `data` regardless.
 *
 * 2. Account change. The form asks for the new password twice and forwards
 *    confirm_password to a route that reads current_password and new_password
 *    only (backend/api/v2/account/password.py). Nothing compared the two
 *    fields: not the form, not the page, not the server. A typo in the second
 *    box silently set a password the user never meant to choose — while the
 *    other two surfaces that ask twice (ResetPasswordPage, ForcePasswordChange)
 *    do compare them.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPost = vi.hoisted(() => vi.fn())
const accountMocks = vi.hoisted(() => ({
  getProfile: vi.fn(),
  getApiKeys: vi.fn(),
  getWebAuthnCredentials: vi.fn(),
  getMTLSCertificates: vi.fn(),
  getAvailableMTLSCertificates: vi.fn(),
  changePassword: vi.fn(),
}))
const notifications = vi.hoisted(() => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showWarning: vi.fn(),
  showConfirm: vi.fn(),
  showPrompt: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

describe('admin password reset sends what the route requires', () => {
  beforeEach(() => {
    apiPost.mockReset()
    apiPost.mockResolvedValue({ message: 'Password reset successfully' })
    vi.resetModules()
  })

  it('posts new_password rather than an empty body', async () => {
    vi.doMock('../../services/apiClient', () => ({
      apiClient: {
        post: apiPost,
        get: vi.fn().mockResolvedValue({ data: [] }),
        put: vi.fn().mockResolvedValue({ data: {} }),
        patch: vi.fn().mockResolvedValue({ data: {} }),
        delete: vi.fn().mockResolvedValue({ data: {} }),
        upload: vi.fn().mockResolvedValue({ data: {} }),
      },
      buildQueryString: () => '',
      createCRUDService: () => ({
        getAll: vi.fn().mockResolvedValue({ data: [] }),
        getById: vi.fn().mockResolvedValue({ data: {} }),
        create: vi.fn().mockResolvedValue({ data: {} }),
        update: vi.fn().mockResolvedValue({ data: {} }),
        delete: vi.fn().mockResolvedValue({ data: {} }),
      }),
    }))
    const { usersService } = await import('../../services/users.service')

    await usersService.resetPassword(42, 'a-brand-new-password')

    expect(apiPost).toHaveBeenCalledTimes(1)
    const [endpoint, body] = apiPost.mock.calls[0]
    expect(endpoint).toBe('/users/42/reset-password')
    // apiClient only serialises a body when it is an object, so anything less
    // than this reaches Flask as an empty request and comes back 400.
    expect(body).toEqual({ new_password: 'a-brand-new-password' })
  })
})

describe('account password change honours its own confirmation field', () => {
  beforeEach(() => {
    vi.resetModules()
    Object.values(notifications).forEach(fn => fn.mockReset())
    Object.values(accountMocks).forEach(fn => fn.mockReset())
    accountMocks.getProfile.mockResolvedValue({ data: { username: 'probe', email: 'probe@test.local' } })
    accountMocks.getApiKeys.mockResolvedValue({ data: [] })
    accountMocks.getWebAuthnCredentials.mockResolvedValue({ data: [] })
    accountMocks.getMTLSCertificates.mockResolvedValue({ data: [] })
    accountMocks.getAvailableMTLSCertificates.mockResolvedValue({ data: [] })
    accountMocks.changePassword.mockResolvedValue({ message: 'ok' })
  })

  async function openPasswordForm() {
    vi.doMock('../../contexts', () => ({
      useAuth: () => ({ user: { id: 7, username: 'probe', role: 'admin' } }),
      useNotification: () => notifications,
      useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
      useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
      useInspector: () => ({
        openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
        prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
      }),
    }))
    vi.doMock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: ['*'] }) }))
    vi.doMock('../../hooks/useWebSocket', () => ({
      useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
      WebSocketProvider: ({ children }) => children,
      EventType: {},
      ConnectionState: { DISCONNECTED: 'disconnected' },
    }))
    vi.doMock('../../services/account.service', () => ({ accountService: accountMocks }))
    vi.doMock('../../services/cas.service', () => ({ casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) } }))
    vi.doMock('../../services/user-certificates.service', () => ({
      userCertificatesService: { export: vi.fn() },
    }))

    const { MemoryRouter } = await import('react-router-dom')
    const { default: AccountPage } = await import('../AccountPage')
    render(<MemoryRouter><AccountPage /></MemoryRouter>)

    const securityTabs = await screen.findAllByText('common.security')
    fireEvent.click(securityTabs[0])
    const changeButtons = await screen.findAllByText('common.changePassword')
    fireEvent.click(changeButtons[0])
    await waitFor(() => expect(field('confirm_password')).not.toBeNull(), { timeout: 10000 })
  }

  // FormModal builds its payload from FormData, so the name attribute is the
  // contract — the same thing the request body is made of.
  const field = (name) => document.querySelector(`[name="${name}"]`)
  const fill = (name, value) => fireEvent.change(field(name), { target: { value } })
  const submit = () => fireEvent.submit(field('confirm_password').closest('form'))

  it('refuses a confirmation that does not match, without calling the API', async () => {
    await openPasswordForm()
    fill('current_password', 'current-password')
    fill('new_password', 'chosen-password-1')
    fill('confirm_password', 'chosen-password-2')
    submit()

    await waitFor(() => expect(notifications.showError).toHaveBeenCalledWith('common.passwordMismatch'), { timeout: 10000 })
    expect(accountMocks.changePassword).not.toHaveBeenCalled()
  }, 20000)

  it('sends only the two keys the route reads when they match', async () => {
    await openPasswordForm()
    fill('current_password', 'current-password')
    fill('new_password', 'chosen-password-1')
    fill('confirm_password', 'chosen-password-1')
    submit()

    await waitFor(() => expect(accountMocks.changePassword).toHaveBeenCalledTimes(1), { timeout: 10000 })
    expect(accountMocks.changePassword.mock.calls[0][0]).toEqual({
      current_password: 'current-password',
      new_password: 'chosen-password-1',
    })
  }, 20000)
})
