/**
 * IssueCertificateForm and ML-DSA (FIPS 204): a third key type sent as
 * key_type=ml-dsa key_size=<level>, kept when an ML-DSA template is picked.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { GROUP_PQ, KEY_ALGORITHMS, findAlgorithm } from '../../lib/keyAlgorithms'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn(), templates: [] }))

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: mocks.templates })),
    getForCA: vi.fn(() => Promise.resolve({ data: mocks.templates })),
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

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
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

async function submit(onSubmit) {
  fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'pq.example.test' } })
  fireEvent.submit(screen.getByPlaceholderText('example.com').closest('form'))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
  return onSubmit.mock.calls[0][0]
}

describe('IssueCertificateForm ML-DSA', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.templates = []
  })

  it('offers ml-dsa with its levels and sends key_type=ml-dsa key_size=65 by default', async () => {
    expect(PQ_ROWS).toHaveLength(3)
    const onSubmit = renderForm({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    expect(optionValues('common.keyType')).toContain('ml-dsa')
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'ml-dsa' } })
    expect(optionValues('common.keySize')).toEqual(PQ_ROWS.map(a => a.issue[1]))
    expect(screen.getByLabelText('common.keySize').value).toBe('65')
    expect(await submit(onSubmit)).toMatchObject({ key_type: 'ml-dsa', key_size: '65' })
  })

  it('keeps an ML-DSA template as ML-DSA, never ECDSA', async () => {
    mocks.templates = [{ id: 9, name: 'PQ server', template_type: 'web_server', key_type: 'ML-DSA-87', dn_template: {} }]
    const onSubmit = renderForm({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(optionValues('certificates.templateOptional')).toContain('9'))
    fireEvent.change(screen.getByLabelText('certificates.templateOptional'), { target: { value: '9' } })
    await waitFor(() => expect(screen.getByLabelText('common.keyType').value).toBe('ml-dsa'))
    expect(screen.getByLabelText('common.keySize').value).toBe(findAlgorithm('ML-DSA-87').issue[1])
    expect(await submit(onSubmit)).toMatchObject({ key_type: 'ml-dsa', key_size: '87' })
  })

  it('switches to ML-DSA when it is all the policies allow', async () => {
    const onSubmit = renderForm({ allowed_key_types: ['ML-DSA-44'], allowed_digests: null })
    await waitFor(() => expect(optionValues('common.keyType')).toEqual(['ml-dsa']))
    expect(optionValues('common.keySize')).toEqual(['44'])
    expect(await submit(onSubmit)).toMatchObject({ key_type: 'ml-dsa', key_size: '44' })
  })

  it('offers no ML-DSA in FIPS mode', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues('common.keyType')).not.toContain('ml-dsa'))
    expect(optionValues('common.keyType').length).toBeGreaterThan(0)
  })
})
