/**
 * Revoking or deleting a user certificate UCM obtained over ACME says, as the
 * certificates page does, when its CA was not told (owed or local only).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  getStats: vi.fn(),
  getById: vi.fn(),
  export: vi.fn(),
  revoke: vi.fn(),
  delete: vi.fn(),
}))
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
    showConfirm: () => Promise.resolve(true), showPrompt: () => {},
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
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

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, canRead: () => true,
      hasPermission: () => true, isAdmin: () => true, permissions: ['*'],
    }),
  }
})

vi.mock('../../services', () => ({
  userCertificatesService: serviceMocks,
}))

import UserCertificatesPage from '../UserCertificatesPage'

const ROW = {
  id: 11, name: 'alice@example.test', cert_subject: 'CN=alice@example.test',
  has_private_key: false, valid_to: '2030-01-01T00:00:00Z', status: 'valid',
}
const OWED = {
  message: 'Certificate revoked in UCM, but the ACME CA did not confirm the revocation (HTTP 503); it is sent again automatically until the CA does.',
  meta: { acme_local_only: true, acme_upstream_pending: true, acme_ca_error: 'HTTP 503' },
}

describe('A user certificate the ACME CA was not told of', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    serviceMocks.getStats.mockResolvedValue({ data: {} })
    serviceMocks.getAll.mockResolvedValue({ data: { items: [ROW], total: 1 } })
    serviceMocks.getById.mockResolvedValue({ data: ROW })
  })

  it('says so on revocation', async () => {
    serviceMocks.revoke.mockResolvedValue({ data: ROW, ...OWED })
    render(<UserCertificatesPage />)
    fireEvent.click(await screen.findByTitle('userCertificates.actions.revoke'))
    fireEvent.click(await screen.findByText('revocation.confirm'))
    await waitFor(() => expect(stable.notify.showWarning).toHaveBeenCalledWith(OWED.message))
    expect(stable.notify.showSuccess).not.toHaveBeenCalled()
  })

  it('says so on deletion', async () => {
    serviceMocks.delete.mockResolvedValue({ ...OWED, message: `${OWED.message} Certificate deleted.` })
    render(<UserCertificatesPage />)
    fireEvent.click(await screen.findByTitle('common.delete'))
    await waitFor(() => expect(stable.notify.showWarning).toHaveBeenCalledWith(
      `${OWED.message} Certificate deleted.`))
    expect(stable.notify.showSuccess).not.toHaveBeenCalled()
  })

  it('reports a plain success when nothing was left to the CA', async () => {
    serviceMocks.delete.mockResolvedValue(null)
    render(<UserCertificatesPage />)
    fireEvent.click(await screen.findByTitle('common.delete'))
    await waitFor(() => expect(stable.notify.showSuccess).toHaveBeenCalledWith('userCertificates.deleteSuccess'))
    expect(stable.notify.showWarning).not.toHaveBeenCalled()
  })
})
