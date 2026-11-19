/**
 * User certificates: the CSV export walks the pages of the list as filtered
 * and sorted on screen, not the page being shown.
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

const exported = vi.hoisted(() => ({ csv: vi.fn() }))
vi.mock('../../lib/utils', async () => {
  const actual = await vi.importActual('../../lib/utils')
  return { ...actual, exportToCSV: exported.csv }
})

import UserCertificatesPage from '../UserCertificatesPage'

const mk = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => ({
  id: from + i, name: `c${from + i}`, common_name: `c${from + i}`, subject: `CN=c${from + i}`,
  status: 'valid', valid_to: new Date(Date.now() + 864e5).toISOString(),
}))

describe('user certificates: export', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    exported.csv.mockReset()
    getAll.mockImplementation(async (p) => ({
      data: { items: mk((p.page - 1) * p.per_page + 1, Math.min(p.page * p.per_page, 130)), total: 130 },
    }))
  })

  it('exports every page with the sort of the screen', async () => {
    render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
    await screen.findAllByText('c1')
    fireEvent.click(screen.getByText('userCertificates.columns.name'))
    await waitFor(() => expect(getAll.mock.calls.at(-1)[0].sort_by).toBe('name'))
    getAll.mockClear()
    fireEvent.click(await screen.findByTitle('table.exportData'))
    fireEvent.click(await screen.findByText('table.exportCSV'))
    await waitFor(() => expect(exported.csv).toHaveBeenCalled())
    expect(exported.csv.mock.calls[0][0]).toHaveLength(130)
    expect(getAll.mock.calls.every(([p]) => p.sort_by === 'name' && p.per_page === 100)).toBe(true)
  })
})
