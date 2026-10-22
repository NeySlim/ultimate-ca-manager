/**
 * The issue form offers the Brainpool curves with a compatibility notice, maps a
 * Brainpool template onto them, and drops them in FIPS mode (phase 4.4).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn(), getAll: vi.fn(), getForCA: vi.fn() }))

vi.mock('../../services', () => ({
  templatesService: { getAll: mocks.getAll, getForCA: mocks.getForCA },
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

function renderForm(effective, templates = []) {
  mocks.getEffective.mockResolvedValue({ data: effective })
  mocks.getAll.mockResolvedValue({ data: templates })
  mocks.getForCA.mockResolvedValue({ data: templates })
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  render(
    <IssueCertificateForm
      cas={[{ id: 3, descr: 'Issuing CA', has_private_key: true }]}
      onSubmit={onSubmit} onCancel={() => {}} t={t}
    />
  )
  fireEvent.change(screen.getByLabelText('common.certificateAuthority'), { target: { value: '3' } })
  return onSubmit
}

describe('IssueCertificateForm Brainpool', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the curves and warns while one is selected', async () => {
    const onSubmit = renderForm({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'ecdsa' } })
    expect(optionValues('common.keySize')).toEqual(
      ['256', '384', '521', 'brainpoolP256r1', 'brainpoolP384r1', 'brainpoolP512r1'])
    expect(screen.queryByRole('note')).toBeNull()

    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: 'brainpoolP384r1' } })
    expect(screen.getByRole('note').textContent).toContain('common.keyGroups.brainpoolWarning')

    fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'host.example.test' } })
    fireEvent.submit(screen.getByPlaceholderText('example.com').closest('form'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ key_type: 'ecdsa', key_size: 'brainpoolP384r1' })
  })

  it('follows a Brainpool template', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null },
      [{ id: 9, name: 'Bp', key_type: 'EC-BP512', template_type: 'custom' }])
    const picker = await screen.findByLabelText('certificates.templateOptional')
    await waitFor(() => expect(within(picker).getAllByRole('option').length).toBeGreaterThan(1))
    fireEvent.change(picker, { target: { value: '9' } })
    await waitFor(() => expect(screen.getByLabelText('common.keySize').value).toBe('brainpoolP512r1'))
  })

  it('drops the curves in FIPS mode', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null, fips: true })
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'ecdsa' } })
    await waitFor(() => expect(optionValues('common.keySize')).toEqual(['256', '384', '521']))
  })
})
