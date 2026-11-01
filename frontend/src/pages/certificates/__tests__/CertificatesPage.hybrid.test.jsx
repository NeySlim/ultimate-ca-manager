/**
 * CertificatesPage and a hybrid pair (RFC 9763): the classical member opens after
 * issuance, the linked one opens from its details, and the revocation dialog's
 * answer about the linked certificate reaches the service.
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
  isMobile: false, openWindow: vi.fn(), create: vi.fn(), getAll: vi.fn(), getById: vi.fn(),
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
  useWindowManager: () => ({
    openWindow: mocks.openWindow, closeWindow: vi.fn(), windows: [],
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

// Details and dialog stubs expose the callbacks the page hands them
vi.mock('../../../components', async () => {
  const actual = await vi.importActual('../../../components')
  return {
    ...actual,
    CertificateDetails: ({ certificate, onRevoke, onRenew, onOpenRelated }) => (
      <div>
        <span>details-{certificate.id}</span>
        <button type="button" onClick={onRevoke}>details-revoke</button>
        <button type="button" onClick={() => onRenew?.()}>details-renew</button>
        <button type="button" onClick={() => onOpenRelated?.(certificate.related_certificate_id)}>details-open-related</button>
      </div>
    ),
  }
})
vi.mock('../../../components/RevokeCertificateModal', () => ({
  RevokeCertificateModal: ({ open, onConfirm }) => (open
    ? <button type="button" onClick={() => onConfirm('keyCompromise', mocks.revokeOptions)}>confirm-revoke</button>
    : null),
}))

import CertificatesPage from '../../CertificatesPage'

const A = { id: 11, cn: 'pair.example.com', related_certificate_id: 12, hybrid_role: 'classical' }
const B = { id: 12, cn: 'pair.example.com', related_certificate_id: 11, hybrid_role: 'pq' }

const issuePair = async () => {
  render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(mocks.getAll).toHaveBeenCalled())
  fireEvent.click(screen.getAllByText('certificates.issueCertificate')[0])
  fireEvent.click(await screen.findByText('submit-issue'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
}

// Mobile: the deep link opens the classical member in the slide-over
const openMemberOnMobile = async () => {
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
}

describe('CertificatesPage and a hybrid pair', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    mocks.isMobile = false
    mocks.getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    mocks.create.mockResolvedValue({ data: { certificate: A, related: B } })
    mocks.getById.mockImplementation((id) => Promise.resolve({ data: id === 12 ? B : A }))
    mocks.revoke.mockResolvedValue({ data: {} })
    mocks.revokeOptions = { revokeRelated: false }
  })

  it('opens the classical member of the pair it has just issued', async () => {
    await issuePair()
    await waitFor(() => expect(mocks.openWindow).toHaveBeenCalledWith('certificate', 11))
  })

  it('forwards the revocation answer about the linked certificate', async () => {
    await openMemberOnMobile()
    fireEvent.click(screen.getByText('details-revoke'))
    fireEvent.click(await screen.findByText('confirm-revoke'))
    await waitFor(() => expect(mocks.revoke).toHaveBeenCalledWith(11, 'keyCompromise', { revokeRelated: false }))
  })

  it('names the linked certificate the server revoked too', async () => {
    mocks.revokeOptions = { revokeRelated: true }
    mocks.revoke.mockResolvedValue({ data: { id: 11, revoked: true, related_revoked: 12 } })
    await openMemberOnMobile()
    fireEvent.click(screen.getByText('details-revoke'))
    fireEvent.click(await screen.findByText('confirm-revoke'))
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('revocation.revokedWithRelated'))
    expect(mocks.showWarning).not.toHaveBeenCalledWith('revocation.relatedNotRevoked')
  })

  it('says the linked certificate could not be revoked', async () => {
    mocks.revokeOptions = { revokeRelated: true }
    mocks.revoke.mockResolvedValue({ data: { id: 11, revoked: true, related_not_revoked: 12 } })
    await openMemberOnMobile()
    fireEvent.click(screen.getByText('details-revoke'))
    fireEvent.click(await screen.findByText('confirm-revoke'))
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('revocation.relatedRevokeFailed'))
    expect(mocks.showWarning).not.toHaveBeenCalledWith('revocation.relatedNotRevoked')
  })

  it('warns when the linked certificate asked for was not revoked', async () => {
    mocks.revokeOptions = { revokeRelated: true }
    mocks.revoke.mockResolvedValue({ data: { id: 11, revoked: true } })
    await openMemberOnMobile()
    fireEvent.click(screen.getByText('details-revoke'))
    fireEvent.click(await screen.findByText('confirm-revoke'))
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('revocation.relatedNotRevoked'))
    expect(mocks.showSuccess).toHaveBeenCalledWith('messages.success.other.revoked')
  })

  it.each([
    [{ id: 11, related_renewed: [12] }, 'certificates.hybrid.renewedWithRelated'],
    [{ id: 11 }, 'notifications.certificateIssued'],
  ])('names the linked certificate renewed with it (%o)', async (answer, toast) => {
    mocks.getById.mockImplementation((id) => Promise.resolve({ data: id === 12 ? B : { ...A, has_private_key: true } }))
    mocks.renew.mockResolvedValue({ data: answer })
    await openMemberOnMobile()
    fireEvent.click(screen.getByText('details-renew'))
    await waitFor(() => expect(mocks.renew).toHaveBeenCalledWith(11, {}))
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith(toast))
  })

  it('opens the linked member from the details', async () => {
    await openMemberOnMobile()
    fireEvent.click(await screen.findByText('details-open-related'))
    expect(await screen.findByText('details-12')).toBeInTheDocument()
  })
})
