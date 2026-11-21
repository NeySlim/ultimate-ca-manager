/**
 * DiscoveryPage — the buttons mirror the backend scopes.
 *
 * Scanning, profile CRUD, the bulk DNS resolve and the purge all require
 * admin:system, a scope no role carries outside the admin wildcard. The page
 * offered them on write:certificates, so an operator saw every button and
 * each one answered 403.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const discovered = vi.hoisted(() => ([
  {
    id: 1, target: '10.0.0.5', port: 443, status: 'ok',
    subject: 'CN=probe.lan', issuer: 'CN=Probe CA', hostname: 'probe.lan',
    valid_to: '2030-01-01T00:00:00Z', discovered_at: '2026-01-01T00:00:00Z',
  },
]))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(),
    showConfirm: vi.fn(), showPrompt: vi.fn(),
  }),
  useAuth: () => ({ user: { id: 1, username: 'probe' }, permissions: authState.permissions }),
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services', () => ({
  discoveryService: {
    getStats: vi.fn().mockResolvedValue({ data: { total: 1, valid: 1, expiring: 0, expired: 0, errors: 0 } }),
    getProfiles: vi.fn().mockResolvedValue({ data: [{ id: 3, name: 'Lab sweep', targets: ['10.0.0.0/24'], ports: [443] }] }),
    getAll: vi.fn().mockResolvedValue({ data: discovered, meta: { total: 1 } }),
    getRuns: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    scan: vi.fn(), scanProfile: vi.fn(), delete: vi.fn(), deleteAll: vi.fn(),
    createProfile: vi.fn(), updateProfile: vi.fn(), deleteProfile: vi.fn(),
    bulkResolveDns: vi.fn(), export: vi.fn(),
  },
}))

import DiscoveryPage from '../DiscoveryPage'

// Verbatim from backend/auth/permissions.py.
const OPERATOR_WRITE_CERTIFICATES = [
  'read:certificates', 'write:certificates',
  'read:cas', 'write:cas', 'read:templates',
]

async function renderPage() {
  render(<MemoryRouter><DiscoveryPage /></MemoryRouter>)
  // Wait for the results to land: the toolbar actions only render once the
  // table has rows, so asserting before that would pass on an empty page.
  await screen.findAllByText('10.0.0.5:443')
}

describe('DiscoveryPage — scan actions follow admin:system', () => {
  beforeEach(() => { authState.permissions = [] })

  it('offers no scan or purge to an operator', async () => {
    authState.permissions = [...OPERATOR_WRITE_CERTIFICATES]
    await renderPage()
    expect(screen.queryByText('discovery.quickScan')).not.toBeInTheDocument()
    expect(screen.queryByText('discovery.deleteAll')).not.toBeInTheDocument()
    expect(screen.queryByText('discovery.bulkResolveDns')).not.toBeInTheDocument()
  })

  it('still offers the export, which only needs read:certificates', async () => {
    authState.permissions = [...OPERATOR_WRITE_CERTIFICATES]
    await renderPage()
    expect(await screen.findByText('common.export')).toBeInTheDocument()
  })

  it('offers them to the admin wildcard', async () => {
    authState.permissions = ['*']
    await renderPage()
    expect(await screen.findByText('discovery.quickScan')).toBeInTheDocument()
    expect(screen.getByText('discovery.deleteAll')).toBeInTheDocument()
    expect(screen.getByText('discovery.bulkResolveDns')).toBeInTheDocument()
  })

  it('offers them to a custom role holding admin:system', async () => {
    authState.permissions = [...OPERATOR_WRITE_CERTIFICATES, 'admin:system']
    await renderPage()
    expect(await screen.findByText('discovery.quickScan')).toBeInTheDocument()
  })
})
