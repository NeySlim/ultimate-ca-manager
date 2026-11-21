import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getCRLBindings: vi.fn(),
  getTargets: vi.fn(),
  t: vi.fn(key => key),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showConfirm: vi.fn(),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError, showConfirm: mocks.showConfirm }),
}))
vi.mock('../../hooks', () => ({ usePermission: () => ({ hasPermission: () => true }) }))
vi.mock('../../services', () => ({ deployService: mocks }))
vi.mock('../index', () => ({
  Badge: ({ children }) => <span>{children}</span>,
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  CompactSection: ({ children }) => <section>{children}</section>,
}))

import { CRLDeploySection } from '../CRLDeploySection'

const binding = (id, target_name) => ({
  id, target_name, crl_path: `/srv/${target_name}.crl`, format: 'pem', include_parent_crls: false, enabled: true,
})

describe('CRLDeploySection keeps only the newest load', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getTargets.mockResolvedValue({ data: [] })
  })

  it('a slow answer for the previous CA does not overwrite the current one', async () => {
    let resolveSlow
    mocks.getCRLBindings.mockImplementationOnce(() => new Promise(resolve => { resolveSlow = resolve }))
    const { rerender } = render(<CRLDeploySection ca={{ id: 1, descr: 'Old CA' }} hasCRL />)
    await waitFor(() => expect(mocks.getCRLBindings).toHaveBeenCalledTimes(1))

    mocks.getCRLBindings.mockResolvedValueOnce({ data: [binding(2, 'new-target')] })
    rerender(<CRLDeploySection ca={{ id: 2, descr: 'New CA' }} hasCRL />)
    await screen.findByText('new-target')

    resolveSlow({ data: [binding(1, 'old-target')] })
    await waitFor(() => expect(mocks.getCRLBindings).toHaveBeenCalledTimes(2))
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(screen.queryByText('old-target')).not.toBeInTheDocument()
    expect(screen.getByText('new-target')).toBeInTheDocument()
  })
})
