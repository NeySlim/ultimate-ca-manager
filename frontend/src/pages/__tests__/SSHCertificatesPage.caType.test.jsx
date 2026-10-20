/**
 * SSHCertificatesPage: the certificate type follows the type of the selected CA.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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

const HOST_CA = { id: 1, name: 'Hosts CA', descr: 'Hosts CA', ca_type: 'host' }
const USER_CA = { id: 2, name: 'Users CA', descr: 'Users CA', ca_type: 'user' }

const openForm = async () => {
  render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getByText('sshCertificates.issueCertificate'))
  fireEvent.click(await screen.findByText('sshCertificates.generateKeyPair'))
  return document.querySelector('form')
}

const submitAndGetType = async (form) => {
  fireEvent.change(form.querySelector('input'), { target: { value: 'k' } })
  fireEvent.click(form.querySelector('button[type="submit"]'))
  await waitFor(() => expect(generate).toHaveBeenCalled())
  return generate.mock.calls.at(-1)[0].cert_type
}

describe('SSHCertificatesPage: certificate type follows the CA', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset(); getStats.mockReset(); generate.mockReset(); casGetAll.mockReset()
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: { certificates: { valid: 0, expired: 0, revoked: 0, total: 0 } } })
    generate.mockResolvedValue({ data: { id: 9, key_id: 'k', certificate: 'C', private_key: 'P' } })
    Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
  })

  it('switches to the type of the default CA when it differs from user', async () => {
    casGetAll.mockResolvedValue({ data: [HOST_CA, USER_CA] })
    const form = await openForm()
    expect(await submitAndGetType(form)).toBe('host')
  })

  it('follows the CA the user picks in the selector', async () => {
    casGetAll.mockResolvedValue({ data: [USER_CA, HOST_CA] })
    const form = await openForm()
    const triggers = form.querySelectorAll('[role="combobox"]')
    fireEvent.keyDown(triggers[0], { key: 'Enter' })
    fireEvent.click(await screen.findByRole('option', { name: 'Hosts CA' }))
    await waitFor(() => expect(form.querySelectorAll('[role="combobox"]')[1]).toHaveTextContent('sshCertificates.typeHost'))
    expect(await submitAndGetType(form)).toBe('host')
  })

  it('keeps the type when it already matches the CA', async () => {
    casGetAll.mockResolvedValue({ data: [USER_CA] })
    const form = await openForm()
    expect(await submitAndGetType(form)).toBe('user')
  })
})
