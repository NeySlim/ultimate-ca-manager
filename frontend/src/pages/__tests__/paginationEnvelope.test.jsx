/**
 * Pagination envelope — one envelope, not two (DUP-FE-014a).
 *
 * `/api/v2/certificates` and `/api/v2/ssh/certificates` both answer through
 * success_response(data=..., meta={'total': ...}). No certificate endpoint
 * ever emits a top-level `pagination` key — the single producer of that shape
 * is the notification-log endpoint, which no page calls. Reading a second
 * envelope as a fallback suggests a contract that does not exist, and a
 * response carrying only `pagination` must therefore NOT set the row count.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// `t` keeps its identity across renders, like the real hook: the page loaders
// list it in their dependencies.
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('react-i18next', () => {
  const translation = {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  }
  return {
    useTranslation: () => translation,
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
    useClipboard: () => ({ copy: vi.fn(), copied: false }),
  }
})

const certsGetAll = vi.fn()
const sshGetAll = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...a) => certsGetAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 0, expiring: 0, expired: 0, revoked: 0, total: 0 } }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
  sshCertificatesService: {
    getAll: (...a) => sshGetAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { certificates: { valid: 0, expired: 0, revoked: 0, total: 0 } } }),
  },
  sshCasService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

import CertificatesPage from '../CertificatesPage'
import SSHCertificatesPage from '../SSHCertificatesPage'

const rows = (n) => Array.from({ length: n }, (_, i) => ({
  id: i + 1, subject: `CN=host${i}`, common_name: `host${i}`, status: 'valid',
  valid_to: new Date(Date.now() + 864e5).toISOString(),
}))

describe('DUP-FE-014a — the `pagination` envelope is not a contract', () => {
  beforeEach(() => {
    window.localStorage.clear()
    certsGetAll.mockReset()
    sshGetAll.mockReset()
  })

  it('CertificatesPage counts the rows received when only `pagination` is present', async () => {
    certsGetAll.mockResolvedValue({ data: rows(3), pagination: { total: 99 } })
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(certsGetAll).toHaveBeenCalled())
    expect(await screen.findByText('certificates.subtitle:3')).toBeTruthy()
    expect(screen.queryByText('certificates.subtitle:99')).toBeNull()
  })

  it('CertificatesPage still honours meta.total', async () => {
    certsGetAll.mockResolvedValue({ data: rows(3), meta: { total: 42 } })
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    expect(await screen.findByText('certificates.subtitle:42')).toBeTruthy()
  })

  it('SSHCertificatesPage counts the rows received when only `pagination` is present', async () => {
    sshGetAll.mockResolvedValue({ data: rows(2), pagination: { total: 77 } })
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(sshGetAll).toHaveBeenCalled())
    expect(await screen.findByText('sshCertificates.subtitle:2')).toBeTruthy()
    expect(screen.queryByText('sshCertificates.subtitle:77')).toBeNull()
  })

  it('SSHCertificatesPage still honours meta.total', async () => {
    sshGetAll.mockResolvedValue({ data: rows(2), meta: { total: 55 } })
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    expect(await screen.findByText('sshCertificates.subtitle:55')).toBeTruthy()
  })
})
