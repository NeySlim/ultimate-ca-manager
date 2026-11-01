/**
 * The SSH CA list needs read:ssh_cas: without it the certificates still load.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const showError = vi.hoisted(() => vi.fn())
// Stable across renders: t and showError are loadData dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: (...a) => showError(...a), showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
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

  it('says why the issue form has no CA to offer', async () => {
    await renderPage(['read:ssh', 'write:ssh'])
    fireEvent.click((await screen.findAllByText('sshCertificates.issueCertificate'))[0])
    expect(await screen.findByText('sshCertificates.issueNeedsCaRead')).toBeInTheDocument()
  })

  it('shows no such notice to an account that can list the CAs', async () => {
    casGetAll.mockResolvedValue({ data: [] })
    await renderPage(['read:ssh', 'write:ssh', 'read:ssh_cas'])
    fireEvent.click((await screen.findAllByText('sshCertificates.issueCertificate'))[0])
    await screen.findAllByText('sshCertificates.selectCa')
    expect(screen.queryByText('sshCertificates.issueNeedsCaRead')).toBeNull()
  })

  it('loads the CAs once read:ssh_cas is granted', async () => {
    authState.permissions = ['read:ssh']
    const { rerender } = render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(casGetAll).not.toHaveBeenCalled()
    casGetAll.mockResolvedValue({ data: [] })
    authState.permissions = ['read:ssh', 'read:ssh_cas']
    rerender(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(casGetAll).toHaveBeenCalled())
  })
})
