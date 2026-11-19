/**
 * SSHCertificatesPage: critical options are offered for user certificates only,
 * OpenSSH defines none for host certificates (PROTOCOL.certkeys).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
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


describe('SSHCertificatesPage: critical options', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset(); getStats.mockReset(); generate.mockReset(); casGetAll.mockReset()
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: { certificates: { valid: 0, expired: 0, revoked: 0, total: 0 } } })
    generate.mockResolvedValue({ data: { id: 9, key_id: 'k', certificate: 'C', private_key: 'P' } })
    Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
  })

  it('are not offered for a host CA', async () => {
    casGetAll.mockResolvedValue({ data: [HOST_CA] })
    await openForm()
    await waitFor(() => expect(screen.getAllByText('sshCertificates.typeHost').length).toBeGreaterThan(0))
    expect(screen.queryByText('sshCertificates.criticalOptions')).toBeNull()
  })

  it('are offered and sent for a user CA', async () => {
    casGetAll.mockResolvedValue({ data: [USER_CA] })
    const form = await openForm()
    fireEvent.click(await screen.findByText('sshCertificates.criticalOptions'))
    fireEvent.change(screen.getByPlaceholderText('e.g. /usr/bin/rsync'), { target: { value: '/bin/true' } })
    fireEvent.change(form.querySelector('input'), { target: { value: 'k' } })
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(generate).toHaveBeenCalled())
    expect(generate.mock.calls.at(-1)[0].critical_options).toEqual({ 'force-command': '/bin/true' })
  })
})
