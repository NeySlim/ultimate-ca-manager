/**
 * CertificatesPage: the filters an overview link carries are read from the URL,
 * sent to the list as they are, shown as removable chips.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockIsMobile = false

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: mockIsMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    ...windows, windows: [], prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: () => {},
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

const getAll = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...args) => getAll(...args),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 3, expiring: 0, expired: 0, revoked: 1, total: 4 } }),
    revoke: vi.fn().mockResolvedValue({ data: {} }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
}))

import CertificatesPage from '../CertificatesPage'


const Where = () => <output data-testid="where">{useLocation().search}</output>
const renderAt = (url) => render(<MemoryRouter initialEntries={[url]}><CertificatesPage /><Where /></MemoryRouter>)
const lastParams = () => getAll.mock.calls[getAll.mock.calls.length - 1][0]

describe('CertificatesPage: overview filters in the URL', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('sends the filters of the link to the list, with no other filter', async () => {
    window.localStorage.setItem('ucm-filter-certs-status', JSON.stringify(['valid']))
    renderAt('/certificates?live=true&sig_hash=sha1&sig_hash=md5&bogus=1')
    await waitFor(() => expect(lastParams().live).toBe('true'))
    expect(lastParams().sig_hash).toEqual(['sha1', 'md5'])
    expect(lastParams().bogus).toBeUndefined()
    await waitFor(() => expect(lastParams().status).toBeUndefined())
  })

  it('removes a chip: the URL and the next request lose that filter only', async () => {
    renderAt('/certificates?live=true&no_key=true')
    await waitFor(() => expect(lastParams().no_key).toBe('true'))
    fireEvent.click(screen.getByLabelText(/Remove overview.filter.no_key/))
    await waitFor(() => expect(lastParams().no_key).toBeUndefined())
    expect(lastParams().live).toBe('true')
    expect(screen.getByTestId('where').textContent).toBe('?live=true')
  })

  it('applies the status of a horizon link as a removable filter', async () => {
    renderAt('/certificates?status=expiring')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(screen.getByLabelText(/Remove overview.filter.status/))
    await waitFor(() => expect(lastParams().status).toBeUndefined())
    expect(screen.getByTestId('where').textContent).toBe('')
  })

  it('drops an unknown status from the link', async () => {
    renderAt('/certificates?status=bogus')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().status).toBeUndefined()
  })

  it('a filtered link takes precedence over the saved filters and leaves them stored', async () => {
    window.localStorage.setItem('ucm-filter-certs-status', JSON.stringify(['valid']))
    window.localStorage.setItem('ucm-filter-certs-ca', JSON.stringify(['1']))
    renderAt('/certificates?status=expiring')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    expect(lastParams().ca_id).toBeUndefined()
    // past the 200 ms debounce of usePersistedState
    await new Promise((r) => setTimeout(r, 400))
    expect(lastParams().ca_id).toBeUndefined()
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-status'))).toEqual(['valid'])
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-ca'))).toEqual(['1'])
  })

  it('the saved filters apply again once the link filters are gone', async () => {
    window.localStorage.setItem('ucm-filter-certs-ca', JSON.stringify(['1']))
    renderAt('/certificates?no_key=true')
    await waitFor(() => expect(lastParams().no_key).toBe('true'))
    fireEvent.click(screen.getByLabelText(/Remove overview.filter.no_key/))
    await waitFor(() => expect(lastParams().ca_id).toEqual(['1']))
  })

  it('sends none without them', async () => {
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().live).toBeUndefined()
  })
})
