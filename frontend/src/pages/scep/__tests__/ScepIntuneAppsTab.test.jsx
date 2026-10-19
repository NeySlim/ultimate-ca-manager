import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getIntuneApps: vi.fn(),
  createIntuneApp: vi.fn(),
  updateIntuneApp: vi.fn(),
  deleteIntuneApp: vi.fn(),
  testIntuneApp: vi.fn(),
  t: vi.fn((key, vars) => (vars?.name ? `${key}:${vars.name}` : vars?.count != null ? `${key}:${vars.count}` : key)),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showConfirm: vi.fn(),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError, showConfirm: mocks.showConfirm }),
}))
vi.mock('../../../services', () => ({ scepService: mocks }))
vi.mock('../../../components', () => ({
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, hasExistingValue: _e, error: _err, ...props }) => <label>{label}<input {...props} /></label>,
  Card: ({ children }) => <section>{children}</section>,
  Badge: ({ children }) => <span>{children}</span>,
  Modal: ({ open, title, children }) => open ? <div role="dialog" aria-label={title}>{children}</div> : null,
  EmptyState: ({ title }) => <p>{title}</p>,
  HelpCard: ({ children }) => <aside>{children}</aside>,
}))

import ScepIntuneAppsTab from '../ScepIntuneAppsTab'

const APPS = [
  { id: 7, name: 'Corp Intune', tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7',
    client_secret_set: true, profile_count: 2, profile_names: ['Windows', 'iOS'], last_test_at: null },
  { id: 8, name: 'Lab Intune', tenant_id: 'lab.onmicrosoft.com', client_id: 'client-8',
    client_secret_set: true, profile_count: 0, profile_names: [], last_test_at: null },
]

const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('ScepIntuneAppsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getIntuneApps.mockResolvedValue({ data: APPS })
    mocks.createIntuneApp.mockResolvedValue({ data: { id: 9 } })
    mocks.updateIntuneApp.mockResolvedValue({ data: { id: 7 } })
    mocks.showConfirm.mockResolvedValue(true)
  })

  it('lists the registrations with the profiles that use them', async () => {
    render(<ScepIntuneAppsTab canWrite />)
    expect(await screen.findByText('Corp Intune')).toBeInTheDocument()
    expect(screen.getByText('scep.intuneAppUsedBy:2')).toBeInTheDocument()
    expect(screen.getByText('scep.intuneAppNotUsed')).toBeInTheDocument()
    expect(screen.getByText('Windows, iOS')).toBeInTheDocument()
  })

  it('creates a registration from the form', async () => {
    render(<ScepIntuneAppsTab canWrite />)
    await screen.findByText('Corp Intune')
    fireEvent.click(screen.getByText('scep.newIntuneApp'))
    await screen.findByRole('dialog')
    fill('common.name', 'New app')
    fill('scep.intuneTenantId', 'new.onmicrosoft.com')
    fill('scep.intuneClientId', 'client-new')
    fill('scep.intuneClientSecret', 's3cret')
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createIntuneApp).toHaveBeenCalledWith({
      name: 'New app', tenant_id: 'new.onmicrosoft.com', client_id: 'client-new', client_secret: 's3cret',
    }))
    expect(mocks.showSuccess).toHaveBeenCalledWith('scep.intuneAppCreated')
  })

  it('a blank secret on edit is not sent, and the test uses the saved app', async () => {
    render(<ScepIntuneAppsTab canWrite />)
    await screen.findByText('Corp Intune')
    fireEvent.click(screen.getAllByTitle('common.edit')[0])
    await screen.findByRole('dialog')
    expect(screen.getByLabelText('scep.intuneClientId')).toHaveValue('client-7')
    fireEvent.click(screen.getByText('scep.intuneTestConnection'))
    await waitFor(() => expect(mocks.testIntuneApp).toHaveBeenCalledWith({
      app_id: 7, tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7', client_secret: '',
    }))
    fill('common.name', 'Corp Intune 2')
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.updateIntuneApp).toHaveBeenCalledWith(7, {
      name: 'Corp Intune 2', tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7',
    }))
  })

  it('moving the saved secret to another client asks for it again', async () => {
    render(<ScepIntuneAppsTab canWrite />)
    await screen.findByText('Corp Intune')
    fireEvent.click(screen.getAllByTitle('common.edit')[0])
    await screen.findByRole('dialog')
    fill('scep.intuneClientId', 'client-7b')
    expect(screen.getByLabelText('scep.intuneClientSecret').required).toBe(true)
    fireEvent.submit(document.querySelector('form'))
    expect(mocks.showError).toHaveBeenCalledWith('common.secretRequiredForTarget')
    expect(mocks.updateIntuneApp).not.toHaveBeenCalled()
    fill('scep.intuneClientSecret', 'typed')
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.updateIntuneApp).toHaveBeenCalledWith(7, {
      name: 'Corp Intune', tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7b', client_secret: 'typed',
    }))
  })

  it('shows the server reason when a registration in use cannot be deleted', async () => {
    mocks.deleteIntuneApp.mockRejectedValue(new Error('Cannot delete: used by 2 SCEP profile(s): Windows, iOS'))
    render(<ScepIntuneAppsTab canWrite />)
    await screen.findByText('Corp Intune')
    fireEvent.click(screen.getAllByTitle('common.delete')[0])
    await waitFor(() => expect(mocks.deleteIntuneApp).toHaveBeenCalledWith(7))
    expect(mocks.showError).toHaveBeenCalledWith('Cannot delete: used by 2 SCEP profile(s): Windows, iOS')
    expect(mocks.showConfirm).toHaveBeenCalledWith('scep.intuneAppDeleteConfirm:Corp Intune', expect.anything())
  })
})
