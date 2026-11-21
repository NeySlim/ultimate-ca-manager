/**
 * A certificate opened from another page (the overview, an approval, the palette) shows in the
 * Certificates zone's dock, as the mockup's openCert() switches to that view: the page and the
 * inspector are the real ones, with the close-on-navigate preference on.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const stable = vi.hoisted(() => ({
  i18n: { t: (key) => key, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(''),
  },
}))
const mocks = vi.hoisted(() => ({ getAll: vi.fn(), getById: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true, permissions: ['*'] }) }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../contexts', async () => {
  const inspector = await vi.importActual('../../../contexts/InspectorContext')
  return {
    useNotification: () => stable.notify,
    useMobile: () => ({ isMobile: false, isTablet: false }),
    useInspector: inspector.useInspector,
    InspectorProvider: inspector.InspectorProvider,
  }
})
vi.mock('../../../hooks', async () => {
  const actual = await vi.importActual('../../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})
vi.mock('../../../services', () => ({
  certificatesService: {
    getAll: (...a) => mocks.getAll(...a), getById: (...a) => mocks.getById(...a),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 1, total: 1 } }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  auditService: { getLogs: vi.fn().mockResolvedValue({ data: [] }) },
  acmeService: {}, truststoreService: { addFromCA: vi.fn() },
}))
vi.mock('../../../services/account.service', () => ({ accountService: { updatePreferences: vi.fn() } }))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))

import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'
import { InspectorCloseOnNavigate } from '../../../components/inspector/InspectorCloseOnNavigate'
import CertificatesPage from '../../CertificatesPage'

const CERT = { id: 7, common_name: 'web.example.com', cn: 'web.example.com', status: 'valid', valid_to: '2030-01-01T00:00:00Z', source: 'manual' }

function Elsewhere() {
  const { openEntity } = useInspector()
  return <button type="button" onClick={() => openEntity('certificate', 7)}>open-from-overview</button>
}
const Where = () => <output data-testid="where">{useLocation().pathname}</output>

beforeEach(() => {
  window.localStorage.clear()
  mocks.getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  mocks.getById.mockResolvedValue({ data: CERT })
})

describe('a certificate opened from another page', () => {
  it('lands in the Certificates zone dock, not in a dock of the shell', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <InspectorProvider>
          <Routes>
            <Route path="/" element={<Elsewhere />} />
            <Route path="/certificates" element={<CertificatesPage />} />
            <Route path="/certificates/:id" element={<CertificatesPage />} />
          </Routes>
          <InspectorCloseOnNavigate />
          <Where />
        </InspectorProvider>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('open-from-overview'))
    await waitFor(() => expect(document.getElementById('inspector')).not.toBeNull())
    const dock = document.getElementById('inspector')
    expect(dock.closest('[data-testid="certificates-zone"]')).not.toBeNull()
    expect(await within(dock).findByRole('heading', { name: 'web.example.com' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/certificates$/))
    expect(mocks.getById).toHaveBeenCalledWith(7)
  })
})
