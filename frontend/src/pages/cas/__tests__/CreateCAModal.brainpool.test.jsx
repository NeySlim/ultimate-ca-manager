/**
 * CreateCAModal and Brainpool (phase 4.4): curves in the key size list, FIPS mode
 * hides them, and an HSM generates them only on a PKCS#11 provider.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

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
  Input: ({ label, ...props }) => <input aria-label={label || props.name} {...props} />,
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

function renderModal(effective, providers = []) {
  mocks.getProviders.mockResolvedValue({ data: providers })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
}

describe('CreateCAModal Brainpool', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the curves and sends the one picked, with its matching digest', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ECDSA' } })
    expect(optionValues('common.keySize')).toEqual(
      ['prime256v1', 'secp384r1', 'secp521r1', 'brainpoolP256r1', 'brainpoolP384r1', 'brainpoolP512r1'])
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: 'brainpoolP384r1' } })
    expect(screen.getByText('cas.create.digestAutoHint:SHA384')).toBeTruthy()
    expect(screen.getByRole('note').textContent).toContain('common.keyGroups.brainpoolWarning')

    fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'Root' } })
    fireEvent.click(screen.getByText('common.createCA'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0]).toMatchObject({ keyAlgo: 'ECDSA', keySize: 'brainpoolP384r1' })
  })

  it('hides the curves in FIPS mode', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ECDSA' } })
    await waitFor(() => expect(optionValues('common.keySize')).toEqual(['prime256v1', 'secp384r1', 'secp521r1']))
  })

  it('generates an HSM key as Brainpool on a PKCS#11 provider only', async () => {
    const providers = [
      { id: 1, name: 'tokens', provider_type: 'pkcs11', enabled: true },
      { id: 2, name: 'vault', provider_type: 'azure', enabled: true },
    ]
    renderModal({ allowed_key_types: null, allowed_digests: null }, providers)
    fireEvent.click(await screen.findByLabelText('cas.create.keyStorageHsm'))
    const provider = await screen.findByLabelText('cas.create.hsmProvider')
    await waitFor(() => expect(within(provider).getAllByRole('option').length).toBe(2))

    fireEvent.change(provider, { target: { value: '2' } })
    expect(optionValues('cas.create.hsmKeyAlgorithm')).toEqual(
      ['RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521'])
    fireEvent.change(provider, { target: { value: '1' } })
    expect(optionValues('cas.create.hsmKeyAlgorithm')).toEqual(
      ['RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521', 'EC-BP256', 'EC-BP384', 'EC-BP512'])
  })
})
