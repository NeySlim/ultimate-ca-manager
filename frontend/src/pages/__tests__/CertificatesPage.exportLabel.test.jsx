/**
 * The table export carries the label shown on screen: the common name with its
 * description, not the empty cell a raw API row gives.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({
  showError: vi.fn(),
  csv: vi.fn(),
  row: { id: 4, common_name: 'host.example.com', descr: 'web front', status: 'valid', has_private_key: true },
}))
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: mocks.showError, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  // On a phone the detail opens in the page itself, with this page's export handler
  useMobile: () => ({ isMobile: false, isDesktop: true, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
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
  }
})

vi.mock('../../services', () => ({
  certificatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [mocks.row], meta: { total: 1 } }),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 1, expiring: 0, expired: 0, revoked: 0, total: 1 } }),
    getById: vi.fn((id) => Promise.resolve({ data: id === 5 ? { id: 5, has_private_key: false } : mocks.row })),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  truststoreService: { addFromCA: vi.fn() },
}))

vi.mock('../../lib/utils', async () => {
  const actual = await vi.importActual('../../lib/utils')
  return { ...actual, exportToCSV: mocks.csv }
})

import CertificatesPage from '../CertificatesPage'

describe('CertificatesPage table export', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mocks.csv.mockReset()
  })

  it('exports the name and the description as displayed, each in its column', async () => {
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    fireEvent.click(await screen.findByTitle('table.exportData'))
    fireEvent.click(await screen.findByText('table.exportCSV'))
    await waitFor(() => expect(mocks.csv).toHaveBeenCalled())
    const [rows, columns] = mocks.csv.mock.calls[0]
    const value = (key) => {
      const col = columns.find(c => c.key === key)
      return col.accessor ? col.accessor(rows[0]) : rows[0][key]
    }
    expect(value('cn')).toBe('host.example.com')
    expect(value('descr')).toBe('web front')
  })
})
