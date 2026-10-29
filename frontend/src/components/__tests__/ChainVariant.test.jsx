/**
 * The chain a CA or certificate presents when a cross-certificate offers another path (#400):
 * chosen on export, pinned on a deploy binding.
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
vi.mock('../Modal', () => ({
  Modal: ({ open, children }) => (open ? <div role="dialog">{children}</div> : null),
}))

import { ExportModal } from '../ExportModal'
import { CertDeploySection } from '../deploy/CertDeploySection'

const VARIANTS = [
  { id: 'primary', servable: true, served: false, ca_name: 'Root B', issuer: null },
  { id: 'cross:4', servable: true, served: true, ca_name: 'Root B', issuer: 'CN=Root A,O=Acme' },
  { id: 'cross:5', servable: false, served: false, ca_name: 'Root B', issuer: 'CN=Old Root' },
]

describe('ExportModal chain variant', () => {
  beforeEach(() => vi.clearAllMocks())

  const renderExport = (onExport, extra = {}) => render(
    <ExportModal open onClose={() => {}} entityType="ca" entityName="Root B" onExport={onExport}
                 chainVariantsFor={{ type: 'ca', id: 9 }} {...extra} />)

  it('offers the variants of a CA and sends the chosen one', async () => {
    mocks.getChainVariants.mockResolvedValue({ data: VARIANTS })
    const onExport = vi.fn().mockResolvedValue(undefined)
    renderExport(onExport)
    const select = await screen.findByRole('combobox')
    expect(mocks.getChainVariants).toHaveBeenCalledWith(9)
    fireEvent.change(select, { target: { value: 'cross:4' } })
    fireEvent.submit(select.closest('form'))
    await waitFor(() => expect(onExport).toHaveBeenCalled())
    expect(onExport.mock.calls[0][1].chainVariant).toBe('cross:4')
  })

  it('sends no variant by default', async () => {
    mocks.getChainVariants.mockResolvedValue({ data: VARIANTS })
    const onExport = vi.fn().mockResolvedValue(undefined)
    renderExport(onExport)
    const select = await screen.findByRole('combobox')
    fireEvent.submit(select.closest('form'))
    await waitFor(() => expect(onExport).toHaveBeenCalled())
    expect(onExport.mock.calls[0][1].chainVariant).toBeUndefined()
  })

  it('shows no selector when the chain has no alternative', async () => {
    mocks.getChainVariants.mockResolvedValue({ data: [VARIANTS[0]] })
    renderExport(vi.fn())
    await waitFor(() => expect(mocks.getChainVariants).toHaveBeenCalled())
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('reads the variants of a certificate from its chain status', async () => {
    mocks.getById.mockResolvedValue({ data: { chain_status: { variants: VARIANTS } } })
    renderExport(vi.fn(), { entityType: 'certificate', chainVariantsFor: { type: 'certificate', id: 3 } })
    expect(await screen.findByRole('combobox')).toBeInTheDocument()
    expect(mocks.getById).toHaveBeenCalledWith(3)
  })

  it('hides the selector without the chain', async () => {
    mocks.getChainVariants.mockResolvedValue({ data: VARIANTS })
    renderExport(vi.fn())
    await screen.findByRole('combobox')
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    expect(screen.queryByRole('combobox')).toBeNull()
  })
})

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
