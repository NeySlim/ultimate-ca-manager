/**
 * CreateCAModal — onSuccess receives the created CA so the caller can open it.
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
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'

describe('CreateCAModal onSuccess payload', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls onSuccess with the CA casService.create returned', async () => {
    mocks.getProviders.mockResolvedValue({ data: [] })
    mocks.create.mockResolvedValue({ data: { id: 55, common_name: 'Root CA' } })
    const onSuccess = vi.fn()
    render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={onSuccess} />)
    fireEvent.change(screen.getByLabelText('common.commonName (CN)'), {
      target: { value: 'Root CA' },
    })
    fireEvent.click(screen.getByText('common.createCA'))
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith({ id: 55, common_name: 'Root CA' }))
  })
})
