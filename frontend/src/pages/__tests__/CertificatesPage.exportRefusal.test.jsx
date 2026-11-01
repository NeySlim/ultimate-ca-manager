/**
 * An export the server refuses says why: a hybrid bundle with keys whose other
 * member has none is refused with that reason, not a bare "export failed".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  showError: vi.fn(),
  export: vi.fn(),
  row: { id: 4, common_name: 'pair.example.com', status: 'valid', related_certificate_id: 5, has_private_key: true },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: mocks.showError, showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  // On a phone the detail opens in the page itself, with this page's export handler
  useMobile: () => ({ isMobile: true, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
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
  }
})

vi.mock('../../services', () => ({
  certificatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [mocks.row], meta: { total: 1 } }),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 1, expiring: 0, expired: 0, revoked: 0, total: 1 } }),
    getById: vi.fn((id) => Promise.resolve({ data: id === 5 ? { id: 5, has_private_key: false } : mocks.row })),
    export: (...a) => mocks.export(...a),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  truststoreService: { addFromCA: vi.fn() },
}))

// Each row as a plain button
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveDataTable: ({ data = [], onRowClick }) => data.map(row => (
    <button key={row.id} type="button" onClick={() => onRowClick(row)}>{`row-${row.id}`}</button>
  )),
}))

import CertificatesPage from '../CertificatesPage'

describe('CertificatesPage export refused by the server', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mocks.showError.mockReset()
    mocks.export.mockReset()
  })

  it.each([
    ['the server reason', Object.assign(new Error('Certificate 5 has no private key'), { status: 400 }),
      'Certificate 5 has no private key'],
    ['the generic message without an answer', Object.assign(new Error('Network error'), { status: 0 }),
      'messages.errors.exportFailed.certificate'],
  ])('shows %s', async (_name, error, toast) => {
    mocks.export.mockRejectedValue(error)
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    fireEvent.click(await screen.findByText('row-4'))
    fireEvent.click(await screen.findByTitle('export.title'))
    fireEvent.click(screen.getByText('export.formats.hybridBundle').closest('button'))
    fireEvent.submit(screen.getByText('PEM').closest('form'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith(toast))
  })
})
