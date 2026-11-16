/**
 * An SSH CA can be backed by an HSM key: the private key never comes back,
 * the algorithm comes off the card, and one key signs one CA per role.
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
import { HsmBadge } from '../cas/CAListUtils'

// A PIV card as the HSM page would list it: a signing key per slot
const CARD_KEYS = [
  { id: 11, label: 'piv-sign', algorithm: 'EC-P384', key_type: 'asymmetric', purpose: 'signing' },
  { id: 12, label: 'piv-auth', algorithm: 'RSA-4096', key_type: 'asymmetric', purpose: 'signing' },
  { id: 13, label: 'ssh-slot', algorithm: 'ED25519', key_type: 'asymmetric', purpose: 'signing' },
  { id: 14, label: 'bp-key', algorithm: 'EC-BP256', key_type: 'asymmetric', purpose: 'signing' },
  { id: 15, label: 'wrap-key', algorithm: 'RSA-2048', key_type: 'symmetric', purpose: 'decrypt' },
]

beforeEach(() => {
  // Radix Select needs these in jsdom
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
  Element.prototype.scrollIntoView = () => {}
})

/** The Radix trigger of the Select whose label is `labelKey` */
function comboboxFor(form, labelKey) {
  for (const el of form.querySelectorAll('[role="combobox"]')) {
    const label = [...(el.parentElement?.children || [])]
      .find(c => c.tagName === 'LABEL' && c.textContent.trim() === labelKey)
    if (label) return el
  }
  return null
}

async function pickOption(trigger, name) {
  await userEvent.click(trigger)
  await userEvent.click(await screen.findByRole('option', { name }))
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
  await waitFor(() => expect(getSigningKeys).toHaveBeenCalledWith({ providerId: 3, unused: false }))
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

  it('asks for every signing key: a key signing an X.509 CA is still free here', async () => {
    await openHsmMode()
    expect(getSigningKeys).toHaveBeenCalledWith({ providerId: 3, unused: false })
  })

  it('offers only the key types OpenSSH certificates know', async () => {
    const form = await openHsmMode()
    await userEvent.click(comboboxFor(form, 'cas.create.hsmExistingKey'))
    const names = (await screen.findAllByRole('option')).map(o => o.textContent)
    await userEvent.keyboard('{Escape}')
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

  it('names the role a key already serves, and blocks the CA until the role changes', async () => {
    getAll.mockResolvedValue({ data: [{
      id: 4, descr: 'Existing host CA', ca_type: 'host', key_type: 'ecdsa-p384',
      key_source: 'hsm', hsm_key_id: 11, hsm_key_label: 'piv-sign', cert_count: 0,
    }] })
    const form = await openHsmMode()

    // A user CA on this key is legal: OpenSSH keeps the roles apart
    await pickOption(comboboxFor(form, 'cas.create.hsmExistingKey'), /^piv-sign/)
    const submit = form.querySelector('button[type="submit"]')
    expect(submit.disabled).toBe(false)

    await pickOption(comboboxFor(form, 'sshCas.caType'), 'sshCas.typeHost')
    expect(await screen.findByText('sshCas.modal.hsmKeyInUse')).toBeInTheDocument()
    expect(submit.disabled).toBe(true)

    await pickOption(comboboxFor(form, 'sshCas.caType'), 'sshCas.typeUser')
    await waitFor(() => expect(submit.disabled).toBe(false))
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

describe('the HSM badge an SSH CA and an X.509 CA share', () => {
  it('marks both, and nothing for a software CA', () => {
    const translate = (key) => key
    expect(render(<HsmBadge ca={{ key_source: 'hsm', hsm_key_label: 'piv-sign' }} t={translate} />)
      .container.textContent).toBe('HSM')
    expect(render(<HsmBadge ca={{ uses_hsm: true, hsm_key_label: 'ca-key' }} t={translate} />)
      .container.textContent).toBe('HSM')
    expect(render(<HsmBadge ca={{ key_source: 'software' }} t={translate} />).container).toBeEmptyDOMElement()
  })
})
