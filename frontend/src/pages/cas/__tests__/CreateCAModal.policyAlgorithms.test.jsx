/**
 * CreateCAModal offers only the key types and signature hashes the policies
 * in scope allow (#397): the parent CA's for an intermediate, the global ones otherwise.
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

function renderModal(effective) {
  mocks.getProviders.mockResolvedValue({ data: [] })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
}

describe('CreateCAModal policy algorithms (#397)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers every option when no policy restricts them', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => {
      expect(mocks.getEffective).toHaveBeenCalled()
      expect(optionValues('common.keyAlgorithm')).toEqual(['RSA', 'ECDSA'])
      expect(optionValues('common.signatureAlgorithm')).toEqual(['auto', 'sha256', 'sha384', 'sha512'])
    })
  })

  it('switches to an allowed key and sends only allowed choices', async () => {
    renderModal({ allowed_key_types: ['EC-P384'], allowed_digests: ['sha384', 'sha512'] })
    // The three selects settle over separate renders: wait for all of them.
    await waitFor(() => {
      expect(optionValues('common.keyAlgorithm')).toEqual(['ECDSA'])
      expect(optionValues('common.keySize')).toEqual(['secp384r1'])
      expect(optionValues('common.signatureAlgorithm')).toEqual(['auto', 'sha384', 'sha512'])
    })
    expect(screen.getByText('cas.create.digestAutoHint:SHA384')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'Root' } })
    fireEvent.click(screen.getByText('common.createCA'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    const payload = mocks.create.mock.calls[0][0]
    expect(payload.keyAlgo).toBe('ECDSA')
    expect(payload.keySize).toBe('secp384r1')
  })

  it('auto names the weakest allowed hash when the key default is forbidden', async () => {
    renderModal({ allowed_key_types: null, allowed_digests: ['sha512'] })
    await waitFor(() => expect(optionValues('common.signatureAlgorithm')).toEqual(['auto', 'sha512']))
    expect(screen.getByText('cas.create.digestAutoHint:SHA512')).toBeTruthy()
  })

  it('blocks creation when the policies allow no key type', async () => {
    renderModal({ allowed_key_types: ['ED25519'], allowed_digests: null })
    expect(await screen.findByText('cas.create.noKeyTypeAllowedByPolicy')).toBeTruthy()
    expect(screen.getByText('common.createCA').closest('button').disabled).toBe(true)
  })

  it('asks the parent CA policies for an intermediate, the global ones for a root', async () => {
    mocks.getProviders.mockResolvedValue({ data: [] })
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
    render(<CreateCAModal open onClose={vi.fn()} onSuccess={vi.fn()}
      cas={[{ id: 7, descr: 'Parent', has_private_key: true }]} />)
    await waitFor(() => expect(mocks.getEffective).toHaveBeenLastCalledWith({ ca_id: undefined, template_id: undefined }))
    fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '7' } })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenLastCalledWith({ ca_id: '7', template_id: undefined }))
  })
})
