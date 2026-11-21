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
  Modal: ({ open, title, children }) => open ? <div role="dialog" aria-label={title}>{children}</div> : null,
  HelpCard: ({ children }) => <aside>{children}</aside>,
}))

import IntuneAppForm from '../IntuneAppForm'

const APP = { id: 7, name: 'Corp Intune', tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7', client_secret_set: true }

const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('IntuneAppForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.createIntuneApp.mockResolvedValue({ data: { id: 9 } })
    mocks.updateIntuneApp.mockResolvedValue({ data: { id: 7 } })
    mocks.testIntuneApp.mockResolvedValue({ data: { message: 'ok' } })
  })

  it('creates a registration from the form', async () => {
    const onSaved = vi.fn()
    render(<IntuneAppForm app={null} onClose={vi.fn()} onSaved={onSaved} />)
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
    expect(onSaved).toHaveBeenCalled()
  })

  it('a blank secret on edit is not sent, and the test uses the saved app', async () => {
    render(<IntuneAppForm app={APP} onClose={vi.fn()} onSaved={vi.fn()} />)
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
    render(<IntuneAppForm app={APP} onClose={vi.fn()} onSaved={vi.fn()} />)
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
})
