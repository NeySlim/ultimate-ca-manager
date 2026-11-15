/**
 * CreateCAModal on an HSM key: the server's refusals (403 read:hsm, 409 key already
 * backing an authority) show in the form with their message.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  getEffective: vi.fn(),
  getProfiles: vi.fn(),
  getSettings: vi.fn(),
  getSigningKeys: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: mocks.getSigningKeys },
  policiesService: { getEffective: mocks.getEffective },
  systemService: { getComplianceProfiles: mocks.getProfiles },
  settingsService: { getAll: mocks.getSettings },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: mocks.showError }),
}))

vi.mock('../../../hooks', () => ({
  useWebSocket: () => ({ muteToasts: vi.fn() }),
}))

vi.mock('../../../lib/utils', () => ({
  extractData: (r) => r?.data ?? r,
  cn: (...a) => a.filter(Boolean).join(' '),
  downloadBlob: vi.fn(),
}))

vi.mock('../../../components', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, ...props }) => <input aria-label={label || props.name} {...props} />,
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'


const PROVIDERS = [{ id: 2, name: 'token', provider_type: 'pkcs11', enabled: true }]

async function renderModal({ providers = PROVIDERS } = {}) {
  mocks.getProviders.mockImplementation(() =>
    providers instanceof Error ? Promise.reject(providers) : Promise.resolve({ data: providers }))
  mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
  mocks.getProfiles.mockResolvedValue({ data: [] })
  mocks.getSettings.mockResolvedValue({ data: { compliance_profile_default: '' } })
  mocks.getSigningKeys.mockResolvedValue({ data: [{ id: 8, label: 'free', algorithm: 'RSA-3072' }] })
  render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'HSM CA' } })
  await waitFor(() => expect(mocks.getProviders).toHaveBeenCalled())
}

async function pickExistingKey() {
  fireEvent.click(screen.getByLabelText('cas.create.keyStorageHsm'))
  await waitFor(() => expect(screen.getByLabelText('cas.create.hsmProvider')).toBeTruthy())
  fireEvent.change(screen.getByLabelText('cas.create.hsmProvider'), { target: { value: '2' } })
  fireEvent.click(screen.getByLabelText('cas.create.hsmKeyModeExisting'))
  await waitFor(() => expect(screen.getByLabelText('cas.create.hsmExistingKey')).toBeTruthy())
  fireEvent.change(screen.getByLabelText('cas.create.hsmExistingKey'), { target: { value: '8' } })
}

describe('CreateCAModal on an HSM key, server refusals', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each([
    [409, "HSM key 'free' already backs the SSH user CA 'Existing': an HSM key backs one authority only"],
    [403, 'Creating an X.509 CA on an HSM key requires the read:hsm permission'],
  ])('shows the %s refusal in the form, not only as a toast', async (status, message) => {
    mocks.create.mockRejectedValue(Object.assign(new Error(message), { status }))
    await renderModal()
    await pickExistingKey()
    fireEvent.click(screen.getByText('common.createCA'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect((await screen.findByRole('alert')).textContent).toBe(message)
    expect(mocks.showError).toHaveBeenCalledWith(message)
  })

  it('clears the refusal when another key is picked', async () => {
    mocks.create.mockRejectedValue(Object.assign(new Error('refused'), { status: 409 }))
    await renderModal()
    await pickExistingKey()
    fireEvent.click(screen.getByText('common.createCA'))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByLabelText('cas.create.hsmKeyModeGenerate'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('says read:hsm is missing when the providers list is refused, and keeps local storage', async () => {
    await renderModal({ providers: Object.assign(new Error('Forbidden'), { status: 403 }) })
    await waitFor(() => expect(screen.getByLabelText('cas.create.keyStorageHsm').disabled).toBe(true))
    expect(screen.getByText('cas.create.hsmNeedsRead')).toBeTruthy()
    expect(screen.getByLabelText('cas.create.keyStorageLocal').checked).toBe(true)
  })
})
