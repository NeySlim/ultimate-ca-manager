/**
 * User certificates: a column sort is asked of the server, which sorts the
 * whole list, never applied to the page being shown.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// `t` keeps its identity across renders, like the real hook: the page loaders
// list it in their dependencies.
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false),
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
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true,
    screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))

vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const getAll = vi.fn()
vi.mock('../../services', () => ({
  userCertificatesService: {
    getAll: (...a) => getAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { total: 1, valid: 1, expiring: 0, expired: 0, revoked: 0 } }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    export: vi.fn(),
    revoke: vi.fn(),
    delete: vi.fn(),
  },
}))

import UserCertificatesPage from '../UserCertificatesPage'

const rows = [
  { id: 1, name: 'bravo', common_name: 'bravo', subject: 'CN=bravo', status: 'valid', valid_to: new Date(Date.now() + 864e5).toISOString() },
  { id: 2, name: 'alpha', common_name: 'alpha', subject: 'CN=alpha', status: 'valid', valid_to: new Date(Date.now() + 864e5).toISOString() },
]

const lastParams = () => getAll.mock.calls.at(-1)[0]

describe('user certificates: server-side sort', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: { items: rows, total: 2 } })
  })

  it('asks the server to sort by name, then reverses', async () => {
    render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
    await screen.findAllByText('bravo')
    expect(lastParams().sort_by).toBeUndefined()
    fireEvent.click(document.querySelector('[data-sort="name"]'))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'name', sort_order: 'asc', page: 1 }))
    fireEvent.click(document.querySelector('[data-sort="name"]'))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'name', sort_order: 'desc' }))
  })

  it('maps the expiry column to valid_until', async () => {
    render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
    await screen.findAllByText('bravo')
    fireEvent.click(document.querySelector('[data-sort="valid_to"]'))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'valid_until', sort_order: 'asc' }))
  })
})
