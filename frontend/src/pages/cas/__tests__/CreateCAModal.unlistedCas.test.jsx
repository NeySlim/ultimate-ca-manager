/**
 * The parent CA picker of an intermediate lists the CAs able to sign and
 * counts the others (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getProviders: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key) }),
}))

vi.mock('../../../services', () => ({
  casService: { create: vi.fn() },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: vi.fn() },
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
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'

const CAS = [
  { id: 1, name: 'Signing CA', has_private_key: true },
  { id: 2, name: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, name: 'Offline CA', has_private_key: true, offline: true },
]

describe('CreateCAModal parent CA picker (#426)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getProviders.mockResolvedValue({ data: [] })
  })

  it('offers only the CA that can sign as parent and counts the others', () => {
    render(<CreateCAModal open onClose={vi.fn()} cas={CAS} onSuccess={vi.fn()} />)
    const type = screen.getAllByRole('combobox').find((s) => within(s).queryByText('cas.intermediateCASigned'))
    fireEvent.change(type, { target: { value: 'intermediate' } })
    const field = screen.getByTestId('field-cas.parentCA')
    expect(within(field).getAllByRole('option').map((o) => o.textContent)).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })
})
