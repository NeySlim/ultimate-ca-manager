/**
 * CertificatesPage after a revocation the issuing CA was not told of (ACME or
 * Microsoft CA): the operator reads the server's warning, not a bare success.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  isMobile: false, openEntity: vi.fn(), create: vi.fn(), getAll: vi.fn(), getById: vi.fn(),
  revoke: vi.fn(), renew: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn(), revokeOptions: { revokeRelated: false },
}))
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: mocks.showSuccess, showError: () => {}, showInfo: () => {}, showWarning: mocks.showWarning,
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(''),
  },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: mocks.isMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    openEntity: mocks.openEntity, closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../../hooks', async () => {
  const actual = await vi.importActual('../../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

vi.mock('../../../services', () => ({
  certificatesService: {
    getAll: (...args) => mocks.getAll(...args),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 2, expiring: 0, expired: 0, revoked: 0, total: 2 } }),
    revoke: (...args) => mocks.revoke(...args),
    renew: (...args) => mocks.renew(...args),
    create: (...args) => mocks.create(...args),
    getById: (...args) => mocks.getById(...args),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
}))

vi.mock('../IssueCertificateForm', () => ({
  IssueCertificateForm: ({ onSubmit }) => (
    <button type="button" onClick={() => onSubmit({
      cn: 'pair.example.com', hybrid: { classical: 'EC-P256', pq: 'ML-DSA-65' },
    })}>submit-issue</button>
  ),
}))

// The panel stub exposes the callbacks the page hands it; actions come from the real action bar
vi.mock('../../../components/detail/CertificatePanel', () => ({
  CertificatePanel: ({ certificate, onOpenRelated }) => (
    <div>
      <span>details-{certificate.id}</span>
      <button type="button" onClick={() => onOpenRelated?.(certificate.related_certificate_id)}>details-open-related</button>
    </div>
  ),
}))
vi.mock('../../../components/RevokeCertificateModal', () => ({
  RevokeCertificateModal: ({ open, onConfirm }) => (open
    ? <button type="button" onClick={() => onConfirm('keyCompromise', mocks.revokeOptions)}>confirm-revoke</button>
    : null),
}))

import CertificatesPage from '../../CertificatesPage'

const A = { id: 11, cn: 'upstream.example.com' }

const revokeFromDetails = async () => {
  mocks.isMobile = true
  render(
    <MemoryRouter initialEntries={['/certificates/11']}>
      <Routes>
        <Route path="/certificates/:id" element={<CertificatesPage />} />
        <Route path="/certificates" element={<CertificatesPage />} />
      </Routes>
    </MemoryRouter>
  )
  expect(await screen.findByText('details-11')).toBeInTheDocument()
  fireEvent.click(screen.getByText('common.revoke'))
  fireEvent.click(await screen.findByText('confirm-revoke'))
  await waitFor(() => expect(mocks.revoke).toHaveBeenCalled())
}

describe('CertificatesPage and a revocation the issuing CA did not confirm', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    mocks.getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    mocks.getById.mockResolvedValue({ data: A })
    mocks.revokeOptions = { revokeRelated: false }
  })

  it.each([
    ['acme_local_only', { acme_local_only: true, acme_upstream_pending: true }],
    ['msca_local_only', { msca_local_only: true }],
  ])('shows the server warning for %s', async (_flag, meta) => {
    const message = 'Certificate revoked in UCM, but the CA did not confirm the revocation'
    mocks.revoke.mockResolvedValue({ data: { id: 11, revoked: true }, message, meta })
    await revokeFromDetails()
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith(message))
    expect(mocks.showSuccess).not.toHaveBeenCalledWith('messages.success.other.revoked')
  })

  it('falls back to its own warning when the server gives no message', async () => {
    mocks.revoke.mockResolvedValue({ data: { id: 11, revoked: true }, meta: { acme_local_only: true } })
    await revokeFromDetails()
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('revocation.revokedLocallyOnly'))
  })

  it('says plain success when the CA confirmed', async () => {
    mocks.revoke.mockResolvedValue({ data: { id: 11, revoked: true }, meta: { acme_ca_revoked: true } })
    await revokeFromDetails()
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('messages.success.other.revoked'))
    expect(mocks.showWarning).not.toHaveBeenCalled()
  })
})
