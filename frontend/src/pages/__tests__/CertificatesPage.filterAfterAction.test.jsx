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
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
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

const renderPage = () => render(
  <MemoryRouter><CertificatesPage /></MemoryRouter>
)

const lastParams = () => getAll.mock.calls[getAll.mock.calls.length - 1][0]

describe('CertificatesPage — filter survives an external action (#345)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('reloads with the filter set after mount', async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().status).toBeUndefined()

    // A stat card sets the status filter, like the filter dropdown does
    fireEvent.click(screen.getByText('common.valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['valid']))

    const before = getAll.mock.calls.length
    await act(async () => {
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate' } }))
    })
    await waitFor(() => expect(getAll.mock.calls.length).toBeGreaterThan(before))
    // The reload triggered by the action keeps the filter
    expect(lastParams().status).toEqual(['valid'])
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

  it('restores a filter persisted from an earlier session', async () => {
    window.localStorage.setItem('ucm-filter-certs-source', JSON.stringify(['import']))
    renderPage()
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
