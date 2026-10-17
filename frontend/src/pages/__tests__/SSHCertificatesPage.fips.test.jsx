/**
 * SSHCertificatesPage in FIPS mode (#399): a generated key pair defaults to
 * ECDSA P-256; outside FIPS mode the default stays Ed25519.
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
const getEffective = vi.fn()
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
  policiesService: { getEffective: (...args) => getEffective(...args) },
}))

import SSHCertificatesPage from '../SSHCertificatesPage'



async function generateWithDefaults(fips) {
  render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getAllByText('sshCertificates.issueCertificate')[0])
  fireEvent.click(await screen.findByText('sshCertificates.generateKeyPair'))
  await waitFor(() => expect(getEffective).toHaveBeenCalled())
  const form = document.querySelector('form')
  // FIPS mode is read asynchronously: Ed25519 leaves the choices once it is known
  if (fips) await waitFor(() => expect(form.textContent).not.toContain('Ed25519'))
  fireEvent.change(form.querySelector('input'), { target: { value: 'alice' } })
  fireEvent.click(form.querySelector('button[type="submit"]'))
  await waitFor(() => expect(generate).toHaveBeenCalled())
  return generate.mock.calls[0][0]
}

describe('SSHCertificatesPage generated key type (#399)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    casGetAll.mockResolvedValue({ data: [{ id: 5, name: 'Users CA', ca_type: 'user' }] })
    getStats.mockResolvedValue({ data: { certificates: { valid: 0, expired: 0, revoked: 0, total: 0 } } })
    generate.mockResolvedValue({ data: { id: 42, key_id: 'alice', certificate: 'CERT', private_key: 'PRIV' } })
    getById.mockResolvedValue({ data: { id: 42, key_id: 'alice', cert_type: 'user' } })
  })

  it('generates ECDSA P-256 in FIPS mode', async () => {
    getEffective.mockResolvedValue({ data: { fips: true } })
    const payload = await generateWithDefaults(true)
    expect(payload.key_type).toBe('ecdsa-p256')
  })

  it('keeps Ed25519 outside FIPS mode', async () => {
    getEffective.mockResolvedValue({ data: {} })
    const payload = await generateWithDefaults(false)
    expect(payload.key_type).toBe('ed25519')
  })
})
