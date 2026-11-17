/**
 * SSHCertificatesPage: a certificate that shares its serial with another of its CA (an upgraded
 * 2.254 database may hold such pairs) says so, with its remedy, and its revocation says what it takes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
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
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
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
const getById = vi.fn()
const getStats = vi.fn()
const generate = vi.fn()
const sign = vi.fn()
const importCertificate = vi.fn()
const revoke = vi.fn()
const casGetAll = vi.fn()
vi.mock('../../services', () => ({
  sshCertificatesService: {
    getAll: (...args) => getAll(...args),
    getById: (...args) => getById(...args),
    getStats: (...args) => getStats(...args),
    generate: (...args) => generate(...args),
    sign: (...args) => sign(...args),
    importCertificate: (...args) => importCertificate(...args),
    revoke: (...args) => revoke(...args),
  },
  sshCasService: {
    getAll: (...args) => casGetAll(...args),
  },
}))

import SSHCertificatesPage from '../SSHCertificatesPage'

const PAIR = { id: 1, key_id: 'shared-cert', cert_type: 'user', serial: 7, status: 'valid',
  valid_to: '2030-01-01T00:00:00Z', serial_shared_with: [2] }
const ALONE = { id: 3, key_id: 'lone-cert', cert_type: 'user', serial: 8, status: 'valid',
  valid_to: '2030-01-01T00:00:00Z', serial_shared_with: [] }

const renderPage = () => render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)

describe('SSHCertificatesPage: a serial two certificates share', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset(); getById.mockReset(); getStats.mockReset(); revoke.mockReset(); casGetAll.mockReset()
    getAll.mockResolvedValue({ data: [PAIR, ALONE], meta: { total: 2 } })
    casGetAll.mockResolvedValue({ data: [] })
    getStats.mockResolvedValue({ data: { certificates: { valid: 2, expired: 0, revoked: 0, total: 2 } } })
  })

  it('marks the row of a shared serial and only that one', async () => {
    renderPage()
    await screen.findByText('shared-cert')
    expect(screen.getAllByText('sshCertificates.serialShared')).toHaveLength(1)
  })

  it('shows the remedy in the detail and warns before revoking', async () => {
    getById.mockResolvedValue({ data: PAIR })
    revoke.mockResolvedValue({ data: { ...PAIR, revoked: true, revoked_with: [2] } })
    renderPage()
    fireEvent.click(await screen.findByText('shared-cert'))
    expect(await screen.findByText('sshCertificates.serialSharedDetail')).toBeInTheDocument()
    fireEvent.click(screen.getAllByText('sshCertificates.revokeCertificate').find(el => el.closest('button')))
    expect(await screen.findByText('sshCertificates.revokeSharedSerial')).toBeInTheDocument()
  })

  it('says nothing of the kind for a serial held once', async () => {
    getById.mockResolvedValue({ data: ALONE })
    renderPage()
    fireEvent.click(await screen.findByText('lone-cert'))
    await waitFor(() => expect(getById).toHaveBeenCalledWith(3))
    expect(screen.queryByText('sshCertificates.serialSharedDetail')).toBeNull()
  })
})
