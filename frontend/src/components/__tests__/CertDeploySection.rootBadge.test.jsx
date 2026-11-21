/**
 * CertDeploySection: a binding whose full chain file still carries the root
 * says so on its row, since nothing else in the interface shows the flag
 * (#357 follow-up).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getBindings: vi.fn(),
  getTargets: vi.fn(),
  createBinding: vi.fn(),
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

import { CertDeploySection } from '../deploy/CertDeploySection'

const certificate = { id: 42, has_private_key: true }

function binding(overrides) {
  return {
    id: 1, target_id: 7, target_name: 'web01', enabled: true,
    fullchain_path: '/etc/ssl/certs/app-fullchain.pem', include_root: false,
    last_delivery: null, ...overrides,
  }
}

describe('CertDeploySection root badge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getTargets.mockResolvedValue({ data: [] })
  })

  it('marks a binding whose full chain carries the root', async () => {
    mocks.getBindings.mockResolvedValue({ data: [binding({ include_root: true })] })
    render(<CertDeploySection certificate={certificate} />)
    expect(await screen.findByText('web01')).toBeInTheDocument()
    expect(screen.getByText('deploy.rootIncluded')).toBeInTheDocument()
  })

  it('stays silent for the default chain and for a binding without a full chain', async () => {
    mocks.getBindings.mockResolvedValue({ data: [
      binding({ id: 1, target_name: 'web01', include_root: false }),
      binding({ id: 2, target_name: 'web02', fullchain_path: null, include_root: true }),
    ] })
    render(<CertDeploySection certificate={certificate} />)
    expect(await screen.findByText('web02')).toBeInTheDocument()
    expect(screen.queryByText('deploy.rootIncluded')).not.toBeInTheDocument()
  })
})
