/**
 * The template digest is the issuing CA's hash, not a property of the leaf key,
 * so the detail view shows it for an ML-DSA template too.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

// A stable notification object keeps useCRUDPage from refetching in a loop
const notification = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notification,
  useMobile: () => ({ isMobile: false, isDesktop: true, isTouch: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: persisted.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const TEMPLATES = vi.hoisted(() => [
  { id: 7, name: 'PQ leaf', template_type: 'web_server', is_system: false, key_type: 'ML-DSA-65', digest: 'sha512', validity_days: 90 },
])

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: TEMPLATES }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    create: vi.fn(), update: vi.fn(), delete: vi.fn(),
  },
}))
vi.mock('../../services/eku.service', () => ({
  ekuService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

import TemplatesPage from '../TemplatesPage'

describe('TemplatesPage detail digest', () => {
  it('shows the CA digest of an ML-DSA template', async () => {
    window.localStorage.clear()
    render(<MemoryRouter><TemplatesPage /></MemoryRouter>)
    fireEvent.click(within(await screen.findByRole('table')).getByText('PQ leaf'))
    expect(await screen.findByText('sha512')).toBeTruthy()
    expect(screen.getByText('common.digest')).toBeTruthy()
  })
})
