/**
 * CertificatesPage — the active filter survives an action done elsewhere (#345).
 *
 * The certificates list is filtered server-side, and an action performed in
 * the floating detail window (revoke, renew, delete) announces itself with a
 * `ucm:data-changed` event. The listener has to reload with the filters as
 * they are at that moment: registered once with the loader captured at mount,
 * it reloaded without the filters set since, so the filter chip stayed on
 * screen while the list showed everything.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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
  useMobile: () => ({ isMobile: mockIsMobile, isDesktop: !mockIsMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

// The zone's table reads the phone from the context module itself
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: mockIsMobile }) }))

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

const renderPage = (url = '/certificates') => render(
  <MemoryRouter initialEntries={[url]}><CertificatesPage /></MemoryRouter>
)

const lastParams = () => getAll.mock.calls[getAll.mock.calls.length - 1][0]

describe('CertificatesPage — filter survives an external action (#345)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mockIsMobile = false
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('reloads with the filter set after mount', async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().status).toBeUndefined()

    // A state tab sets the status filter
    fireEvent.click(screen.getByRole('button', { name: /^certificates\.views\.valid/ }))
    await waitFor(() => expect(lastParams().status).toEqual(['valid']))

    const before = getAll.mock.calls.length
    await act(async () => {
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate' } }))
    })
    await waitFor(() => expect(getAll.mock.calls.length).toBeGreaterThan(before))
    // The reload triggered by the action keeps the filter
    expect(lastParams().status).toEqual(['valid'])
  })

  it('names a row by its Common Name and shows the description in its own column (#365)', async () => {
    getAll.mockResolvedValue({ data: [{
      id: 42, cn: 'host.example.com', common_name: 'host.example.com',
      descr: 'Renamed by an operator', status: 'valid', caref: 'ca-1',
    }], meta: { total: 1 } })
    renderPage()
    const row = await screen.findByRole('row', { name: /host\.example\.com/ })
    const name = within(row).getByRole('button', { name: 'host.example.com' })
    // One line per row: the name's cell holds the name alone, the description sits in the next cell
    expect(name.closest('td')).toHaveTextContent(/^host\.example\.com$/)
    expect(name.closest('td').nextElementSibling).toHaveTextContent(/^Renamed by an operator$/)
  })

  it('shows the description under the Common Name on mobile too', async () => {
    mockIsMobile = true
    getAll.mockResolvedValue({ data: [{
      id: 43, cn: 'phone.example.com', descr: 'Renamed on mobile', status: 'valid', caref: 'ca-1',
    }], meta: { total: 1 } })
    renderPage()
    // The record shows the description on its own line, under the name
    const name = await screen.findByText('phone.example.com')
    const record = name.closest('article.mobile-record')
    expect(record.querySelector('.row-description')).toHaveTextContent(/^Renamed on mobile$/)
  })

  it('does not repeat a description that is the CN', async () => {
    getAll.mockResolvedValue({ data: [{
      id: 44, cn: 'same.example.com', descr: 'same.example.com', status: 'valid', caref: 'ca-1',
    }], meta: { total: 1 } })
    renderPage()
    const row = await screen.findByRole('row', { name: /same\.example\.com/ })
    expect(within(row).getAllByText('same.example.com')).toHaveLength(1)
  })

  it('ignores an event for another entity type', async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    const before = getAll.mock.calls.length
    await act(async () => {
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    })
    expect(getAll.mock.calls.length).toBe(before)
  })

  it('keeps a filter the address carries when an action elsewhere reloads the list', async () => {
    renderPage('/certificates?source=import')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().source).toEqual(['import'])

    const before = getAll.mock.calls.length
    await act(async () => {
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate' } }))
    })
    await waitFor(() => expect(getAll.mock.calls.length).toBeGreaterThan(before))
    expect(lastParams().source).toEqual(['import'])
  })
})

describe('backupPasswordProblem — counts characters like the server (#346 review)', () => {
  const t = (key, opts) => (opts ? `${key}:${opts.distinct}/${opts.required}` : key)

  it('counts code points, not UTF-16 units', async () => {
    const { backupPasswordProblem } = await import('../SettingsPage')
    // 6 emoji: 12 UTF-16 units but 6 characters, which the server refuses
    expect(backupPasswordProblem('\u{1F510}'.repeat(6), t)).toBe('settings.passwordMinLength')
    // 12 distinct characters, emoji included
    expect(backupPasswordProblem('\u{1F510}a\u{1F511}b\u{1F5DD}c\u{1F512}d\u{1F513}e\u{1F6E1}f', t)).toBeNull()
  })

  it('applies the distinct-character floor, relaxed once long', () => {
    return import('../SettingsPage').then(({ backupPasswordProblem }) => {
      expect(backupPasswordProblem('abcabcabcabc', t)).toContain('backupPasswordTooRepetitive')
      expect(backupPasswordProblem('Start.01Start.01', t)).toBeNull()
      expect(backupPasswordProblem('aaaaaaaaaaaaaaaa', t)).toContain('backupPasswordTooRepetitive')
      expect(backupPasswordProblem('short', t)).toBe('settings.passwordMinLength')
    })
  })
})
