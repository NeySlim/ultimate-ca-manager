/**
 * The chain a CA or certificate presents when a cross-certificate offers another path (#400):
 * pinned on a deploy binding (export: pages/certificates/dialogs).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getChainVariants: vi.fn(),
  getById: vi.fn(),
  getBindings: vi.fn(),
  getTargets: vi.fn(),
  createBinding: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, vars) => (vars?.issuer ? `${key}:${vars.issuer}` : key),
  }),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))
vi.mock('../../hooks', () => ({ usePermission: () => ({ hasPermission: () => true }) }))
vi.mock('../../services', () => ({
  casService: { getChainVariants: mocks.getChainVariants },
  certificatesService: { getById: mocks.getById },
  deployService: mocks,
}))
vi.mock('../../lib/exportPassword', () => ({
  exportPasswordPolicy: () => ({ min_length: 1, max_length: 64 }),
  isExportPasswordValid: () => true,
  loadExportPasswordPolicy: () => Promise.resolve({ min_length: 1, max_length: 64 }),
}))
import { CertDeploySection } from '../deploy/CertDeploySection'

const VARIANTS = [
  { id: 'primary', servable: true, served: false, ca_name: 'Root B', issuer: null },
  { id: 'cross:4', servable: true, served: true, ca_name: 'Root B', issuer: 'CN=Root A,O=Acme' },
  { id: 'cross:5', servable: false, served: false, ca_name: 'Root B', issuer: 'CN=Old Root' },
]

describe('CertDeploySection chain variant', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getBindings.mockResolvedValue({ data: [] })
    mocks.getTargets.mockResolvedValue({ data: [{ id: 7, name: 'web01', host: 'h', username: 'u', enabled: true }] })
    mocks.createBinding.mockResolvedValue({ data: { id: 1 } })
    mocks.getById.mockResolvedValue({ data: { chain_status: { variants: VARIANTS } } })
  })

  async function openForm() {
    render(<CertDeploySection certificate={{ id: 42, has_private_key: true }} />)
    fireEvent.click(await screen.findByText('deploy.attachTarget'))
    await screen.findByRole('dialog')
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: '7' } })
    fireEvent.change(screen.getByPlaceholderText('/etc/ssl/certs/app-fullchain.pem'), {
      target: { value: '/etc/ssl/certs/app-fullchain.pem' },
    })
  }

  it('pins a servable variant on the binding and refuses an unservable one', async () => {
    await openForm()
    const select = await screen.findByLabelText('chainVariant.label')
    expect(select.querySelector('option[value="cross:5"]')).toBeDisabled()
    expect(select.querySelector('option[value="cross:4"]')).not.toBeDisabled()
    fireEvent.change(select, { target: { value: 'cross:4' } })
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createBinding).toHaveBeenCalledWith(
      expect.objectContaining({ chain_variant: 'cross:4', certificate_id: 42 })))
  })

  it('sends no variant while it stays on auto', async () => {
    await openForm()
    await screen.findByLabelText('chainVariant.label')
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.createBinding).toHaveBeenCalled())
    expect(mocks.createBinding.mock.calls[0][0]).not.toHaveProperty('chain_variant')
  })
})
