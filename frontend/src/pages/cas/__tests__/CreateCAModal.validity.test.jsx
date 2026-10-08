/**
 * CreateCAModal: a CA lasts a preset number of years or any number of days
 * (#378), where only 5, 10, 15 or 20 years were offered.
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
  Input: ({ label, helperText: _h, ...props }) => <input aria-label={label || props.name} {...props} />,
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

async function openRoot() {
  mocks.getProviders.mockResolvedValue({ data: [] })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), {
    target: { value: 'Short Root' },
  })
}

async function submittedPayload() {
  fireEvent.click(screen.getByText('common.createCA'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0]
}

describe('CreateCAModal validity (#378)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps sending whole years for a preset', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('common.validityPeriod'), { target: { value: '2' } })
    const payload = await submittedPayload()
    expect(payload.validityYears).toBe(2)
    expect(payload).not.toHaveProperty('validityDays')
  })

  it('sends days for a custom validity', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('common.validityPeriod'), { target: { value: 'custom' } })
    fireEvent.change(screen.getByLabelText('cas.validityDays'), { target: { value: '400' } })
    const payload = await submittedPayload()
    expect(payload.validityDays).toBe(400)
    expect(payload).not.toHaveProperty('validityYears')
  })

  it('reopens on the default validity after a custom one', async () => {
    mocks.getProviders.mockResolvedValue({ data: [] })
    const props = { onClose: vi.fn(), cas: [], onSuccess: vi.fn() }
    const { rerender } = render(<CreateCAModal open {...props} />)
    fireEvent.change(screen.getByLabelText('common.validityPeriod'), { target: { value: 'custom' } })
    rerender(<CreateCAModal open={false} {...props} />)
    rerender(<CreateCAModal open {...props} />)
    expect(screen.getByLabelText('common.validityPeriod').value).toBe('10')
    expect(screen.queryByLabelText('cas.validityDays')).toBeNull()
  })

  it('offers short presets below five years', async () => {
    await openRoot()
    const values = Array.from(screen.getByLabelText('common.validityPeriod').options).map(o => o.value)
    expect(values).toEqual(expect.arrayContaining(['1', '2', '3', '5', 'custom']))
  })
})
