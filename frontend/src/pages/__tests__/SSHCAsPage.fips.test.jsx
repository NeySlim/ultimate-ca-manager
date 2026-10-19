/**
 * SSHCAsPage in FIPS mode (#399): a new SSH CA defaults to ECDSA P-256 and
 * Ed25519 is not offered; outside FIPS mode the default stays Ed25519.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  }
})

const getAll = vi.fn()
const create = vi.fn()
const getEffective = vi.fn()
vi.mock('../../services', () => ({
  sshCasService: { getAll: (...a) => getAll(...a), create: (...a) => create(...a), importCA: vi.fn() },
  policiesService: { getEffective: (...a) => getEffective(...a) },
}))

import SSHCAsPage from '../SSHCAsPage'

async function createCa() {
  render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getAllByText('sshCas.createCA')[0])
  fireEvent.change(await screen.findByPlaceholderText('sshCas.modal.descriptionPlaceholder'), {
    target: { value: 'New SSH CA' },
  })
  await waitFor(() => expect(getEffective).toHaveBeenCalled())
  return document.querySelector('form')
}

describe('SSHCAsPage key algorithm in FIPS mode (#399)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [] })
    create.mockResolvedValue({ data: { id: 5, descr: 'New SSH CA', ca_type: 'user', cert_count: 0 } })
  })

  it('creates an ECDSA P-256 CA by default and offers no Ed25519', async () => {
    getEffective.mockResolvedValue({ data: { fips: true } })
    const form = await createCa()
    await waitFor(() => expect(form.textContent).toContain('ECDSA P-256'))
    expect(form.textContent).not.toContain('Ed25519')
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].key_type).toBe('ecdsa-p256')
  })

  it('keeps Ed25519 as the default outside FIPS mode', async () => {
    getEffective.mockResolvedValue({ data: { allowed_key_types: null } })
    const form = await createCa()
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].key_type).toBe('ed25519')
  })
})

describe('SSHCAsPage RSA key size', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [] })
    create.mockResolvedValue({ data: { id: 6, descr: 'New SSH CA', ca_type: 'user', cert_count: 0 } })
    getEffective.mockResolvedValue({ data: {} })
  })

  it('offers no size the server ignored: RSA CAs are 4096-bit', async () => {
    Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
    Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
    Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
    Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
    const user = userEvent.setup()
    const form = await createCa()
    const trigger = [...form.querySelectorAll('[role="combobox"]')].find(el => el.textContent.includes('Ed25519'))
    await user.click(trigger)
    await user.click(await screen.findByRole('option', { name: /^RSA/ }))
    expect(screen.queryByText('sshCas.keySize')).toBeNull()
    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].key_type).toBe('rsa')
    expect(create.mock.calls[0][0]).not.toHaveProperty('key_size')
  })
})
