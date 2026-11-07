/**
 * A user certificate on hold can still be revoked for good (RFC 5280 §5.2.4):
 * its row keeps the Revoke action; one revoked for good loses it.
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
const downloadBlob = vi.hoisted(() => vi.fn())
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showWarning: () => {},
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

vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
  WindowManagerProvider: ({ children }) => children,
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

vi.mock('../../lib/utils', async (importOriginal) => ({
  ...(await importOriginal()),
  downloadBlob,
}))

import UserCertificatesPage from '../UserCertificatesPage'

const ROW = {
  id: 11, name: 'alice@example.test', cert_subject: 'CN=alice@example.test',
  has_private_key: false, valid_to: '2030-01-01T00:00:00Z',
}

describe('Revoke on a revoked user certificate', () => {
  beforeEach(() => {
    serviceMocks.getStats.mockResolvedValue({ data: {} })
  })

  it.each([
    ['on hold', { status: 'revoked', revoked: true, revoke_reason: 'certificateHold' }, true],
    ['revoked for good', { status: 'revoked', revoked: true, revoke_reason: 'keyCompromise' }, false],
  ])('%s', async (_name, state, offered) => {
    const row = { ...ROW, ...state }
    serviceMocks.getAll.mockResolvedValue({ data: { items: [row], total: 1 } })
    serviceMocks.getById.mockResolvedValue({ data: row })
    render(<UserCertificatesPage />)
    await screen.findByTitle('common.export')
    await waitFor(() => expect(!!screen.queryByTitle('userCertificates.actions.revoke')).toBe(offered))
  })
})
