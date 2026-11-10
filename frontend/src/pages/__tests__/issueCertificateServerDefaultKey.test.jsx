/**
 * The issue form starts from the key the server names as default for the chosen CA and
 * template, keeps a key the user picked, and never invents one when the server is silent.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn(), templates: [] }))

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn(async () => ({ data: mocks.templates })),
    getForCA: vi.fn(async () => ({ data: mocks.templates })),
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
    <select aria-label={label} value={value ?? ''} data-state-value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { IssueCertificateForm } from '../certificates/IssueCertificateForm'

const t = (key) => key
const state = (label) => screen.getByLabelText(label).dataset.stateValue
const CAS = [{ id: 3, descr: 'CA three', has_private_key: true }, { id: 4, descr: 'CA four', has_private_key: true }]

function renderForm(onSubmit = vi.fn().mockResolvedValue(undefined)) {
  render(<IssueCertificateForm cas={CAS} onSubmit={onSubmit} onCancel={() => {}} t={t} />)
  return onSubmit
}
const pickTemplate = (id) => fireEvent.change(screen.getByLabelText('certificates.templateOptional'), { target: { value: id } })
const TEMPLATES = [
  { id: 7, name: 'EC template', key_type: 'EC-P384', dn_template: {} },
  { id: 8, name: 'Keyless template', key_type: '', dn_template: {} },
]
const pickCa = (id) => fireEvent.change(screen.getByLabelText('common.certificateAuthority'), { target: { value: id } })

describe('IssueCertificateForm server default key', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.templates = [] })

  it('follows the default of the chosen CA', async () => {
    mocks.getEffective.mockImplementation(async ({ ca_id }) => ({
      data: { allowed_key_types: null, default_key_type: ca_id === '4' ? 'EC-P384' : 'RSA-3072' },
    }))
    renderForm()
    pickCa('3')
    await waitFor(() => expect(state('common.keyType')).toBe('rsa'))
    await waitFor(() => expect(state('common.keySize')).toBe('3072'))
    pickCa('4')
    await waitFor(() => expect(state('common.keyType')).toBe('ecdsa'))
    await waitFor(() => expect(state('common.keySize')).toBe('384'))
  })

  it('keeps the key the user chose when the CA changes', async () => {
    mocks.getEffective.mockImplementation(async ({ ca_id }) => ({
      data: { allowed_key_types: null, default_key_type: ca_id === '4' ? 'EC-P384' : 'RSA-3072' },
    }))
    renderForm()
    pickCa('3')
    await waitFor(() => expect(state('common.keyType')).toBe('rsa'))
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'ml-dsa' } })
    pickCa('4')
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalledWith({ ca_id: '4', template_id: undefined }))
    await new Promise((r) => setTimeout(r, 20))
    expect(state('common.keyType')).toBe('ml-dsa')
  })

  it('preselects the server default when a policy restricts the key types', async () => {
    mocks.getEffective.mockImplementation(async ({ ca_id }) => ({
      data: ca_id === '4'
        ? { allowed_key_types: ['RSA-4096', 'EC-P384'], default_key_type: 'EC-P384' }
        : { allowed_key_types: null, default_key_type: 'RSA-3072' },
    }))
    renderForm()
    pickCa('3')
    await waitFor(() => expect(state('common.keySize')).toBe('3072'))
    pickCa('4')
    await waitFor(() => expect(state('common.keyType')).toBe('ecdsa'))
    await waitFor(() => expect(state('common.keySize')).toBe('384'))
  })

  it('preselects nothing and submits no key when the server does not answer', async () => {
    mocks.getEffective.mockRejectedValue(new Error('down'))
    const onSubmit = renderForm()
    pickCa('3')
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 20))
    expect(state('common.keyType')).toBe('')
    fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'host.example.test' } })
    fireEvent.submit(screen.getByPlaceholderText('example.com').closest('form'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].key_type).toBeUndefined()
  })

  it('keeps the key the user chose across a keyless template and a CA change', async () => {
    mocks.templates = TEMPLATES
    mocks.getEffective.mockImplementation(async ({ ca_id }) => ({
      data: { allowed_key_types: null, default_key_type: ca_id === '4' ? 'EC-P384' : 'RSA-3072' },
    }))
    renderForm()
    pickCa('3')
    await waitFor(() => expect(state('common.keyType')).toBe('rsa'))
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'ml-dsa' } })
    await screen.findByLabelText('certificates.templateOptional')
    pickTemplate('8')
    pickCa('4')
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalledWith({ ca_id: '4', template_id: '8' }))
    await new Promise((r) => setTimeout(r, 20))
    expect(state('common.keyType')).toBe('ml-dsa')
  })
})
