/** The update screen says how old the check it shows is, and flags a failed one. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, values) => (values ? `${key}:${Object.values(values).join('|')}` : key) }),
}))
vi.mock('../../services', () => ({ apiClient: { get: mocks.get, post: vi.fn() } }))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))
vi.mock('../../hooks', () => vi.importActual('../../hooks/useServiceReconnect'))
vi.mock('../index.js', async () => {
  const { ServiceReconnectOverlay } = await vi.importActual('../ServiceReconnectOverlay')
  return {
    Card: ({ children }) => <div>{children}</div>,
    Button: ({ children, ...props }) => <button {...props}>{children}</button>,
    Badge: ({ children }) => <span>{children}</span>,
    LoadingSpinner: () => null,
    ServiceReconnectOverlay,
  }
})

import { UpdateChecker } from '../UpdateChecker'

describe('update check age', () => {
  beforeEach(() => mocks.get.mockReset())

  it('shows when the served answer was checked', async () => {
    const checkedAt = new Date(Date.now() - 3 * 3600000).toISOString()
    mocks.get.mockResolvedValue({ data: { update_available: false, current_version: '3.1', checked_at: checkedAt } })
    render(<UpdateChecker />)
    expect(await screen.findByText('settings.updates.lastChecked')).toBeInTheDocument()
    expect(screen.getByText(/time\.compact\.hoursAgo:3/)).toBeInTheDocument()
  })

  it('says nothing about an age the server did not give', async () => {
    mocks.get.mockResolvedValue({ data: { update_available: false, current_version: '3.1' } })
    render(<UpdateChecker />)
    expect(await screen.findByText('settings.upToDateTitle')).toBeInTheDocument()
    expect(screen.queryByText('settings.updates.lastChecked')).toBeNull()
  })

  it('flags a failed check with its age', async () => {
    mocks.get.mockResolvedValue({ data: { update_available: false, current_version: '3.1', error: 'offline',
      checked_at: new Date(Date.now() - 60000).toISOString() } })
    render(<UpdateChecker />)
    expect(await screen.findByText('settings.checkFailed')).toBeInTheDocument()
    expect(screen.getByText('settings.updates.lastChecked')).toBeInTheDocument()
  })
})
