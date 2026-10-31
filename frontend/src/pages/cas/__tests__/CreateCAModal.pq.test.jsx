/**
 * CreateCAModal and ML-DSA (FIPS 204): a third key family whose parameter is the
 * level, no signature hash, absent in FIPS mode and from every HSM provider.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { GROUP_PQ, KEY_ALGORITHMS, findAlgorithm } from '../../../lib/keyAlgorithms'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  getEffective: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.digest ? `${key}:${opts.digest}` : key) }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: vi.fn() },
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

function renderModal(effective, providers = []) {
  mocks.getProviders.mockResolvedValue({ data: providers })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
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
    expect(optionValues('common.keySize')).toEqual(['87'])
    expect(screen.queryByText('cas.create.noDigestAllowedByPolicy')).toBeNull()
    expect(screen.getByText('common.createCA').closest('button').disabled).toBe(false)
    expect(await submit()).toMatchObject({ keyAlgo: 'ML-DSA', keySize: 87 })
  })

  it('offers no ML-DSA in FIPS mode', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues('common.keyAlgorithm')).toEqual(['RSA', 'ECDSA']))
  })

  it('generates no ML-DSA key on any HSM provider', async () => {
    const providers = [
      { id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true },
      { id: 2, name: 'bao', provider_type: 'openbao', enabled: true },
    ]
    renderModal({ allowed_key_types: null, allowed_digests: null }, providers)
    fireEvent.click(await screen.findByLabelText('cas.create.keyStorageHsm'))
    const provider = await screen.findByLabelText('cas.create.hsmProvider')
    await waitFor(() => expect(within(provider).getAllByRole('option').length).toBe(2))
    for (const id of ['1', '2']) {
      fireEvent.change(provider, { target: { value: id } })
      const offered = optionValues('cas.create.hsmKeyAlgorithm')
      expect(offered.length).toBeGreaterThan(0)
      expect(offered.filter(l => PQ_ROWS.some(a => a.label === l))).toEqual([])
    }
  })
})
