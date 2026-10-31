/**
 * The issue form offers only the key types the policies of the selected CA and
 * template allow (#397), and falls back to the first allowed one.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn() }))

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getForCA: vi.fn().mockResolvedValue({ data: [] }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

vi.mock('../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, ...props }) => <input aria-label={label || props.name} {...props} />,
  DatePicker: () => null,
  EkuMultiSelect: () => null,
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { IssueCertificateForm } from '../certificates/IssueCertificateForm'

const t = (key) => key
const optionValues = (label) =>
  within(screen.getByLabelText(label)).getAllByRole('option').map((o) => o.value)

function renderForm(effective, onSubmit = vi.fn().mockResolvedValue(undefined)) {
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(
    <IssueCertificateForm
      cas={[{ id: 3, descr: 'Issuing CA', has_private_key: true }]}
      onSubmit={onSubmit} onCancel={() => {}} t={t}
    />
  )
  fireEvent.change(screen.getByLabelText('common.certificateAuthority'), { target: { value: '3' } })
  return onSubmit
}

describe('IssueCertificateForm policy key types (#397)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps every key type when the policies do not restrict them', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalledWith({ ca_id: '3', template_id: undefined }))
    expect(optionValues('common.keyType')).toEqual(['rsa', 'ecdsa', 'ml-dsa'])
    expect(optionValues('common.keySize')).toEqual(['2048', '3072', '4096'])
  })

  it('switches to the first allowed key and submits it', async () => {
    const onSubmit = renderForm({ allowed_key_types: ['RSA-4096', 'EC-P384'], allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keySize')).toEqual(['4096']))
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'ecdsa' } })
    expect(optionValues('common.keySize')).toEqual(['384'])

    fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'host.example.test' } })
    fireEvent.submit(screen.getByPlaceholderText('example.com').closest('form'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ key_type: 'ecdsa', key_size: '384' })
  })

  it('says so and blocks the submit when no key type is allowed', async () => {
    renderForm({ allowed_key_types: ['ED25519'], allowed_digests: null })
    expect(await screen.findByText('certificates.noKeyTypeAllowedByPolicy')).toBeTruthy()
    expect(screen.getByText('certificates.issueCertificate').closest('button').disabled).toBe(true)
  })
})
