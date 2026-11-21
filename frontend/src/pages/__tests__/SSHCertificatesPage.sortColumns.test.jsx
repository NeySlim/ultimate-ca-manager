/**
 * SSHCertificatesPage: only the columns the server sorts offer a sort.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts?.keyId ? `${key}:${opts.keyId}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
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
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return {
    ...actual,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
const getStats = vi.fn()
const generate = vi.fn()
const casGetAll = vi.fn()
vi.mock('../../services', () => ({
  sshCertificatesService: {
    getAll: (...a) => getAll(...a),
    getStats: (...a) => getStats(...a),
    generate: (...a) => generate(...a),
    getById: vi.fn(),
    sign: vi.fn(),
    importCertificate: vi.fn(),
  },
  sshCasService: { getAll: (...a) => casGetAll(...a) },
}))


import SSHCertificatesPage from '../SSHCertificatesPage'

describe('SSHCertificatesPage: sortable columns', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', principals: ['a'], ca_name: 'CA',
      valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: {} })
    casGetAll.mockResolvedValue({ data: [] })
  })

  it.each(['sshCertificates.principals', 'sshCertificates.caName'])('%s asks no sort of the server', async (header) => {
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await screen.findByText('c')
    const th = screen.getAllByText(header).find((el) => el.closest('th'))
    fireEvent.click(th)
    await new Promise((r) => setTimeout(r, 30))
    expect(getAll.mock.calls.map(([params]) => params?.sort_by)).not.toContain(header === 'sshCertificates.caName' ? 'ca_name' : 'principals')
  })

  it('key_id still sorts', async () => {
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await screen.findByText('c')
    fireEvent.click(screen.getAllByText('sshCertificates.keyId').find((el) => el.closest('th')))
    await waitFor(() => expect(getAll.mock.calls.map(([params]) => params?.sort_by)).toContain('key_id'))
  })
})
