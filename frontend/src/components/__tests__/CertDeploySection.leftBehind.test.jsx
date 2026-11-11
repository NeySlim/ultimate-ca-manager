/**
 * CertDeploySection: a binding a renewal left on the previous certificate says so,
 * and offers the reattachment only when the renewed certificate can take it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getBindings: vi.fn(),
  getTargets: vi.fn(),
  reattachBinding: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({ hasPermission: () => true }),
}))

vi.mock('../../services', () => ({ deployService: mocks }))

vi.mock('../Modal', () => ({
  Modal: ({ open, children }) => open ? <div role="dialog">{children}</div> : null,
}))

import { CertDeploySection } from '../deploy/CertDeploySection'

const certificate = { id: 42, has_private_key: true }

function binding(attention) {
  return {
    id: 5, target_id: 7, target_name: 'web01', enabled: true,
    cert_path: '/etc/ssl/app.pem', key_path: '/etc/ssl/app.key',
    last_delivery: null, needs_attention: attention,
  }
}

describe('CertDeploySection left-behind state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getTargets.mockResolvedValue({ data: [] })
    mocks.reattachBinding.mockResolvedValue({ data: {} })
  })

  it('explains what to do when the renewed certificate has no key', async () => {
    mocks.getBindings.mockResolvedValue({ data: [binding({
      reason: 'successor_without_key', successor_id: 43, successor_refid: 'abc',
      successor_has_key: false, can_reattach: false,
    })] })
    render(<CertDeploySection certificate={certificate} />)
    expect(await screen.findByText('deploy.leftBehind')).toBeInTheDocument()
    expect(screen.getByText('deploy.leftBehindNoKey')).toBeInTheDocument()
    expect(screen.queryByText('deploy.reattach')).not.toBeInTheDocument()
  })

  it('reattaches to the renewed certificate when it can', async () => {
    mocks.getBindings.mockResolvedValue({ data: [binding({
      reason: 'successor_without_key', successor_id: 43, successor_refid: 'abc',
      successor_has_key: true, can_reattach: true,
    })] })
    render(<CertDeploySection certificate={certificate} />)
    fireEvent.click(await screen.findByText('deploy.reattach'))
    await waitFor(() => expect(mocks.reattachBinding).toHaveBeenCalledWith(5))
    await waitFor(() => expect(mocks.getBindings).toHaveBeenCalledTimes(2))
  })

  it('stays silent for a binding that followed', async () => {
    mocks.getBindings.mockResolvedValue({ data: [binding(null)] })
    render(<CertDeploySection certificate={certificate} />)
    expect(await screen.findByText('web01')).toBeInTheDocument()
    expect(screen.queryByText('deploy.leftBehind')).not.toBeInTheDocument()
  })
})
