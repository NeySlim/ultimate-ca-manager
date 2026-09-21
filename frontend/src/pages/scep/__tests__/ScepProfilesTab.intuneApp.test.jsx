import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getIntuneApps: vi.fn(),
  createProfile: vi.fn(),
  updateProfile: vi.fn(),
  testIntuneApp: vi.fn(),
  t: vi.fn((key, vars) => (vars?.name ? `${key}:${vars.name}` : key)),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showConfirm: vi.fn(),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError, showConfirm: mocks.showConfirm }),
}))
vi.mock('../../../hooks/useClipboard', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))
vi.mock('../../../services', () => ({ scepService: mocks }))
vi.mock('../../../components', () => ({
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _h, noAutofill: _n, ...props }) => <label>{label}<input {...props} /></label>,
  Select: ({ label, value, onChange, options = [], placeholder }) => (
    <label>{label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{placeholder}</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  ),
  Card: ({ children }) => <section>{children}</section>,
  Badge: ({ children }) => <span>{children}</span>,
  Modal: ({ open, children }) => open ? <div role="dialog">{children}</div> : null,
  EmptyState: ({ title }) => <p>{title}</p>,
  HelpCard: ({ children }) => <aside>{children}</aside>,
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label, checked, onChange, disabled }) => (
    <label>{label}<input type="checkbox" checked={checked} disabled={disabled}
                         onChange={(e) => onChange(e.target.checked)} /></label>
  ),
}))

import ScepProfilesTab from '../ScepProfilesTab'

const CAS = [{ id: 3, refid: 'ca-3', descr: 'Issuing CA' }]
const APPS = [
  { id: 7, name: 'Corp Intune', tenant_id: 'corp.onmicrosoft.com' },
  { id: 8, name: 'Lab Intune', tenant_id: 'lab.onmicrosoft.com' },
]

describe('ScepProfilesTab picks an Intune app registration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getIntuneApps.mockResolvedValue({ data: APPS })
    mocks.createProfile.mockResolvedValue({ data: { id: 1 } })
    mocks.testIntuneApp.mockResolvedValue({ data: { message: 'ok' } })
  })

  it('offers the registrations, no test button, and submits the chosen id, never the credentials', async () => {
    const onManage = vi.fn()
    render(<ScepProfilesTab profiles={[]} cas={CAS} templates={[]} canWrite
                            onChanged={vi.fn()} onManageIntuneApps={onManage} />)
    fireEvent.click(screen.getByText('scep.newProfile'))
    await screen.findByRole('dialog')
    await waitFor(() => expect(mocks.getIntuneApps).toHaveBeenCalled())

    fireEvent.change(screen.getByLabelText('common.name'), { target: { value: 'Windows devices' } })
    fireEvent.change(screen.getByLabelText('common.certificateAuthority'), { target: { value: '3' } })
    fireEvent.click(screen.getByLabelText('scep.intuneEnabled'))
    const picker = await screen.findByLabelText('scep.intuneApp')
    expect(screen.getByText('Corp Intune (corp.onmicrosoft.com)')).toBeInTheDocument()
    expect(screen.queryByLabelText('scep.intuneTenantId')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('scep.intuneClientSecret')).not.toBeInTheDocument()

    fireEvent.change(picker, { target: { value: '7' } })
    // The connection test lives on the registrations tab, not here
    expect(screen.queryByText('scep.intuneTestConnection')).not.toBeInTheDocument()
    expect(mocks.testIntuneApp).not.toHaveBeenCalled()

    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createProfile).toHaveBeenCalled())
    const payload = mocks.createProfile.mock.calls[0][0]
    expect(payload).toMatchObject({ intune_enabled: true, intune_app_id: 7, auto_approve: true })
    expect(payload).not.toHaveProperty('intune_tenant_id')
    expect(payload).not.toHaveProperty('intune_client_secret')
  })

  it('a profile with Intune off sends no registration', async () => {
    render(<ScepProfilesTab profiles={[]} cas={CAS} templates={[]} canWrite onChanged={vi.fn()} />)
    fireEvent.click(screen.getByText('scep.newProfile'))
    await screen.findByRole('dialog')
    fireEvent.change(screen.getByLabelText('common.name'), { target: { value: 'Static' } })
    fireEvent.change(screen.getByLabelText('common.certificateAuthority'), { target: { value: '3' } })
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createProfile).toHaveBeenCalled())
    expect(mocks.createProfile.mock.calls[0][0]).toMatchObject({ intune_enabled: false, intune_app_id: null })
  })

  it('the manage link closes the form and opens the registrations tab', async () => {
    const onManage = vi.fn()
    render(<ScepProfilesTab profiles={[]} cas={CAS} templates={[]} canWrite
                            onChanged={vi.fn()} onManageIntuneApps={onManage} />)
    fireEvent.click(screen.getByText('scep.newProfile'))
    await screen.findByRole('dialog')
    fireEvent.click(screen.getByLabelText('scep.intuneEnabled'))
    fireEvent.click(await screen.findByText('scep.manageIntuneApps'))
    expect(onManage).toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
