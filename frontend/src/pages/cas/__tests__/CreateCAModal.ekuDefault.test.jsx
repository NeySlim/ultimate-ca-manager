/**
 * CreateCAModal — an intermediate CA carries no EKU unless the operator asks
 * for one (#228 follow-up). A serverAuth-only issuing CA makes OpenSSL-based
 * validators reject every clientAuth leaf beneath it, the very defect v2.196
 * closed on the API path.
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

const CAS = [{ id: 1, name: 'Signing CA', has_private_key: true }]

async function openIntermediate() {
  mocks.getProviders.mockResolvedValue({ data: [] })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  render(<CreateCAModal open onClose={vi.fn()} cas={CAS} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), {
    target: { value: 'Org Issuing CA' },
  })
  fireEvent.change(screen.getByLabelText('common.type'), { target: { value: 'intermediate' } })
  fireEvent.change(screen.getByLabelText('cas.parentCA'), { target: { value: '1' } })
}

async function submittedPayload() {
  fireEvent.click(screen.getByText('common.createCA'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0]
}

describe('CreateCAModal EKU default', () => {
  beforeEach(() => vi.clearAllMocks())

  it('creates an intermediate CA with no EKU unless serverAuth is ticked', async () => {
    await openIntermediate()
    const payload = await submittedPayload()
    expect(payload.type).toBe('intermediate')
    expect(payload.extendedKeyUsage).toEqual([])
  })

  it('still sends serverAuth when the operator ticks the box', async () => {
    await openIntermediate()
    fireEvent.click(screen.getByText('cas.create.certificateProfile'))
    fireEvent.click(screen.getByLabelText('cas.create.ekuServerAuth'))
    const payload = await submittedPayload()
    expect(payload.extendedKeyUsage).toEqual(['serverAuth'])
  })
})
