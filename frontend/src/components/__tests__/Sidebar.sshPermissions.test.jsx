/**
 * The SSH CAs entry needs read:ssh_cas, the SSH certificates entry read:ssh.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 3, username: 'probe', role: 'viewer' }, logout: vi.fn(),
    permissions: authState.permissions }),
}))
vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'default', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(),
    themes: [], isLight: false }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isLargeScreen: true }) }))
vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'disconnected', isConnected: false, connect: vi.fn() }),
  ConnectionState: { DISCONNECTED: 'disconnected', CONNECTED: 'connected', CONNECTING: 'connecting' },
}))
vi.mock('../../services', () => ({
  certificatesService: { getStats: vi.fn().mockResolvedValue({ data: {} }) },
}))

import { Sidebar } from '../Sidebar'

function renderSidebar(permissions) {
  authState.permissions = permissions
  window.localStorage.setItem('ucm_nav_expanded', JSON.stringify(['ssh']))
  render(<MemoryRouter><Sidebar activePage="dashboard" /></MemoryRouter>)
}

describe('Sidebar SSH entries', () => {
  beforeEach(() => window.localStorage.clear())

  it('shows SSH certificates but not SSH CAs with read:ssh alone', () => {
    renderSidebar(['read:ssh'])
    expect(screen.queryAllByTitle('common.sshCertificates').length).toBeGreaterThan(0)
    expect(screen.queryAllByTitle('common.sshCas')).toHaveLength(0)
  })

  it('shows SSH CAs with read:ssh_cas', () => {
    renderSidebar(['read:ssh_cas'])
    expect(screen.queryAllByTitle('common.sshCas').length).toBeGreaterThan(0)
    expect(screen.queryAllByTitle('common.sshCertificates')).toHaveLength(0)
  })
})
