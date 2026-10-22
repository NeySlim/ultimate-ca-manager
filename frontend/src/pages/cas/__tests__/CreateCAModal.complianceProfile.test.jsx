/**
 * CreateCAModal compliance profile: a selector, the parent's profile (else the
 * global default) proposed, and the choices cut down to what the profile allows.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  getEffective: vi.fn(),
  getProfiles: vi.fn(),
  getSettings: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: vi.fn() },
  policiesService: { getEffective: mocks.getEffective },
  systemService: { getComplianceProfiles: mocks.getProfiles },
  settingsService: { getAll: mocks.getSettings },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
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

const DIGESTS = ['sha256', 'sha384', 'sha512']
const PROFILES = [
  {
    name: 'anssi', title: 'ANSSI', reference: 'ANSSI-PG-083 3.00',
    allowed_key_types: ['RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521'],
    allowed_digests: DIGESTS, allowed_signature_schemes: ['rsa_pkcs1v15', 'rsa_pss', 'ecdsa'],
    key_type_horizons: { 'RSA-2048': '2030-12-31' }, require_hsm_ca_key: false,
  },
  {
    name: 'bsi', title: 'BSI', reference: 'BSI-TR-02102-1 2026-01',
    allowed_key_types: ['RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521'],
    allowed_digests: DIGESTS, allowed_signature_schemes: ['rsa_pss', 'ecdsa'],
    key_type_horizons: {}, require_hsm_ca_key: false,
  },
  {
    name: 'eu-acm', title: 'EU ACM', reference: 'ECCG-ACM 2.0',
    allowed_key_types: ['RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521'],
    allowed_digests: DIGESTS, allowed_signature_schemes: ['rsa_pkcs1v15', 'rsa_pss', 'ecdsa'],
    key_type_horizons: { 'RSA-2048': '2028-12-31' }, require_hsm_ca_key: true,
  },
]

const optionValues = (label) =>
  within(screen.getByLabelText(label)).getAllByRole('option').map((o) => o.value)
const profileSelect = () => screen.getByLabelText('cas.complianceProfile')

async function renderModal({ cas = [], defaultProfile = '', providers = [] } = {}) {
  mocks.getProviders.mockResolvedValue({ data: providers })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
  mocks.getProfiles.mockResolvedValue({ data: PROFILES })
  mocks.getSettings.mockResolvedValue({ data: { compliance_profile_default: defaultProfile } })
  render(<CreateCAModal open onClose={vi.fn()} cas={cas} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'Profile CA' } })
  await waitFor(() => expect(mocks.getProfiles).toHaveBeenCalled())
}

async function submittedPayload() {
  fireEvent.click(screen.getByText('common.createCA'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0]
}

describe('CreateCAModal compliance profile', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers none and the three profiles', async () => {
    await renderModal()
    await waitFor(() => expect(optionValues('cas.complianceProfile')).toEqual(['', 'anssi', 'bsi', 'eu-acm']))
  })

  it('sends no profile key when nothing was chosen and no default exists', async () => {
    await renderModal()
    expect(await submittedPayload()).not.toHaveProperty('complianceProfile')
  })

  it('sends the profile that was chosen', async () => {
    await renderModal()
    fireEvent.change(profileSelect(), { target: { value: 'anssi' } })
    expect((await submittedPayload()).complianceProfile).toBe('anssi')
  })

  it('proposes the global default for a root CA', async () => {
    await renderModal({ defaultProfile: 'bsi' })
    await waitFor(() => expect(profileSelect().value).toBe('bsi'))
    expect((await submittedPayload()).complianceProfile).toBe('bsi')
  })

  it('sends an explicit null when the proposal is set aside', async () => {
    await renderModal({ defaultProfile: 'bsi' })
    await waitFor(() => expect(profileSelect().value).toBe('bsi'))
    fireEvent.change(profileSelect(), { target: { value: '' } })
    expect((await submittedPayload()).complianceProfile).toBeNull()
  })

  it('proposes the parent profile for an intermediate CA, over the default', async () => {
    const cas = [
      { id: 7, name: 'Parent', has_private_key: true, compliance_profile: 'anssi' },
      { id: 8, name: 'Plain parent', has_private_key: true, compliance_profile: null },
    ]
    await renderModal({ cas, defaultProfile: 'bsi' })
    fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '7' } })
    await waitFor(() => expect(profileSelect().value).toBe('anssi'))
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '8' } })
    await waitFor(() => expect(profileSelect().value).toBe('bsi'))
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '7' } })
    expect((await submittedPayload()).complianceProfile).toBe('anssi')
  })

  it('keeps a manual choice when the parent changes', async () => {
    const cas = [{ id: 7, name: 'Parent', has_private_key: true, compliance_profile: 'anssi' }]
    await renderModal({ cas })
    fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
    fireEvent.change(profileSelect(), { target: { value: 'eu-acm' } })
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '7' } })
    expect(profileSelect().value).toBe('eu-acm')
  })

  it('under bsi: no RSA-2048, RSA-PSS imposed', async () => {
    await renderModal()
    fireEvent.change(profileSelect(), { target: { value: 'bsi' } })
    await waitFor(() => expect(optionValues('common.keySize')).toEqual(['3072', '4096']))
    expect(optionValues('cas.signatureScheme')).toEqual(['pss'])
    await waitFor(() => expect(screen.getByLabelText('cas.signatureScheme').value).toBe('pss'))
    const payload = await submittedPayload()
    expect(payload.signatureScheme).toBe('pss')
    expect(payload.keySize).toBe(3072)
  })

  it('under bsi a key that was RSA-2048 moves to an allowed size', async () => {
    await renderModal()
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: '2048' } })
    fireEvent.change(profileSelect(), { target: { value: 'bsi' } })
    await waitFor(() => expect(screen.getByLabelText('common.keySize').value).toBe('3072'))
  })

  it('under anssi both RSA schemes stay available', async () => {
    await renderModal()
    fireEvent.change(profileSelect(), { target: { value: 'anssi' } })
    await waitFor(() => expect(optionValues('cas.signatureScheme')).toEqual(['pkcs1v15', 'pss']))
  })

  it('under eu-acm the key goes on an HSM and local storage is off', async () => {
    const providers = [{ id: 2, name: 'token', provider_type: 'pkcs11', enabled: true }]
    await renderModal({ providers })
    expect(screen.getByLabelText('cas.create.keyStorageLocal').disabled).toBe(false)
    fireEvent.change(profileSelect(), { target: { value: 'eu-acm' } })
    await waitFor(() => expect(screen.getByLabelText('cas.create.keyStorageLocal').disabled).toBe(true))
    expect(screen.getByLabelText('cas.create.keyStorageHsm').checked).toBe(true)
    expect(screen.queryByLabelText('common.keySize')).toBeNull()
    await waitFor(() => expect(screen.getByLabelText('cas.create.hsmProvider')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('cas.create.hsmProvider'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('cas.create.hsmKeyLabel'), { target: { value: 'acm-key' } })
    const payload = await submittedPayload()
    expect(payload.hsmProviderId).toBe(2)
    expect(payload.complianceProfile).toBe('eu-acm')
  })

  it('warns when the CA would outlive the profile horizon for its key', async () => {
    await renderModal()
    fireEvent.change(profileSelect(), { target: { value: 'anssi' } })
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: '2048' } })
    fireEvent.change(screen.getByLabelText('common.validityPeriod'), { target: { value: '10' } })
    await waitFor(() => expect(screen.getByText('cas.create.profileHorizon')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: '3072' } })
    await waitFor(() => expect(screen.queryByText('cas.create.profileHorizon')).toBeNull())
  })

  it('blocks creation when the profile leaves no RSA scheme for the key', async () => {
    const providers = [{ id: 1, name: 'vault', provider_type: 'azure-keyvault', enabled: true }]
    await renderModal({ providers })
    fireEvent.click(screen.getByLabelText('cas.create.keyStorageHsm'))
    await waitFor(() => expect(screen.getByLabelText('cas.create.hsmProvider')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('cas.create.hsmProvider'), { target: { value: '1' } })
    fireEvent.change(profileSelect(), { target: { value: 'bsi' } })
    await waitFor(() => expect(screen.getByText('cas.create.noSchemeAllowedByProfile')).toBeTruthy())
    expect(screen.getByText('common.createCA').disabled).toBe(true)
  })
})
