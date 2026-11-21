/**
 * An SSH CA can be backed by an HSM key: the private key never comes back,
 * the algorithm comes off the card, and one key backs one authority.
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

const access = vi.hoisted(() => ({ hsm: true }))
vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return {
    ...actual,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true,
      canRead: (resource) => resource !== 'hsm' || access.hsm,
    }),
  }
})

const getAll = vi.fn()
const create = vi.fn()
const getEffective = vi.fn()
const getProviders = vi.fn()
const getSigningKeys = vi.fn()
vi.mock('../../services', () => ({
  sshCasService: { getAll: (...a) => getAll(...a), create: (...a) => create(...a), importCA: vi.fn() },
  policiesService: { getEffective: (...a) => getEffective(...a) },
  hsmService: {
    getProviders: (...a) => getProviders(...a),
    getSigningKeys: (...a) => getSigningKeys(...a),
  },
}))

import SSHCAsPage from '../SSHCAsPage'

// A PIV card as the HSM page would list it: a signing key per slot
const CARD_KEYS = [
  { id: 11, label: 'piv-sign', algorithm: 'EC-P384', key_type: 'asymmetric', purpose: 'signing' },
  { id: 12, label: 'piv-auth', algorithm: 'RSA-4096', key_type: 'asymmetric', purpose: 'signing' },
  { id: 13, label: 'ssh-slot', algorithm: 'ED25519', key_type: 'asymmetric', purpose: 'signing' },
  { id: 14, label: 'bp-key', algorithm: 'EC-BP256', key_type: 'asymmetric', purpose: 'signing' },
  { id: 15, label: 'wrap-key', algorithm: 'RSA-2048', key_type: 'symmetric', purpose: 'decrypt' },
]

/** The native select whose label is `labelKey` (the mockup's `.field`) */
function comboboxFor(form, labelKey) {
  const label = [...form.querySelectorAll('label')].find((l) => l.textContent.trim() === labelKey)
  return label ? form.querySelector(`#${CSS.escape(label.htmlFor)}`) : null
}

async function pickOption(select, name) {
  const option = [...select.options].find((o) => (name instanceof RegExp ? name.test(o.textContent) : o.textContent === name))
  await userEvent.selectOptions(select, option)
}

async function openCreateModal() {
  render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  fireEvent.click(screen.getAllByText('sshCas.createCA')[0])
  fireEvent.change(await screen.findByPlaceholderText('sshCas.modal.descriptionPlaceholder'), {
    target: { value: 'New SSH CA' },
  })
  await waitFor(() => expect(getEffective).toHaveBeenCalled())
  return document.querySelector('form')
}

async function openHsmMode() {
  const form = await openCreateModal()
  expect(getProviders).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('cas.create.keyStorageHsm'))
  await waitFor(() => expect(getProviders).toHaveBeenCalled())
  await pickOption(comboboxFor(form, 'cas.create.hsmProvider'), 'PIV (pkcs11)')
  await waitFor(() => expect(getSigningKeys).toHaveBeenCalledWith({ providerId: 3, unused: true }))
  return form
}

describe('SSHCAsPage SSH CA on HSM', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    getAll.mockResolvedValue({ data: [] })
    getEffective.mockResolvedValue({ data: { allowed_key_types: null } })
    getProviders.mockResolvedValue({
      data: [{ id: 3, name: 'PIV', provider_type: 'pkcs11', enabled: true },
             { id: 9, name: 'Retired', provider_type: 'pkcs11', enabled: false }],
    })
    getSigningKeys.mockResolvedValue({ data: CARD_KEYS })
    create.mockResolvedValue({ data: { id: 7, descr: 'New SSH CA', ca_type: 'user', cert_count: 0 } })
  })

  it('asks for the unused keys only: one HSM key backs one authority, X.509 or SSH', async () => {
    await openHsmMode()
    expect(getSigningKeys).toHaveBeenCalledWith({ providerId: 3, unused: true })
  })

  it('offers only the key types OpenSSH certificates know', async () => {
    const form = await openHsmMode()
    const names = [...comboboxFor(form, 'cas.create.hsmExistingKey').options].map(o => o.textContent)
    expect(names).toEqual(expect.arrayContaining(['piv-sign (EC-P384)', 'piv-auth (RSA-4096)']))
    expect(names).not.toEqual(expect.arrayContaining(
      ['ssh-slot (ED25519)', 'bp-key (EC-BP256)', 'wrap-key (RSA-2048)']))
  })

  it('sends the card key and no key type: the server reads it off the card', async () => {
    const form = await openHsmMode()
    await pickOption(comboboxFor(form, 'cas.create.hsmExistingKey'), /^piv-sign/)
    expect(await screen.findByText('sshCas.modal.hsmDerivedKey')).toBeInTheDocument()
    expect(screen.queryByText('sshCas.keyAlgorithm')).toBeNull()

    fireEvent.click(form.querySelector('button[type="submit"]'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    const payload = create.mock.calls[0][0]
    expect(payload.hsm_key_id).toBe(11)
    expect(payload).not.toHaveProperty('key_type')
  })

  it.each([
    [409, "HSM key 'piv-sign' already backs the SSH user CA 'Existing': an HSM key backs one authority only"],
    [403, 'Creating an SSH CA on an HSM key requires the read:hsm permission'],
    [503, 'The HSM provider of this key cannot be reached'],
    [403, 'FIPS mode refuses SoftHSM for a CA key'],
    [403, 'A smart card reader is local to one node: refused in high availability'],
  ])('shows the server refusal %s under the key: %s', async (status, message) => {
    create.mockRejectedValue(Object.assign(new Error(message), { status }))
    const form = await openHsmMode()
    await pickOption(comboboxFor(form, 'cas.create.hsmExistingKey'), /^piv-sign/)
    fireEvent.click(form.querySelector('button[type="submit"]'))
    expect(await screen.findByText(message)).toBeInTheDocument()
    // The modal stays open so the user can pick another key
    expect(document.querySelector('form')).toBeTruthy()
  })

  it('offers no HSM key storage without read:hsm, and says why', async () => {
    access.hsm = false
    try {
      const form = await openCreateModal()
      expect(screen.getByLabelText('cas.create.keyStorageHsm').disabled).toBe(true)
      expect(screen.getByText('sshCas.modal.hsmNeedsRead')).toBeInTheDocument()
      expect(form.querySelector('input[value="software"]').checked).toBe(true)
      expect(getProviders).not.toHaveBeenCalled()
    } finally {
      access.hsm = true
    }
  })

  it('keeps HSM key storage selectable with read:hsm', async () => {
    await openCreateModal()
    expect(screen.getByLabelText('cas.create.keyStorageHsm').disabled).toBe(false)
    expect(screen.queryByText('sshCas.modal.hsmNeedsRead')).toBeNull()
  })

  it('shows a card-backed CA by its key, and keeps that key unchangeable', async () => {
    getAll.mockResolvedValue({ data: [{
      id: 4, descr: 'Card CA', ca_type: 'user', key_type: 'ecdsa-p384',
      key_source: 'hsm', hsm_key_id: 11, hsm_key_label: 'piv-sign', cert_count: 0,
    }] })
    render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())

    fireEvent.click(await screen.findByTitle('common.edit'))
    await waitFor(() => expect(document.querySelector('form')).toBeTruthy())
    const form = document.querySelector('form')
    expect(screen.getByDisplayValue('piv-sign')).toBeInTheDocument()
    expect(screen.getByText('sshCas.modal.keyStorageLockedHelp')).toBeInTheDocument()
    expect([...form.querySelectorAll('input[type="radio"]')].every(r => r.disabled)).toBe(true)
    expect(getProviders).not.toHaveBeenCalled()
    expect(getSigningKeys).not.toHaveBeenCalled()
  })
})
