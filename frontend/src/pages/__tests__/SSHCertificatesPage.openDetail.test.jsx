/**
 * SSHCertificatesPage: a certificate just issued or imported is selected (open-detail).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
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
const casGetAll = vi.fn()
vi.mock('../../services', () => ({
  sshCertificatesService: {
    getAll: (...args) => getAll(...args),
    getById: (...args) => getById(...args),
    getStats: (...args) => getStats(...args),
    generate: (...args) => generate(...args),
    sign: (...args) => sign(...args),
    importCertificate: (...args) => importCertificate(...args),
  },
  sshCasService: {
    getAll: (...args) => casGetAll(...args),
  },
}))

import SSHCertificatesPage from '../SSHCertificatesPage'

const EXISTING = [
  { id: 1, key_id: 'existing-cert', cert_type: 'user', valid_to: '2030-01-01T00:00:00Z' },
]
const CAS = [{ id: 5, name: 'Users CA', ca_type: 'user' }]

const renderPage = () => render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)

describe('SSHCertificatesPage — opening the certificate just issued or imported', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset(); getById.mockReset(); getStats.mockReset()
    generate.mockReset(); sign.mockReset(); importCertificate.mockReset(); casGetAll.mockReset()
    getAll.mockResolvedValue({ data: EXISTING, meta: { total: 1 } })
    casGetAll.mockResolvedValue({ data: CAS })
    getStats.mockResolvedValue({ data: { certificates: { valid: 1, expired: 0, revoked: 0, total: 1 } } })
  })

  it('looks up and selects the certificate it has just generated', async () => {
    generate.mockResolvedValue({ data: { id: 42, key_id: 'new-host-key', certificate: 'CERT', private_key: 'PRIV' } })
    getById.mockResolvedValue({ data: { id: 42, key_id: 'new-host-key', cert_type: 'host' } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(screen.getByText('sshCertificates.issueCertificate'))
    fireEvent.click(await screen.findByText('sshCertificates.generateKeyPair'))
    const form = document.querySelector('form')
    fireEvent.change(form.querySelector('input'), { target: { value: 'new-host-key' } })
    fireEvent.click(form.querySelector('button[type="submit"]'))

    await waitFor(() => expect(generate).toHaveBeenCalled())
    await waitFor(() => expect(getById).toHaveBeenCalledWith(42))
    // The result view (generated key) still shows behind the now-open detail
    await waitFor(() => expect(screen.getByText('sshCertificates.certificateIssued')).toBeInTheDocument())
  })

  it('selects the certificate it has just imported', async () => {
    importCertificate.mockResolvedValue({ data: { id: 43, key_id: 'imported-key' } })
    getById.mockResolvedValue({ data: { id: 43, key_id: 'imported-key', cert_type: 'user' } })
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(screen.getByText('common.import'))
    const form = await screen.findByText('sshCertificates.importCertDescription').then(el => el.closest('form'))
    fireEvent.change(form.querySelector('textarea'), { target: { value: 'ssh-ed25519 CERT' } })
    fireEvent.click(form.querySelector('button[type="submit"]'))

    await waitFor(() => expect(importCertificate).toHaveBeenCalled())
    await waitFor(() => expect(getById).toHaveBeenCalledWith(43))
  })
})
