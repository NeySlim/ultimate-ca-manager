/**
 * CreateCAModal and ML-DSA (FIPS 204): a third key family whose parameter is the
 * level, no signature hash, absent in FIPS mode and from the HSM types that cannot hold it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { GROUP_PQ, KEY_ALGORITHMS, findAlgorithm } from '../../../lib/keyAlgorithms'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  getEffective: vi.fn(),
  getSigningKeys: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.digest ? `${key}:${opts.digest}` : key) }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: mocks.getSigningKeys },
  policiesService: { getEffective: mocks.getEffective },
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
  Input: ({ label, helperText: _h, ...props }) => <input aria-label={label || props.name} {...props} />,
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <span>{helperText}</span>}
    </>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
const ML_DSA_65 = findAlgorithm('ML-DSA-65')

const optionValues = (label) =>
  within(screen.getByLabelText(label)).getAllByRole('option').map((o) => o.value)

function renderModal(effective, providers = [], cas = []) {
  mocks.getProviders.mockResolvedValue({ data: providers })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(<CreateCAModal open onClose={vi.fn()} cas={cas} onSuccess={vi.fn()} />)
}

const PARENTS = [
  { id: 7, name: 'RSA root', has_private_key: true, key_type: 'RSA 3072' },
  { id: 8, name: 'PQ root', has_private_key: true, key_type: 'ML-DSA-65' },
  { id: 9, name: 'P-384 root', has_private_key: true, key_type: 'EC secp384r1' },
  { id: 10, name: 'RSA-8192 root', has_private_key: true, key_type: 'RSA 8192' },
  { id: 11, name: 'Ed25519 root', has_private_key: true, key_type: 'Ed25519' },
]

async function intermediateUnder(parentId, keyAlgo, effective = { allowed_key_types: null, allowed_digests: null }) {
  renderModal(effective, [], PARENTS)
  await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('ML-DSA'))
  fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
  fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: String(parentId) } })
  fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: keyAlgo } })
}

async function submit() {
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'PQ Root' } })
  fireEvent.click(screen.getByText('common.createCA'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0]
}

describe('CreateCAModal ML-DSA', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers ML-DSA with its three levels and defaults to 65', async () => {
    expect(PQ_ROWS).toHaveLength(3)
    renderModal({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('ML-DSA'))
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ML-DSA' } })
    expect(optionValues('common.keySize')).toEqual(PQ_ROWS.map(a => a.ca[1]))
    expect(screen.getByLabelText('common.keySize').value).toBe(ML_DSA_65.ca[1])
  })

  it('hides the signature hash and sends keyAlgo=ML-DSA keySize=65 without a digest', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('ML-DSA'))
    expect(screen.getByLabelText('common.signatureAlgorithm')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ML-DSA' } })
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    expect(screen.queryByLabelText('cas.signatureScheme')).toBeNull()

    const payload = await submit()
    expect(payload).toMatchObject({ keyAlgo: 'ML-DSA', keySize: 65 })
    expect(payload).not.toHaveProperty('hashAlgorithm')
    expect(payload).not.toHaveProperty('signatureScheme')
  })

  it('creates an ML-DSA-87 CA when it is all the policies allow, even with no hash allowed', async () => {
    renderModal({ allowed_key_types: ['ML-DSA-87'], allowed_digests: [] })
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toEqual(['ML-DSA']))
    // The algorithm switches in an effect, one render after the options narrow
    await waitFor(() => expect(optionValues('common.keySize')).toEqual(['87']))
    expect(screen.queryByText('cas.create.noDigestAllowedByPolicy')).toBeNull()
    expect(screen.getByText('common.createCA').closest('button').disabled).toBe(false)
    expect(await submit()).toMatchObject({ keyAlgo: 'ML-DSA', keySize: 87 })
  })

  it('offers no ML-DSA in FIPS mode', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toEqual(['RSA', 'ECDSA']))
  })

  it('offers no ML-DSA on a build without it, locally or on an HSM', async () => {
    const provider = await onHsm([{ id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true }],
      { allowed_key_types: null, allowed_digests: null, ml_dsa: false })
    fireEvent.change(provider, { target: { value: '1' } })
    const hsmOffered = optionValues('cas.create.hsmKeyAlgorithm')
    expect(hsmOffered).toContain('EC-BP256')
    expect(hsmOffered.filter(l => PQ_ROWS.some(a => a.label === l))).toEqual([])
    fireEvent.click(screen.getByLabelText('cas.create.keyStorageLocal'))
    expect(optionValues('common.keyAlgorithm')).toEqual(['RSA', 'ECDSA', 'EdDSA'])
  })

  async function onHsm(providers, effective = { allowed_key_types: null, allowed_digests: null }) {
    renderModal(effective, providers)
    fireEvent.click(await screen.findByLabelText('cas.create.keyStorageHsm'))
    const provider = await screen.findByLabelText('cas.create.hsmProvider')
    await waitFor(() => expect(within(provider).getAllByRole('option').length).toBe(providers.length))
    return provider
  }

  it('offers ML-DSA in FIPS mode locally when the module approves it, never on an HSM', async () => {
    const fipsKeys = ['RSA-2048', 'EC-P256', ...PQ_ROWS.map(a => a.label)]
    await onHsm([{ id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true }],
      { allowed_key_types: null, allowed_digests: null, fips: true, fips_key_types: fipsKeys })
    fireEvent.change(screen.getByLabelText('cas.create.hsmProvider'), { target: { value: '1' } })
    const hsmOffered = optionValues('cas.create.hsmKeyAlgorithm')
    expect(hsmOffered).toContain('EC-P256')
    expect(hsmOffered.filter(l => PQ_ROWS.some(a => a.label === l))).toEqual([])
    fireEvent.click(screen.getByLabelText('cas.create.keyStorageLocal'))
    expect(optionValues('common.keyAlgorithm')).toContain('ML-DSA')
  })

  it('generates ML-DSA keys on the providers that hold them, not on Azure', async () => {
    const provider = await onHsm([
      { id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true },
      { id: 2, name: 'bao', provider_type: 'openbao', enabled: true },
      { id: 3, name: 'kms', provider_type: 'google-kms', enabled: true },
      { id: 4, name: 'vault', provider_type: 'azure-keyvault', enabled: true },
    ])
    const pqOffered = () => optionValues('cas.create.hsmKeyAlgorithm').filter(l => PQ_ROWS.some(a => a.label === l))
    for (const id of ['1', '2', '3']) {
      fireEvent.change(provider, { target: { value: id } })
      expect(pqOffered()).toEqual(PQ_ROWS.map(a => a.label))
    }
    fireEvent.change(provider, { target: { value: '4' } })
    expect(optionValues('cas.create.hsmKeyAlgorithm').length).toBeGreaterThan(0)
    expect(pqOffered()).toEqual([])
  })

  it('says ML-DSA on Google Cloud KMS is untested', async () => {
    const provider = await onHsm([
      { id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true },
      { id: 3, name: 'kms', provider_type: 'google-kms', enabled: true },
    ])
    fireEvent.change(provider, { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('cas.create.hsmKeyAlgorithm'), { target: { value: 'ML-DSA-65' } })
    expect(screen.queryByText('hsm.mldsaUntestedGoogleKms')).toBeNull()
    fireEvent.change(provider, { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('cas.create.hsmKeyAlgorithm'), { target: { value: 'ML-DSA-65' } })
    expect(screen.getByText('hsm.mldsaUntestedGoogleKms')).toBeTruthy()
  })

  it('creates an HSM ML-DSA root without a digest and with digitalSignature', async () => {
    const provider = await onHsm([{ id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true }])
    fireEvent.change(provider, { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('cas.create.hsmKeyLabel'), { target: { value: 'pq-root' } })
    fireEvent.change(screen.getByLabelText('cas.create.hsmKeyAlgorithm'), { target: { value: 'ML-DSA-65' } })
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    const payload = await submit()
    expect(payload).toMatchObject({ hsmProviderId: 1, hsmKeyLabel: 'pq-root', hsmKeyAlgorithm: 'ML-DSA-65' })
    expect(payload).not.toHaveProperty('hashAlgorithm')
    expect(payload.keyUsage).toEqual(['digitalSignature', 'keyCertSign', 'cRLSign'])
  })

  it('names no digest for an existing HSM ML-DSA key', async () => {
    mocks.getSigningKeys.mockResolvedValue({ data: [{ id: 6, label: 'pq', algorithm: 'ML-DSA-87' }] })
    const provider = await onHsm([{ id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true }])
    fireEvent.change(provider, { target: { value: '1' } })
    fireEvent.click(screen.getByLabelText('cas.create.hsmKeyModeExisting'))
    fireEvent.change(await screen.findByLabelText('cas.create.hsmExistingKey'), { target: { value: '6' } })
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    const payload = await submit()
    expect(payload).toMatchObject({ hsmKeyId: 6 })
    expect(payload).not.toHaveProperty('hashAlgorithm')
  })

  // The parent signs an intermediate: its key, not the child's, decides whether a digest applies
  it('offers and sends a digest for an ML-DSA intermediate under an RSA parent', async () => {
    await intermediateUnder(7, 'ML-DSA')
    fireEvent.change(screen.getByLabelText('common.signatureAlgorithm'), { target: { value: 'sha512' } })
    expect(await submit()).toMatchObject({ keyAlgo: 'ML-DSA', hashAlgorithm: 'sha512' })
  })

  it("proposes the parent's digest for 'auto' when the child takes none", async () => {
    await intermediateUnder(9, 'ML-DSA')
    expect(screen.getByText('cas.create.digestAutoHint:SHA384')).toBeTruthy()
  })

  it('offers a digest for an ML-DSA intermediate under a parent key outside the registry', async () => {
    expect(findAlgorithm('RSA-8192')).toBeFalsy()
    await intermediateUnder(10, 'ML-DSA')
    expect(screen.getByLabelText('common.signatureAlgorithm')).toBeTruthy()
    expect(screen.getByText('cas.create.digestAutoHint:SHA256')).toBeTruthy()
    expect(await submit()).toHaveProperty('hashAlgorithm')
  })

  it('hides the digest of an RSA intermediate under an ML-DSA parent', async () => {
    await intermediateUnder(8, 'RSA')
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    expect(await submit()).not.toHaveProperty('hashAlgorithm')
  })

  it('hides the digest of an intermediate under an Ed25519 parent', async () => {
    await intermediateUnder(11, 'ML-DSA')
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    expect(await submit()).not.toHaveProperty('hashAlgorithm')
  })

  it('gives an ML-DSA root digitalSignature, as the API does by default', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('ML-DSA'))
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ML-DSA' } })
    expect((await submit()).keyUsage).toEqual(['digitalSignature', 'keyCertSign', 'cRLSign'])
  })

  it('keeps an RSA root to keyCertSign and cRLSign', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('ML-DSA'))
    expect((await submit()).keyUsage).toEqual(['keyCertSign', 'cRLSign'])
  })

  it('offers PSS for an existing HSM RSA key the registry does not list', async () => {
    mocks.getSigningKeys.mockResolvedValue({ data: [{ id: 5, label: 'big', algorithm: 'RSA-8192' }] })
    renderModal({ allowed_key_types: null, allowed_digests: null },
      [{ id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true }])
    fireEvent.click(await screen.findByLabelText('cas.create.keyStorageHsm'))
    const provider = await screen.findByLabelText('cas.create.hsmProvider')
    await waitFor(() => expect(within(provider).getAllByRole('option').length).toBe(1))
    fireEvent.change(provider, { target: { value: '1' } })
    fireEvent.click(screen.getByLabelText('cas.create.hsmKeyModeExisting'))
    const key = await screen.findByLabelText('cas.create.hsmExistingKey')
    fireEvent.change(key, { target: { value: '5' } })
    expect(screen.getByLabelText('cas.signatureScheme')).toBeTruthy()
  })

  it('lets an RSA intermediate under an ML-DSA parent through a policy allowing no digest', async () => {
    await intermediateUnder(8, 'RSA', { allowed_key_types: null, allowed_digests: [] })
    expect(screen.queryByText('cas.create.noDigestAllowedByPolicy')).toBeNull()
    expect(screen.getByText('common.createCA').closest('button').disabled).toBe(false)
  })
})
