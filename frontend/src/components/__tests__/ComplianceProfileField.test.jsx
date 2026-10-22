/**
 * The compliance profile of a CA: shown in the details, attached or changed only
 * after the preflight of that profile on that CA and an explicit confirmation,
 * removed after a confirmation, and never offered without write:cas.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  preflight: vi.fn(),
  profiles: vi.fn(),
  showConfirm: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  onChanged: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.profile ? `${key}:${opts.profile}` : key),
    i18n: { language: 'en' },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess, showError: mocks.showError, showConfirm: mocks.showConfirm,
  }),
}))
vi.mock('../../services', () => ({
  casService: { update: mocks.update },
  systemService: { getCompliancePreflight: mocks.preflight, getComplianceProfiles: mocks.profiles },
}))

vi.mock('../Select', () => ({
  SelectComponent: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      <option value="" />
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { ComplianceProfileField } from '../cas/ComplianceProfileField'

const PROFILES = [
  { name: 'anssi', title: 'ANSSI', reference: 'ANSSI-PG-083 3.00' },
  { name: 'bsi', title: 'BSI', reference: 'BSI-TR-02102-1 2026-01' },
  { name: 'eu-acm', title: 'EU ACM', reference: 'ECCG-ACM 2.0' },
]
const REPORT = {
  profile: { name: 'bsi' }, ca_id: 3, ready: false,
  summary: { blocker: 1, warning: 1, info: 0 },
  findings: [
    { id: 'ca.key', severity: 'blocker', title: 'RSA-2048 key is below the profile', remedy: 'Create a CA with RSA-3072', count: 1, examples: ['Probe CA (#3)'] },
    { id: 'ca.scheme', severity: 'warning', title: 'PKCS#1 v1.5 signatures', remedy: 'Switch to RSA-PSS', count: 1, examples: ['Probe CA (#3)'] },
  ],
  errors: [],
}
const CA = { id: 3, descr: 'Probe CA', compliance_profile: null }

function renderField(props = {}) {
  return render(<ComplianceProfileField ca={CA} canWrite canAttach onChanged={mocks.onChanged} {...props} />)
}

async function pickBsi() {
  fireEvent.click(screen.getByText('cas.compliance.attach'))
  fireEvent.change(await screen.findByLabelText('cas.compliance.pickProfile'), { target: { value: 'bsi' } })
}

describe('ComplianceProfileField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.profiles.mockResolvedValue({ data: PROFILES })
    mocks.preflight.mockResolvedValue({ data: REPORT })
    mocks.update.mockResolvedValue({ data: { ...CA, compliance_profile: 'bsi' } })
  })

  it('shows none, or the profile with its reference', async () => {
    const { unmount } = renderField()
    expect(screen.getByText('cas.complianceProfileNone')).toBeTruthy()
    unmount()
    renderField({ ca: { ...CA, compliance_profile: 'bsi' } })
    expect(await screen.findByText('BSI (BSI-TR-02102-1 2026-01)')).toBeTruthy()
  })

  it('runs the preflight on this CA, lists the findings, and patches only after confirmation', async () => {
    renderField()
    await pickBsi()
    await waitFor(() => expect(mocks.preflight).toHaveBeenCalledWith('bsi', 3))
    expect(await screen.findByText('RSA-2048 key is below the profile')).toBeTruthy()
    expect(screen.getByText('PKCS#1 v1.5 signatures')).toBeTruthy()
    expect(screen.getByTestId('compliance-attach-statement').textContent)
      .toBe('cas.compliance.confirmAttach:BSI (BSI-TR-02102-1 2026-01)')
    expect(mocks.update).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('cas.compliance.confirmButton:BSI (BSI-TR-02102-1 2026-01)'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(3, { complianceProfile: 'bsi' }))
    expect(mocks.onChanged).toHaveBeenCalledWith(expect.objectContaining({ compliance_profile: 'bsi' }))
  })

  it('cannot confirm before the report has arrived', async () => {
    mocks.preflight.mockReturnValue(new Promise(() => {}))
    renderField()
    await pickBsi()
    await waitFor(() => expect(mocks.preflight).toHaveBeenCalled())
    const button = screen.getByText('cas.compliance.confirmButton:BSI (BSI-TR-02102-1 2026-01)')
    expect(button.closest('button').disabled).toBe(true)
    fireEvent.click(button)
    expect(mocks.update).not.toHaveBeenCalled()
  })

  it('does not patch when the preflight fails', async () => {
    mocks.preflight.mockRejectedValue(new Error('Forbidden'))
    renderField()
    await pickBsi()
    expect(await screen.findByText('Forbidden')).toBeTruthy()
    expect(screen.queryByTestId('compliance-attach-statement')).toBeNull()
    fireEvent.click(screen.getByText('cas.compliance.confirmButton:BSI (BSI-TR-02102-1 2026-01)'))
    expect(mocks.update).not.toHaveBeenCalled()
  })

  it('does not patch when the dialog is cancelled', async () => {
    renderField()
    await pickBsi()
    await screen.findByText('RSA-2048 key is below the profile')
    fireEvent.click(screen.getByText('common.cancel'))
    await waitFor(() => expect(screen.queryByTestId('compliance-attach-report')).toBeNull())
    expect(mocks.update).not.toHaveBeenCalled()
  })

  it('offers a change that leaves out the current profile', async () => {
    renderField({ ca: { ...CA, compliance_profile: 'bsi' } })
    fireEvent.click(screen.getByText('cas.compliance.change'))
    const names = (await screen.findAllByRole('option')).map((o) => o.textContent)
    expect(names.some((n) => n.startsWith('BSI'))).toBe(false)
    expect(names.some((n) => n.startsWith('ANSSI'))).toBe(true)
  })

  it('removes the profile after a confirmation, with a null', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    mocks.update.mockResolvedValue({ data: { ...CA, compliance_profile: null } })
    renderField({ ca: { ...CA, compliance_profile: 'bsi' } })
    fireEvent.click(screen.getByText('cas.compliance.remove'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(3, { complianceProfile: null }))
    expect(mocks.showConfirm).toHaveBeenCalled()
  })

  it('does not remove the profile when the confirmation is refused', async () => {
    mocks.showConfirm.mockResolvedValue(false)
    renderField({ ca: { ...CA, compliance_profile: 'bsi' } })
    fireEvent.click(screen.getByText('cas.compliance.remove'))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalled())
    expect(mocks.update).not.toHaveBeenCalled()
  })

  it('offers no action without write:cas, or on a revoked CA', () => {
    const { unmount } = renderField({ canWrite: false, ca: { ...CA, compliance_profile: 'bsi' } })
    expect(screen.queryByText('cas.compliance.change')).toBeNull()
    expect(screen.queryByText('cas.compliance.remove')).toBeNull()
    unmount()
    renderField({ ca: { ...CA, revoked: true } })
    expect(screen.queryByText('cas.compliance.attach')).toBeNull()
  })

  it('offers removal but no attach without admin:system', () => {
    renderField({ ca: { ...CA, compliance_profile: 'bsi' }, canAttach: false })
    expect(screen.queryByText('cas.compliance.change')).not.toBeInTheDocument()
    expect(screen.getByText('cas.compliance.remove')).toBeInTheDocument()
  })
})
