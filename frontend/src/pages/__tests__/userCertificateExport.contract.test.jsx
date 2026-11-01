/**
 * One export dialog per certificate, not one per page (DUP-FE-007).
 *
 * A user certificate can be exported from the Account page and from the User
 * Certificates page. Both end up in userCertificatesService.export, whose
 * include_key defaults to true — so the page that passed no options handed out
 * the private key on a plain PEM export, with no checkbox and no permission
 * asked, while the Account page (which goes through ExportModal) sent
 * include_key: false for that same certificate and format.
 *
 * Both surfaces now render ExportModal, so the request is decided by what the
 * operator ticked rather than by which page they happened to start from.
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
  id: 11,
  name: 'alice@example.test',
  cert_subject: 'CN=alice@example.test',
  status: 'valid',
  has_private_key: true,
  valid_to: '2030-01-01T00:00:00Z',
}

async function openRowExport() {
  render(<UserCertificatesPage />)
  await screen.findByTitle('common.export')
  fireEvent.click(screen.getByTitle('common.export'))
  await screen.findByText('PEM')
}

describe('user certificate export sends what was actually asked for', () => {
  beforeEach(() => {
    downloadBlob.mockClear()
    serviceMocks.export.mockReset()
    serviceMocks.export.mockResolvedValue(new Blob(['pem']))
    serviceMocks.getAll.mockResolvedValue({ data: { items: [ROW], total: 1 } })
    serviceMocks.getStats.mockResolvedValue({ data: {} })
    serviceMocks.getById.mockResolvedValue({ data: ROW })
  })

  it('does not ship the private key with a plain PEM export', async () => {
    await openRowExport()
    fireEvent.click(screen.getByText('Download'))

    await waitFor(() => expect(serviceMocks.export).toHaveBeenCalledTimes(1))
    const [id, format, options] = serviceMocks.export.mock.calls[0]
    expect(id).toBe(ROW.id)
    expect(format).toBe('pem')
    // The service defaults include_key to true; the surface must be explicit,
    // or a PEM download quietly becomes a private-key download.
    expect(options.includeKey).toBe(false)
  })

  it('offers the same formats as every other export surface', async () => {
    await openRowExport()
    ;['PEM', 'DER', 'P7B / PKCS#7', 'P12 / PKCS#12', 'JKS'].forEach(label =>
      expect(screen.getByText(label)).toBeInTheDocument()
    )
  })

  it('ships the key only when the operator ticks it', async () => {
    await openRowExport()
    fireEvent.click(screen.getByText('Include private key'))
    fireEvent.click(screen.getByText('Download'))

    await waitFor(() => expect(serviceMocks.export).toHaveBeenCalledTimes(1))
    expect(serviceMocks.export.mock.calls[0][2].includeKey).toBe(true)
  })
})
