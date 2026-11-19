/**
 * CreateCAModal: an intermediate CA is created only once a parent is chosen;
 * the server refuses it otherwise rather than make a self-signed root.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: vi.fn() },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
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
  Select: ({ label, options = [], value, onChange }) => (
    <select
      aria-label={label}
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'

const CAS = [{ id: 7, name: 'Signing CA', has_private_key: true }]

function openIntermediate() {
  mocks.getProviders.mockResolvedValue({ data: [] })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  render(<CreateCAModal open onClose={vi.fn()} cas={CAS} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'Child CA' } })
  fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
}

describe('CreateCAModal parent requirement', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps the create button off until a parent is chosen', () => {
    openIntermediate()
    expect(screen.getByText('common.createCA')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '7' } })
    expect(screen.getByText('common.createCA')).not.toBeDisabled()
  })

  it('does not send a request without a parent', () => {
    openIntermediate()
    fireEvent.submit(screen.getByText('common.createCA').closest('form'))
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('sends the chosen parent', async () => {
    openIntermediate()
    fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '7' } })
    fireEvent.click(screen.getByText('common.createCA'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0].parentCAId).toBe('7')
  })

  it('a root needs no parent', async () => {
    mocks.getProviders.mockResolvedValue({ data: [] })
    mocks.create.mockResolvedValue({ data: { id: 1 } })
    render(<CreateCAModal open onClose={vi.fn()} cas={CAS} onSuccess={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'Root' } })
    expect(screen.getByText('common.createCA')).not.toBeDisabled()
  })
})
