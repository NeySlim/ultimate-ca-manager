import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))
const api = vi.hoisted(() => ({ getSystemStatus: vi.fn(), can: vi.fn() }))
vi.mock('../../../services', () => ({ dashboardService: { getSystemStatus: api.getSystemStatus } }))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: api.can }) }))

import { KeyEncryptionBanner } from '../KeyEncryptionBanner'

const show = () => render(<MemoryRouter><KeyEncryptionBanner /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  api.can.mockReturnValue(true)
})

describe('KeyEncryptionBanner', () => {
  it('warns while no master key is loaded and links to Settings > Security', async () => {
    api.getSystemStatus.mockResolvedValue({ data: { key_encryption: { status: 'warning' } } })
    show()
    expect(await screen.findByText('dashboard.keyEncryptionOffTitle')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('dashboard.keyEncryptionOffDesc')
    expect(screen.getByText('settings.tabs.security')).toBeTruthy()
  })

  it('omits the settings button without admin:system', async () => {
    api.can.mockReturnValue(false)
    api.getSystemStatus.mockResolvedValue({ data: { key_encryption: { status: 'warning' } } })
    show()
    await screen.findByRole('alert')
    expect(screen.queryByText('settings.tabs.security')).toBeNull()
  })

  it('stays silent once the key is loaded', async () => {
    api.getSystemStatus.mockResolvedValue({ data: { key_encryption: { status: 'online' } } })
    show()
    await vi.waitFor(() => expect(api.getSystemStatus).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('stays silent when the status call fails', async () => {
    api.getSystemStatus.mockRejectedValue(new Error('x'))
    show()
    await vi.waitFor(() => expect(api.getSystemStatus).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
