/**
 * CertificatesPage: a search typed before a certificate was opened keeps it open when it lands.
 *
 * The browser router draws a new URL in a transition: the dock writes `?item=` and the page has not
 * drawn it yet when the search's wait ends. The search then has to build on the URL as it is, or it
 * drops the item and the inspector closes under the operator.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'

const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
  inspector: {
    opened: [], activeKey: null, openEntity: () => {}, closeEntity: () => {}, closeAll: () => {},
    setActiveKey: () => {}, setEntityData: () => {}, closeOnNav: false,
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isDesktop: true, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => stable.inspector,
}))

vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...args) => getAll(...args),
    getById: vi.fn().mockResolvedValue({ data: null }),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 1, expiring: 0, expired: 0, revoked: 0, total: 1 } }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
}))

import CertificatesPage from '../CertificatesPage'

let nav
function Where() {
  const loc = useLocation()
  nav = useNavigate()
  return <output data-testid="url">{loc.search}</output>
}

describe('CertificatesPage: a search that lands after a certificate was opened', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('keeps the item the dock wrote since the last render', async () => {
    render(<MemoryRouter initialEntries={['/certificates']}><CertificatesPage /><Where /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'web' } })
    // The dock opens a certificate; its URL is not drawn yet when the search's wait ends
    await act(async () => {
      nav('/certificates?item=8')
      await new Promise((resolve) => setTimeout(resolve, 450))
    })
    const params = new URLSearchParams(screen.getByTestId('url').textContent)
    expect(params.get('q')).toBe('web')
    expect(params.get('item')).toBe('8')
  })
})
