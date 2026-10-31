/**
 * The SSH CA list needs read:ssh_cas: without it the certificates still load.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const showError = vi.hoisted(() => vi.fn())

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
    showSuccess: vi.fn(), showError, showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

const getAll = vi.fn()
const getStats = vi.fn()
const casGetAll = vi.fn()
vi.mock('../../services', () => ({
  sshCertificatesService: { getAll: (...a) => getAll(...a), getStats: (...a) => getStats(...a) },
  sshCasService: { getAll: (...a) => casGetAll(...a) },
}))

import SSHCertificatesPage from '../SSHCertificatesPage'

async function renderPage(permissions) {
  authState.permissions = permissions
  render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
}

describe('SSHCertificatesPage without the SSH CA scope', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'listed-cert', cert_type: 'user',
      valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: { certificates: { valid: 1, expired: 0, revoked: 0, total: 1 } } })
    casGetAll.mockRejectedValue(Object.assign(new Error('Insufficient permissions'), { status: 403 }))
  })

  it('lists the certificates without asking for the CAs', async () => {
    await renderPage(['read:ssh', 'write:ssh'])
    expect((await screen.findAllByText('listed-cert')).length).toBeGreaterThan(0)
    expect(casGetAll).not.toHaveBeenCalled()
    expect(showError).not.toHaveBeenCalled()
  })

  it('asks for the CAs with read:ssh_cas', async () => {
    casGetAll.mockResolvedValue({ data: [] })
    await renderPage(['read:ssh', 'read:ssh_cas'])
    await waitFor(() => expect(casGetAll).toHaveBeenCalled())
  })
})
