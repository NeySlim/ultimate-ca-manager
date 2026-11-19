/**
 * DiscoveryPage: the export asks for what the table shows (search, status, profile).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
import { discoveryService } from '../../services'


describe('DiscoveryPage: export follows the filters', () => {
  beforeEach(() => {
    authState.permissions = ['*']
    discoveryService.export.mockReset()
    discoveryService.export.mockResolvedValue(new Blob(['x']))
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  it('sends the typed search to the export', async () => {
    render(<MemoryRouter><DiscoveryPage /></MemoryRouter>)
    await screen.findAllByText('10.0.0.5:443')
    fireEvent.change(screen.getAllByRole('textbox')[0], { target: { value: 'probe' } })
    await waitFor(() => expect(discoveryService.getAll.mock.calls.at(-1)[0].search).toBe('probe'))
    fireEvent.click(await screen.findByText('common.export'))
    await waitFor(() => expect(discoveryService.export).toHaveBeenCalled())
    expect(discoveryService.export.mock.calls[0][1]).toMatchObject({ search: 'probe' })
  })
})
