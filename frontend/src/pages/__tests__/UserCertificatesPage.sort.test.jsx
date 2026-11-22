/**
 * User certificates: a column sort is asked of the server, which sorts the
 * whole list, never applied to the page being shown; the sort lives in the address.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderAtUrl } from '../../test/dockUrl'
import { sortKeys, sortedHeaders, absorbing, recordFacts } from '../../test/listColumns'

// `t` keeps its identity across renders, like the real hook: the page loaders
// list it in their dependencies.
// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  mobile: false,
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
    isMobile: stable.mobile, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true,
    screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))

vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: stable.mobile }) }))

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
  { id: 1, name: 'bravo', common_name: 'bravo', subject: 'CN=bravo', status: 'valid', valid_to: new Date(Date.now() + 864e5).toISOString(), owner: 'jdoe' },
  { id: 2, name: 'alpha', common_name: 'alpha', subject: 'CN=alpha', status: 'valid', valid_to: new Date(Date.now() + 864e5).toISOString() },
]

const lastParams = () => getAll.mock.calls.at(-1)[0]

describe('user certificates: server-side sort', () => {
  beforeEach(() => {
    window.localStorage.clear()
    stable.mobile = false
    getAll.mockReset()
    getAll.mockResolvedValue({ data: { items: rows, total: 2 } })
  })

  it('opens on the nearest expiry, asked of the server; name, owner, expiry and state sort (T1, T4)', async () => {
    const { container } = render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
    await screen.findAllByText('bravo')
    expect(lastParams()).toMatchObject({ sort_by: 'valid_until', sort_order: 'asc', page: 1 })
    expect(sortedHeaders(container)).toEqual([['userCertificates.module.expires', 'ascending']])
    expect(sortKeys(container)).toEqual(['name', 'owner', 'valid_until', 'status'])
    expect(absorbing(container)).toEqual(['userCertificates.module.description'])
  })

  it('sorts in two states, back to page one, kept in the address and read back (T3, T9)', async () => {
    getAll.mockResolvedValue({ data: { items: rows, total: 60 } })
    const at = renderAtUrl(<UserCertificatesPage />, '/user-certificates')
    await screen.findAllByText('bravo')
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ page: 2 }))
    const name = () => document.querySelector('[data-sort="name"]')
    fireEvent.click(name())
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'name', sort_order: 'asc', page: 1 }))
    expect(at.where()).toBe('/user-certificates?sort=name&order=asc')
    fireEvent.click(name())
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'name', sort_order: 'desc' }))
    fireEvent.click(name())
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'name', sort_order: 'asc' }))
    fireEvent.click(document.querySelector('[data-sort="status"]'))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'status', sort_order: 'asc' }))
    at.unmount()
    renderAtUrl(<UserCertificatesPage />, '/user-certificates?sort=owner&order=desc')
    await screen.findAllByText('bravo')
    expect(lastParams()).toMatchObject({ sort_by: 'owner', sort_order: 'desc' })
  })

  it('draws a phone record by priority: the expiry after its label, then the owner (R5)', async () => {
    stable.mobile = true
    render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
    await screen.findAllByText('bravo')
    const record = [...document.querySelectorAll('article.mobile-record')].find((r) => r.textContent.includes('bravo'))
    const facts = recordFacts(record)
    expect(facts[0]).toMatch(/^userCertificates\.module\.expires \S/)
    expect(facts[1]).toBe('jdoe')
  })
})
