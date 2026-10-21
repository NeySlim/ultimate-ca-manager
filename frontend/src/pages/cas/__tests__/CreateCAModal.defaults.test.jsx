/**
 * CreateCAModal defaults: a new CA is RSA-3072, and an RSA-2048 CA that
 * outlives 2030 is flagged (ANSSI PG-083 and ETSI TS 119 312 horizons).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

describe('CreateCAModal key defaults', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-21T12:00:00Z'))
  })
  afterEach(() => vi.useRealTimers())

  it('creates an RSA-3072 CA by default', async () => {
    await openRoot()
    const payload = await submittedPayload()
    expect(payload.keyAlgo).toBe('RSA')
    expect(payload.keySize).toBe(3072)
  })

  it('switching back to RSA lands on 3072', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ECDSA' } })
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'RSA' } })
    expect(screen.getByLabelText('common.keySize').value).toBe('3072')
  })

  it('flags an RSA-2048 CA valid beyond 2030', async () => {
    await openRoot()
    expect(screen.queryByText('cas.create.rsa2048Horizon')).toBeNull()
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: '2048' } })
    expect(screen.getByText('cas.create.rsa2048Horizon')).toBeTruthy()
  })

  it('does not flag an RSA-2048 CA that expires before 2031', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: '2048' } })
    fireEvent.change(screen.getByLabelText('common.validityPeriod'), { target: { value: '2' } })
    expect(screen.queryByText('cas.create.rsa2048Horizon')).toBeNull()
  })
})
