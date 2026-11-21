import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getBindings: vi.fn(),
  getTargets: vi.fn(),
  createBinding: vi.fn(),
  updateBinding: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showConfirm: vi.fn(),
  }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({ hasPermission: () => true }),
}))

vi.mock('../../services', () => ({ deployService: mocks }))

import { CertDeploySection } from '../deploy/CertDeploySection'

const certificate = { id: 42, has_private_key: true }

async function openForm() {
  render(<CertDeploySection certificate={certificate} />)
  fireEvent.click(await screen.findByText('deploy.attachTarget'))
  await screen.findByRole('dialog')
  fireEvent.change(screen.getByRole('combobox'), { target: { value: '7' } })
  fireEvent.change(screen.getByPlaceholderText('/etc/ssl/certs/app-fullchain.pem'), {
    target: { value: '/etc/ssl/certs/app-fullchain.pem' },
  })
}

describe('CertDeploySection root CA option', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getBindings.mockResolvedValue({ data: [] })
    mocks.getTargets.mockResolvedValue({
      data: [{ id: 7, name: 'web01', host: '192.0.2.10', username: 'deploy', enabled: true }],
    })
    mocks.createBinding.mockResolvedValue({ data: { id: 1 } })
  })

  it('shows the option only for a fullchain and submits the safe default', async () => {
    render(<CertDeploySection certificate={certificate} />)
    fireEvent.click(await screen.findByText('deploy.attachTarget'))
    await screen.findByRole('dialog')
    expect(screen.queryByText('export.includeRoot')).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '7' } })
    fireEvent.change(screen.getByPlaceholderText('/etc/ssl/certs/app-fullchain.pem'), {
      target: { value: '/etc/ssl/certs/app-fullchain.pem' },
    })
    expect(screen.getByText('export.includeRoot')).toBeInTheDocument()

    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createBinding).toHaveBeenCalledWith(
      expect.objectContaining({ include_root: false })))
  })

  it('submits include_root=true when explicitly selected', async () => {
    await openForm()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.submit(document.querySelector('form'))

    await waitFor(() => expect(mocks.createBinding).toHaveBeenCalledWith({
      certificate_id: 42,
      target_id: 7,
      cert_path: undefined,
      key_path: undefined,
      fullchain_path: '/etc/ssl/certs/app-fullchain.pem',
      include_root: true,
      reload_command: '',
    }))
  })

  it('edits the reload command on the certificate binding', async () => {
    mocks.getBindings.mockResolvedValue({ data: [{
      id: 9,
      target_id: 7,
      target_name: 'web01',
      target_host: '192.0.2.10',
      cert_path: '/etc/ssl/certs/app.pem',
      key_path: null,
      fullchain_path: null,
      include_root: false,
      reload_command: 'old reload',
      enabled: true,
    }] })
    mocks.updateBinding.mockResolvedValue({ data: { id: 9 } })

    render(<CertDeploySection certificate={certificate} />)
    await screen.findByText('web01')
    fireEvent.click(document.querySelector('[data-deploy-binding-edit="certificate"]'))
    const command = screen.getByPlaceholderText(
      '/usr/sbin/nginx -t && /usr/sbin/nginx -s reload')
    fireEvent.change(command, { target: { value: 'new reload' } })
    fireEvent.submit(document.querySelector('form'))

    await waitFor(() => expect(mocks.updateBinding).toHaveBeenCalledWith(
      9, expect.objectContaining({ reload_command: 'new reload' })))
  })

  it('explicitly clears optional paths when editing a certificate binding', async () => {
    mocks.getBindings.mockResolvedValue({ data: [{
      id: 10,
      target_id: 7,
      target_name: 'web01',
      target_host: '192.0.2.10',
      cert_path: '/etc/ssl/certs/app.pem',
      key_path: '/etc/ssl/private/app.key',
      fullchain_path: '/etc/ssl/certs/app-fullchain.pem',
      include_root: true,
      reload_command: '',
      enabled: true,
    }] })
    mocks.updateBinding.mockResolvedValue({ data: { id: 10 } })

    render(<CertDeploySection certificate={certificate} />)
    await screen.findByText('web01')
    fireEvent.click(document.querySelector('[data-deploy-binding-edit="certificate"]'))
    fireEvent.change(screen.getByPlaceholderText('/etc/ssl/private/app.key'), {
      target: { value: '' },
    })
    fireEvent.change(screen.getByPlaceholderText('/etc/ssl/certs/app-fullchain.pem'), {
      target: { value: '' },
    })
    fireEvent.submit(document.querySelector('form'))

    await waitFor(() => expect(mocks.updateBinding).toHaveBeenCalledWith(10, {
      cert_path: '/etc/ssl/certs/app.pem',
      key_path: null,
      fullchain_path: null,
      include_root: false,
      reload_command: '',
    }))
  })
})
