import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getCRLBindings: vi.fn(),
  getTargets: vi.fn(),
  createCRLBinding: vi.fn(),
  t: vi.fn(key => key),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showConfirm: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
    showConfirm: mocks.showConfirm,
  }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({ hasPermission: () => true }),
}))

vi.mock('../../services', () => ({ deployService: mocks }))

vi.mock('../index', () => ({
  Badge: ({ children }) => <span>{children}</span>,
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  CompactSection: ({ children }) => <section>{children}</section>,
}))

import { CRLDeploySection } from '../CRLDeploySection'

describe('CRLDeploySection format options', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getCRLBindings.mockResolvedValue({ data: [] })
    mocks.getTargets.mockResolvedValue({
      data: [{ id: 7, name: 'web01', host: '192.0.2.10', enabled: true }],
    })
    mocks.createCRLBinding.mockResolvedValue({ data: { id: 1 } })
  })

  it('hides parent CRLs for DER and submits include_parent_crls=false', async () => {
    render(<CRLDeploySection ca={{ id: 42, descr: 'Client CA' }} hasCRL />)
    fireEvent.click(await screen.findByText('crlDeploy.attach'))
    await screen.findByRole('dialog')

    const path = screen.getByPlaceholderText('/root/certs/CRL.crl')
    expect(path).toHaveValue('')
    expect(path).toBeRequired()

    const selects = screen.getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: '7' } })
    expect(screen.getByText('crlDeploy.includeParents')).toBeInTheDocument()

    fireEvent.change(selects[1], { target: { value: 'der' } })
    expect(screen.queryByText('crlDeploy.includeParents')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'crlDeploy.includeParents' })).not.toBeInTheDocument()

    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createCRLBinding).toHaveBeenCalledWith(
      expect.objectContaining({ format: 'der', include_parent_crls: false })))
  })

  it('localizes delivery state and shows the last failure', async () => {
    mocks.getCRLBindings.mockResolvedValue({ data: [{
      id: 12, target_id: 7, target_name: 'web01', crl_path: '/crl.pem',
      format: 'pem', include_parent_crls: false, enabled: true,
      last_delivery: {
        status: 'failed', last_error: 'Reload command exited 1',
        delivered_at: '2026-09-20T10:00:00Z',
      },
    }] })
    render(<CRLDeploySection ca={{ id: 42, descr: 'Client CA' }} hasCRL />)

    expect(await screen.findByText('deploy.status.failed')).toBeInTheDocument()
    expect(screen.getByText('Reload command exited 1')).toBeInTheDocument()
    expect(mocks.t).toHaveBeenCalledWith('deploy.lastDeployed', expect.any(Object))
  })

  it('shows disabled instead of enabled when a binding has no delivery', async () => {
    mocks.getCRLBindings.mockResolvedValue({ data: [{
      id: 13, target_id: 7, target_name: 'web01', crl_path: '/crl.pem',
      format: 'pem', include_parent_crls: false, enabled: false,
      last_delivery: null,
    }] })
    render(<CRLDeploySection ca={{ id: 42, descr: 'Client CA' }} hasCRL />)
    expect(await screen.findByText('common.disabled')).toBeInTheDocument()
    expect(screen.queryByText('common.enabled')).not.toBeInTheDocument()
  })

  it('shows a pending retry countdown and its last error', async () => {
    mocks.getCRLBindings.mockResolvedValue({ data: [{
      id: 14, target_id: 7, target_name: 'web01', crl_path: '/crl.pem',
      format: 'pem', include_parent_crls: false, enabled: true,
      last_delivery: {
        status: 'pending', last_error: 'Destination directory does not exist',
        next_attempt_at: new Date(Date.now() + 65000).toISOString(),
      },
    }] })
    render(<CRLDeploySection ca={{ id: 42, descr: 'Client CA' }} hasCRL />)

    expect(await screen.findByText('deploy.status.pending')).toBeInTheDocument()
    expect(screen.getByText('Destination directory does not exist')).toBeInTheDocument()
    expect(mocks.t).toHaveBeenCalledWith('deploy.nextRetry', expect.objectContaining({
      date: expect.any(String), countdown: expect.stringMatching(/^1m 0[45]s$/),
    }))
  })

  it('offers an enabled switch while editing a CRL binding', async () => {
    mocks.getCRLBindings.mockResolvedValue({ data: [{
      id: 15, target_id: 7, target_name: 'web01', target_host: 'web01.test',
      crl_path: '/crl.pem', format: 'pem', include_parent_crls: false,
      reload_command: '', enabled: true, last_delivery: null,
    }] })
    render(<CRLDeploySection ca={{ id: 42, descr: 'Client CA' }} hasCRL />)
    await screen.findByText('web01')
    fireEvent.click(screen.getByTitle('common.edit'))
    expect(screen.getByRole('checkbox', { name: 'common.enabled' })).toBeChecked()
  })
})
