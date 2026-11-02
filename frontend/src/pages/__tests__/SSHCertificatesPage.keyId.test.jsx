/**
 * SSHCertificatesPage: the key ID is chosen only where the CA allows it (#432).
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

const NAMED_CA = { id: 1, name: 'Users CA', descr: 'Users CA', ca_type: 'user' }
const OPEN_CA = { id: 2, name: 'Open CA', descr: 'Open CA', ca_type: 'user', allow_custom_key_id: true }

const openForm = async () => {
  render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getByText('sshCertificates.issueCertificate'))
  fireEvent.click(await screen.findByText('sshCertificates.generateKeyPair'))
  return document.querySelector('form')
}

const submit = async (form) => {
  fireEvent.click(form.querySelector('button[type="submit"]'))
  await waitFor(() => expect(generate).toHaveBeenCalled())
  return generate.mock.calls.at(-1)[0]
}

const principals = () => screen.getByPlaceholderText('sshCertificates.modal.principalsPlaceholder')

describe('SSHCertificatesPage: key ID', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: {} })
    generate.mockResolvedValue({ data: { id: 9, key_id: 'k', certificate: 'C', private_key: 'P' } })
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
  })

  it('shows the key ID the CA will set and sends none', async () => {
    casGetAll.mockResolvedValue({ data: [NAMED_CA] })
    const form = await openForm()
    expect(screen.queryByLabelText('sshCertificates.keyId')).toBeNull()
    fireEvent.change(principals(), { target: { value: 'alice, bob' } })
    expect(screen.getByTestId('ssh-key-id-set-by-ca'))
      .toHaveTextContent('sshCertificates.modal.keyIdSetByCa:alice,bob@Users CA')
    const sent = await submit(form)
    expect(sent).not.toHaveProperty('key_id')
    expect(sent.principals).toEqual(['alice', 'bob'])
  })

  it('lets the requester set it where the CA allows it', async () => {
    casGetAll.mockResolvedValue({ data: [OPEN_CA] })
    const form = await openForm()
    fireEvent.change(await screen.findByLabelText('sshCertificates.keyId'), { target: { value: '  ticket-4321 ' } })
    expect((await submit(form)).key_id).toBe('ticket-4321')
  })

  it('leaves it to the CA when the requester sets nothing', async () => {
    casGetAll.mockResolvedValue({ data: [OPEN_CA] })
    const form = await openForm()
    await screen.findByLabelText('sshCertificates.keyId')
    expect(await submit(form)).not.toHaveProperty('key_id')
  })
})
