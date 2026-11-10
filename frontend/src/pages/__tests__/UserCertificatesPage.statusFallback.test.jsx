/**
 * UserCertificatesPage — an unknown status must not read as "Valid"
 * (DUP-FE-013a).
 *
 * The badge map fell back to `config.valid`, so any status the server grows
 * later (or any row whose status failed to compute) was painted green and
 * labelled Valid on a certificate list. The certificates table falls back to
 * a neutral `unknown` entry (useCertificateColumns): grey, no claim made.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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

const row = (status) => ({
  id: 1, name: 'alice', common_name: 'alice', subject: 'CN=alice', status,
  valid_to: new Date(Date.now() + 864e5).toISOString(),
})

const badgesWithText = (text) =>
  screen.queryAllByText(text).filter((el) => /badge-enhanced/.test(el.className || ''))

async function renderWith(status) {
  getAll.mockResolvedValue({ data: { items: [row(status)], total: 1 } })
  render(<MemoryRouter><UserCertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  await screen.findAllByText('alice')
}

describe('DUP-FE-013a — user certificate status badge fallback', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
  })

  it('does not claim "valid" for a status it does not know', async () => {
    await renderWith('suspended')
    await waitFor(() => expect(badgesWithText('common.status').length).toBeGreaterThan(0))
    expect(badgesWithText('common.valid')).toHaveLength(0)
    badgesWithText('common.status').forEach((b) => {
      expect(b.className).not.toMatch(/status-success-bg/)
    })
  })

  it('does not claim "valid" for a missing status either', async () => {
    await renderWith(undefined)
    await waitFor(() => expect(badgesWithText('common.status').length).toBeGreaterThan(0))
    expect(badgesWithText('common.valid')).toHaveLength(0)
  })

  it('still badges the statuses it knows', async () => {
    await renderWith('valid')
    await waitFor(() => expect(badgesWithText('common.valid').length).toBeGreaterThan(0))
    expect(badgesWithText('common.valid')[0].className).toMatch(/status-success-bg/)
  })

  it('still badges a revoked certificate danger', async () => {
    await renderWith('revoked')
    await waitFor(() => expect(badgesWithText('common.revoked').length).toBeGreaterThan(0))
    expect(badgesWithText('common.revoked')[0].className).toMatch(/status-danger-bg/)
  })
})
