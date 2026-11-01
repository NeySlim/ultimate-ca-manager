/**
 * Hybrid pair (RFC 9763): the form sends hybrid: { classical, pq } and the API
 * issues two linked certificates. Lists come from the key registry.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { GROUP_PQ, KEY_ALGORITHMS } from '../../../lib/keyAlgorithms'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn() }))

vi.mock('../../../services', () => ({
  templatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: [] })),
    getForCA: vi.fn(() => Promise.resolve({ data: [] })),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

vi.mock('../../../components', () => ({
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

import { IssueCertificateForm } from '../IssueCertificateForm'

const t = (key) => key
const PQ_LABELS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ && a.generate && a.issue).map(a => a.label)
const CLASSICAL_LABELS = KEY_ALGORITHMS.filter(a => a.group !== GROUP_PQ && a.generate && a.issue).map(a => a.label)
const optionValues = (label) =>
  within(screen.getByLabelText(label)).getAllByRole('option').map((o) => o.value)

function renderForm(effective) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
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

async function submit(onSubmit) {
  fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'pair.example.test' } })
  fireEvent.submit(screen.getByPlaceholderText('example.com').closest('form'))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
  return onSubmit.mock.calls[0][0]
}

const OPEN = { allowed_key_types: null, allowed_digests: null }

describe('IssueCertificateForm hybrid pair', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends hybrid: { classical, pq } with the chosen pair', async () => {
    const onSubmit = renderForm(OPEN)
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    fireEvent.click(await screen.findByLabelText('certificates.hybrid.toggle'))
    expect(optionValues('certificates.hybrid.classical')).toEqual(CLASSICAL_LABELS)
    expect(optionValues('certificates.hybrid.pq')).toEqual(PQ_LABELS)
    fireEvent.change(screen.getByLabelText('certificates.hybrid.classical'), { target: { value: 'EC-P256' } })
    fireEvent.change(screen.getByLabelText('certificates.hybrid.pq'), { target: { value: 'ML-DSA-65' } })
    const payload = await submit(onSubmit)
    expect(payload.hybrid).toEqual({ classical: 'EC-P256', pq: 'ML-DSA-65' })
    // The classical member's key travels as the request's key too
    expect(payload).toMatchObject({ key_type: 'ecdsa', key_size: '256' })
  })

  it('sends no hybrid member for a single certificate', async () => {
    const onSubmit = renderForm(OPEN)
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    expect(screen.queryByLabelText('certificates.hybrid.classical')).toBeNull()
    expect(await submit(onSubmit)).not.toHaveProperty('hybrid')
  })

  it('offers no pair when the policies allow no ML-DSA key', async () => {
    renderForm({ allowed_key_types: ['RSA-2048', 'EC-P256'], allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyType')).toEqual(['rsa', 'ecdsa']))
    expect(screen.queryByLabelText('certificates.hybrid.toggle')).toBeNull()
  })

  it('offers no pair in FIPS mode', async () => {
    renderForm({ ...OPEN, fips: true })
    await waitFor(() => expect(optionValues('common.keyType')).not.toContain('ml-dsa'))
    expect(screen.queryByLabelText('certificates.hybrid.toggle')).toBeNull()
  })

  it('keeps each list to what the policies allow', async () => {
    renderForm({ allowed_key_types: ['EC-P384', 'ML-DSA-87', 'RSA-2048'], allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyType')).toContain('ml-dsa'))
    fireEvent.click(screen.getByLabelText('certificates.hybrid.toggle'))
    expect(optionValues('certificates.hybrid.classical')).toEqual(
      CLASSICAL_LABELS.filter(l => ['EC-P384', 'RSA-2048'].includes(l)))
    expect(optionValues('certificates.hybrid.pq')).toEqual(['ML-DSA-87'])
  })

  it('offers ML-DSA in the pair only when the policies refuse it alone', async () => {
    renderForm({ allowed_key_types: ['EC-P256', 'ML-DSA-65', 'ML-DSA-87'], allowed_digests: null,
      pq_standalone: true })
    fireEvent.click(await screen.findByLabelText('certificates.hybrid.toggle'))
    expect(optionValues('certificates.hybrid.pq')).toEqual(['ML-DSA-65', 'ML-DSA-87'])
    fireEvent.click(screen.getByLabelText('certificates.hybrid.toggle'))
    expect(optionValues('common.keyType')).toEqual(['ecdsa'])
  })
})
