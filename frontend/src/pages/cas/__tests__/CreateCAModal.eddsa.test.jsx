/**
 * CreateCAModal and EdDSA (#436): Ed25519 and Ed448 generated for a CA, no signature
 * hash, absent in FIPS mode and from every HSM key list.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

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

const optionValues = (label) =>
  within(screen.getByLabelText(label)).getAllByRole('option').map((o) => o.value)

const OPEN = { allowed_key_types: null, allowed_digests: null }

function renderModal(effective = OPEN, providers = [], cas = []) {
  mocks.getProviders.mockResolvedValue({ data: providers })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(<CreateCAModal open onClose={vi.fn()} cas={cas} onSuccess={vi.fn()} />)
}

async function submit() {
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'Ed Root' } })
  fireEvent.click(screen.getByText('common.createCA'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0]
}

describe('CreateCAModal EdDSA', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers Ed25519 and Ed448, sends EdDSA + Ed25519 without a digest', async () => {
    renderModal()
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('EdDSA'))
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'EdDSA' } })
    expect(optionValues('common.keySize')).toEqual(['Ed25519', 'Ed448'])
    expect(screen.getByLabelText('common.keySize').value).toBe('Ed25519')
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    expect(screen.queryByLabelText('cas.signatureScheme')).toBeNull()
    const payload = await submit()
    expect(payload).toMatchObject({ keyAlgo: 'EdDSA', keySize: 'Ed25519' })
    expect(payload).not.toHaveProperty('hashAlgorithm')
    expect(payload).not.toHaveProperty('signatureScheme')
    expect(payload.keyUsage).toEqual(['keyCertSign', 'cRLSign'])
  })

  it('creates an Ed448 CA when it is all the policies allow', async () => {
    renderModal({ allowed_key_types: ['ED448'], allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toEqual(['EdDSA']))
    await waitFor(() => expect(optionValues('common.keySize')).toEqual(['Ed448']))
    expect(await submit()).toMatchObject({ keyAlgo: 'EdDSA', keySize: 'Ed448' })
  })

  it('offers no EdDSA in FIPS mode', async () => {
    renderModal({ ...OPEN, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).not.toContain('EdDSA'))
  })

  it('asks no digest of an RSA intermediate under an Ed25519 parent', async () => {
    renderModal(OPEN, [], [{ id: 11, name: 'Ed25519 root', has_private_key: true, key_type: 'Ed25519' }])
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toContain('EdDSA'))
    fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '11' } })
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'RSA' } })
    expect(screen.queryByLabelText('common.signatureAlgorithm')).toBeNull()
    expect(await submit()).not.toHaveProperty('hashAlgorithm')
  })

  it('generates no EdDSA key on any HSM type', async () => {
    const providers = ['pkcs11', 'openbao', 'google-kms', 'azure-keyvault'].map((type, i) => (
      { id: i + 1, name: type, provider_type: type, enabled: true }))
    renderModal(OPEN, providers)
    fireEvent.click(await screen.findByLabelText('cas.create.keyStorageHsm'))
    const provider = await screen.findByLabelText('cas.create.hsmProvider')
    await waitFor(() => expect(within(provider).getAllByRole('option').length).toBe(providers.length))
    for (const { id } of providers) {
      fireEvent.change(provider, { target: { value: String(id) } })
      const offered = optionValues('cas.create.hsmKeyAlgorithm')
      expect(offered.length).toBeGreaterThan(0)
      expect(offered.filter(l => l.startsWith('ED'))).toEqual([])
    }
  })
})
