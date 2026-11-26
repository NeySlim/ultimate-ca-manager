import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getProviders: vi.fn(), listMatchingHsmKeys: vi.fn(), attachHsmKey: vi.fn(),
  showSuccess: vi.fn(), showError: vi.fn(),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))
vi.mock('../../../services', () => ({
  hsmService: { getProviders: mocks.getProviders },
  casService: { listMatchingHsmKeys: mocks.listMatchingHsmKeys, attachHsmKey: mocks.attachHsmKey },
}))

import { AttachHsmKeyModal } from '../AttachHsmKeyModal'

const t = (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key)
const CA = { id: 12, descr: 'Imported Root' }
const KEYS = [
  { key_identifier: 'a1', label: 'root-key', algorithm: 'EC-P384', held_by: null, refusal: null },
  { key_identifier: 'b2', label: 'twin', algorithm: 'EC-P384', held_by: "X.509 CA 'Other'", refusal: null },
]

const openOn = async () => {
  mocks.getProviders.mockResolvedValue({ data: [{ id: 3, name: 'Token', provider_type: 'pkcs11' }] })
  mocks.listMatchingHsmKeys.mockResolvedValue({ data: { keys: KEYS } })
  const onSuccess = vi.fn()
  const onClose = vi.fn()
  render(<AttachHsmKeyModal open ca={CA} onClose={onClose} onSuccess={onSuccess} t={t} />)
  const select = await screen.findByLabelText('cas.attachHsmKey.provider')
  fireEvent.change(select, { target: { value: '3' } })
  await screen.findByText('root-key')
  return { onSuccess, onClose }
}

describe('AttachHsmKeyModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the matching keys of the chosen provider and attaches the confirmed one', async () => {
    const { onSuccess, onClose } = await openOn()
    expect(mocks.listMatchingHsmKeys).toHaveBeenCalledWith(12, '3')
    expect(screen.getByText('cas.attachHsmKey.keyId: a1 · EC-P384')).toBeInTheDocument()
    const radios = screen.getAllByRole('radio')
    expect(radios[1]).toBeDisabled()
    expect(screen.getByText(/cas.attachHsmKey.heldBy/)).toHaveTextContent("X.509 CA 'Other'")
    fireEvent.click(radios[0])
    fireEvent.click(screen.getByText('common.continue'))
    expect(screen.getByText(/cas.attachHsmKey.confirmText/)).toHaveTextContent('"id":"a1"')
    expect(mocks.attachHsmKey).not.toHaveBeenCalled()
    mocks.attachHsmKey.mockResolvedValue({ data: { id: 12, uses_hsm: true } })
    fireEvent.click(screen.getByText('cas.attachHsmKey.confirm'))
    await waitFor(() => expect(mocks.attachHsmKey).toHaveBeenCalledWith(12, 3, 'a1'))
    expect(onSuccess).toHaveBeenCalledWith({ id: 12, uses_hsm: true })
    expect(onClose).toHaveBeenCalled()
  })

  it('shows the refusal of the server and stays open', async () => {
    await openOn()
    fireEvent.click(screen.getAllByRole('radio')[0])
    fireEvent.click(screen.getByText('common.continue'))
    mocks.attachHsmKey.mockRejectedValue(new Error('HSM key does not match the CA certificate'))
    fireEvent.click(screen.getByText('cas.attachHsmKey.confirm'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('HSM key does not match the CA certificate'))
    expect(screen.getByTestId('attach-hsm-key-dialog')).toBeInTheDocument()
  })

  it('says when the provider cannot be read', async () => {
    mocks.getProviders.mockResolvedValue({ data: [{ id: 3, name: 'Token', provider_type: 'pkcs11' }] })
    mocks.listMatchingHsmKeys.mockRejectedValue(new Error('The HSM provider could not be reached'))
    render(<AttachHsmKeyModal open ca={CA} onClose={vi.fn()} t={t} />)
    fireEvent.change(await screen.findByLabelText('cas.attachHsmKey.provider'), { target: { value: '3' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('The HSM provider could not be reached')
    expect(screen.getByText('common.continue')).toBeDisabled()
  })
})
