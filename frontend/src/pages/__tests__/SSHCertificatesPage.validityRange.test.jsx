/**
 * SSHCertificatesPage: the custom validity range reaches the server, as UTC.
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

const CA = { id: 1, name: 'Users CA', descr: 'Users CA', ca_type: 'user' }

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
  Element.prototype.scrollIntoView = () => {}
})

describe('SSHCertificatesPage: validity range', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: {} })
    casGetAll.mockResolvedValue({ data: [CA] })
    generate.mockResolvedValue({ data: { id: 9, key_id: 'k', certificate: 'C', private_key: 'P' } })
  })

  it('sends the typed range as UTC instants', async () => {
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sshCertificates.issueCertificate'))
    fireEvent.click(await screen.findByText('sshCertificates.generateKeyPair'))
    const form = document.querySelector('form')
    fireEvent.change(screen.getByPlaceholderText('sshCertificates.modal.principalsPlaceholder'), { target: { value: 'alice' } })
    await userEvent.click(screen.getAllByRole('combobox').find((c) => c.textContent.includes('sshCertificates.presets.24h')))
    await userEvent.click(await screen.findByRole('option', { name: 'sshCertificates.presets.custom' }))
    const [from, to] = form.querySelectorAll('input[type="datetime-local"]')
    fireEvent.change(from, { target: { value: '2031-03-04T10:00' } })
    fireEvent.change(to, { target: { value: '2031-03-05T10:00' } })
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(generate).toHaveBeenCalled())
    const sent = generate.mock.calls.at(-1)[0]
    expect(sent.valid_from).toBe(new Date('2031-03-04T10:00').toISOString())
    expect(sent.valid_to).toBe(new Date('2031-03-05T10:00').toISOString())
    expect(sent.validity_seconds).toBeUndefined()
  })
})
