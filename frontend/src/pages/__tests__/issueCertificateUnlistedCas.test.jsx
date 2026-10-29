/**
 * The issue form says how many CAs it leaves out instead of hiding them in silence (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'

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
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p data-testid={`help-${label}`}>{helperText}</p>}
    </>
  ),
}))

import { IssueCertificateForm } from '../certificates/IssueCertificateForm'

const t = (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key)

function renderForm(cas) {
  mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
  mocks.getAll.mockResolvedValue({ data: [] })
  mocks.getForCA.mockResolvedValue({ data: [] })
  render(<IssueCertificateForm cas={cas} onSubmit={vi.fn()} onCancel={() => {}} t={t} />)
}

describe('IssueCertificateForm CAs that cannot sign (#426)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the signing CA and counts the root imported without its key', () => {
    renderForm([
      { id: 3, descr: 'Issuing CA', has_private_key: true },
      { id: 4, descr: 'Imported root', is_root: true, certificate_only: true, has_private_key: false },
    ])
    const options = within(screen.getByLabelText('common.certificateAuthority')).getAllByRole('option').map((o) => o.value)
    expect(options).toEqual(['3'])
    expect(screen.getByTestId('help-common.certificateAuthority')).toHaveTextContent('cas.notListedForSigning:1')
  })

  it('says nothing when every CA can sign', () => {
    renderForm([{ id: 3, descr: 'Issuing CA', has_private_key: true }])
    expect(screen.queryByTestId('help-common.certificateAuthority')).toBeNull()
  })
})
