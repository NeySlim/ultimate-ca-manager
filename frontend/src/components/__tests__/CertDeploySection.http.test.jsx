/**
 * Attaching a certificate to an HTTP API target (#428): no paths, no reload
 * command, the chain options stay because the template may send the chain.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getChainVariants: vi.fn(),
  getBindings: vi.fn(),
  getTargets: vi.fn(),
  createBinding: vi.fn(),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))
vi.mock('../../hooks', () => ({ usePermission: () => ({ hasPermission: () => true }) }))
vi.mock('../../services', () => ({
  casService: { getChainVariants: mocks.getChainVariants },
  deployService: mocks,
}))
vi.mock('../Modal', () => ({
  Modal: ({ open, children }) => (open ? <div role="dialog">{children}</div> : null),
}))

import { CertDeploySection } from '../deploy/CertDeploySection'

const TARGETS = [
  { id: 1, kind: 'ssh', name: 'web', enabled: true, username: 'deploy', host: 'web.example.net' },
  { id: 2, kind: 'http', name: 'fw', enabled: true, http_method: 'POST', url: 'https://fw.example.net/api', allow_private_key: true },
]

describe('CertDeploySection with an HTTP target', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getChainVariants.mockResolvedValue({ data: [] })
    mocks.getBindings.mockResolvedValue({ data: [] })
    mocks.getTargets.mockResolvedValue({ data: TARGETS })
    mocks.createBinding.mockResolvedValue({ data: {} })
  })

  it('hides the paths and the reload command and attaches without them', async () => {
    render(<CertDeploySection certificate={{ id: 42, descr: 'app', has_private_key: true }} />)
    fireEvent.click(await screen.findByText('deploy.attachTarget'))
    const select = await screen.findByRole('combobox')
    expect(screen.getByText('deploy.certPath')).toBeInTheDocument()

    fireEvent.change(select, { target: { value: '2' } })
    expect(screen.queryByText('deploy.certPath')).not.toBeInTheDocument()
    expect(screen.queryByText('deploy.reloadCommand')).not.toBeInTheDocument()
    expect(screen.getByText(/deploy.httpBindingHint/)).toBeInTheDocument()
    expect(screen.getByText(/deploy.httpBindingKeyHint/)).toBeInTheDocument()
    expect(screen.getByText('export.includeRoot')).toBeInTheDocument()

    fireEvent.click(screen.getByText('deploy.attach'))
    await vi.waitFor(() => expect(mocks.createBinding).toHaveBeenCalled())
    expect(mocks.createBinding.mock.calls[0][0]).toEqual({
      include_root: false, certificate_id: 42, target_id: 2,
    })
  })

  it('shows an HTTP binding without paths', async () => {
    mocks.getBindings.mockResolvedValue({ data: [{
      id: 5, target_id: 2, target_name: 'fw', target_kind: 'http', target_enabled: true, enabled: true,
      cert_path: null, key_path: null, fullchain_path: null, last_delivery: { status: 'delivered' },
    }] })
    render(<CertDeploySection certificate={{ id: 42, descr: 'app', has_private_key: true }} />)
    expect(await screen.findByText('deploy.httpBinding')).toBeInTheDocument()
  })
})
