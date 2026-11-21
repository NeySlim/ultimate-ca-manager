/** CreateCAModal: the CSR of a pending CA is saved under its label, non-ASCII kept. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  getEffective: vi.fn(),
  getProfiles: vi.fn(),
  getSettings: vi.fn(),
  getSigningKeys: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: mocks.getSigningKeys },
  policiesService: { getEffective: mocks.getEffective },
  systemService: { getComplianceProfiles: mocks.getProfiles },
  settingsService: { getAll: mocks.getSettings },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: mocks.showError }),
}))

vi.mock('../../../hooks', () => ({
  useWebSocket: () => ({ muteToasts: vi.fn() }),
}))

vi.mock('../../../lib/utils', async () => {
  const actual = await vi.importActual('../../../lib/utils')
  return { ...actual, extractData: (r) => r?.data ?? r }
})

vi.mock('../../../components', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, ...props }) => <input aria-label={label || props.name} {...props} />,
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'

describe('CreateCAModal pending CSR download', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  it('keeps the non-ASCII description in the saved file name', async () => {
    const names = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { names.push(this.download) })
    mocks.getProviders.mockResolvedValue({ data: [] })
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
    mocks.getProfiles.mockResolvedValue({ data: [] })
    mocks.getSettings.mockResolvedValue({ data: { compliance_profile_default: '' } })
    mocks.create.mockResolvedValue({ data: { pending: true, csr_pem: 'PEM', descr: '\u30c6\u30b9\u30c8/\u7528:CA', common_name: 'x' } })
    render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('common.commonName (CN)'), { target: { value: 'x' } })
    fireEvent.click(screen.getByText('common.createCA'))
    await waitFor(() => expect(names).toHaveLength(1))
    expect(names[0]).toBe('\u30c6\u30b9\u30c8_\u7528_CA.csr')
    click.mockRestore()
  })
})
