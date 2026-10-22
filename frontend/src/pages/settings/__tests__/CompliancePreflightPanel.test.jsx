import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  preflight: vi.fn(),
  profiles: vi.fn(),
  getSettings: vi.fn(),
  updateBulk: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  permissions: ['admin:system', 'admin:settings'],
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  Select: ({ label, options = [], value, onChange, disabled }) => (
    <select aria-label={label} value={value ?? ''} disabled={disabled} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))
vi.mock('../../../hooks', () => ({
  usePermission: () => ({ hasPermission: (p) => mocks.permissions.includes(p) }),
}))
vi.mock('../../../lib/utils', () => ({
  extractData: (r) => r?.data ?? r,
  cn: (...a) => a.filter(Boolean).join(' '),
}))
vi.mock('../../../services', () => ({
  systemService: { getCompliancePreflight: mocks.preflight, getComplianceProfiles: mocks.profiles },
  settingsService: { getAll: mocks.getSettings, updateBulk: mocks.updateBulk },
}))

import CompliancePreflightPanel from '../CompliancePreflightPanel'

const PROFILES = [
  { name: 'anssi', title: 'ANSSI', reference: 'ANSSI-PG-083 3.00' },
  { name: 'bsi', title: 'BSI', reference: 'BSI-TR-02102-1 2026-01' },
  { name: 'eu-acm', title: 'EU ACM', reference: 'ECCG-ACM 2.0' },
]

describe('CompliancePreflightPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.permissions = ['admin:system', 'admin:settings']
    mocks.profiles.mockResolvedValue({ data: PROFILES })
    mocks.getSettings.mockResolvedValue({ data: { compliance_profile_default: 'anssi' } })
    mocks.updateBulk.mockResolvedValue({})
  })

  it('runs the chosen profile only when asked and groups the findings', async () => {
    mocks.preflight.mockResolvedValue({ data: {
      ready: false, summary: { blocker: 1, warning: 0, info: 0 },
      findings: [{ id: 'ca.key', severity: 'blocker', title: 'RSA-2048 CA', remedy: 'Use RSA-3072', count: 1, examples: ['Root (#1)'] }],
      errors: [],
    } })
    render(<CompliancePreflightPanel />)
    expect(mocks.preflight).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('settings.compliancePreflight.profile'), { target: { value: 'bsi' } })
    fireEvent.click(screen.getByText('settings.compliancePreflight.run'))
    const report = await screen.findByTestId('compliance-preflight-report')
    expect(mocks.preflight).toHaveBeenCalledWith('bsi')
    expect(report.textContent).toContain('settings.compliancePreflight.notReady')
    expect(report.textContent).toContain('RSA-2048 CA')
    expect(report.textContent).toContain('Use RSA-3072')
  })

  it('shows a failed check without a report', async () => {
    mocks.preflight.mockRejectedValue(new Error('Forbidden'))
    render(<CompliancePreflightPanel />)
    fireEvent.click(screen.getByText('settings.compliancePreflight.run'))
    await waitFor(() => expect(screen.getByText('Forbidden')).toBeTruthy())
    expect(screen.queryByTestId('compliance-preflight-report')).toBeNull()
  })

  it('reads the default and saves a new one', async () => {
    render(<CompliancePreflightPanel />)
    const select = screen.getByLabelText('settings.compliancePreflight.defaultProfile')
    await waitFor(() => expect(select.value).toBe('anssi'))
    fireEvent.change(select, { target: { value: 'bsi' } })
    await waitFor(() => expect(mocks.updateBulk).toHaveBeenCalledWith({ compliance_profile_default: 'bsi' }))
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalled())
    fireEvent.change(select, { target: { value: '' } })
    await waitFor(() => expect(mocks.updateBulk).toHaveBeenLastCalledWith({ compliance_profile_default: '' }))
  })

  it('locks the default without admin:settings', async () => {
    mocks.permissions = ['admin:system']
    render(<CompliancePreflightPanel />)
    expect(screen.getByLabelText('settings.compliancePreflight.defaultProfile').disabled).toBe(true)
  })

  it('sets the default without admin:system, and offers no check', async () => {
    mocks.permissions = ['admin:settings']
    render(<CompliancePreflightPanel />)
    const select = screen.getByLabelText('settings.compliancePreflight.defaultProfile')
    await waitFor(() => expect(select.value).toBe('anssi'))
    expect(select.disabled).toBe(false)
    expect(screen.queryByText('settings.compliancePreflight.run')).toBeNull()
  })

  it('keeps the previous default shown when saving fails', async () => {
    mocks.updateBulk.mockRejectedValue(new Error('nope'))
    render(<CompliancePreflightPanel />)
    const select = screen.getByLabelText('settings.compliancePreflight.defaultProfile')
    await waitFor(() => expect(select.value).toBe('anssi'))
    fireEvent.change(select, { target: { value: 'bsi' } })
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('nope'))
    expect(select.value).toBe('anssi')
  })
})
