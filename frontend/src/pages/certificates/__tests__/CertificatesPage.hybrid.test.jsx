/**
 * CertificatesPage and a hybrid pair (RFC 9763): the classical member opens in the
 * inspector after issuance, and a link to a member opens it there on a phone too.
 * Revoking, renewing and opening the linked member from the inspector are covered
 * by InspectorObject.related.test.jsx.
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


import CertificatesPage from '../../CertificatesPage'

const A = { id: 11, cn: 'pair.example.com', related_certificate_id: 12, hybrid_role: 'classical' }
const B = { id: 12, cn: 'pair.example.com', related_certificate_id: 11, hybrid_role: 'pq' }

const issuePair = async () => {
  render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(mocks.getAll).toHaveBeenCalled())
  fireEvent.click(screen.getByRole('button', { name: 'certificates.issue' }))
  fireEvent.click(await screen.findByText('submit-issue'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
}

// Mobile: the deep link opens the classical member in the full-screen inspector, no slide-over
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
  await waitFor(() => expect(mocks.openEntity).toHaveBeenCalledWith('certificate', 11))
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
    await waitFor(() => expect(mocks.openEntity).toHaveBeenCalledWith('certificate', 11))
  })

  it('opens a linked member in the inspector on a phone too', async () => {
    await openMemberOnMobile()
    // The page draws no detail of its own: the inspector shows it
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
