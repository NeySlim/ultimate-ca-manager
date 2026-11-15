/**
 * A later major version is an explicit, recommended upgrade shown from the
 * check's data, and the security-maintenance notice comes from the same data.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), showConfirm: vi.fn(), waitForRestart: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, values) => (values && typeof values === 'object' ? `${key}:${JSON.stringify(values)}` : key),
  }),
}))
vi.mock('react-markdown', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('../../services', () => ({ apiClient: { get: mocks.get, post: mocks.post } }))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: mocks.showConfirm }),
}))
vi.mock('../../hooks', () => ({
  UPDATE_MAX_WAIT_MS: 600000,
  useServiceReconnect: () => ({
    reconnecting: false, status: 'idle', attempt: 0, countdown: 0,
    waitForRestart: mocks.waitForRestart, cancel: vi.fn(),
  }),
}))
vi.mock('../index.js', () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  LoadingSpinner: () => null,
  ServiceReconnectOverlay: () => null,
}))

import { UpdateChecker } from '../UpdateChecker'

const UPGRADE = {
  version: '7.3', html_url: 'https://example.invalid/releases/v7.3', release_notes: '',
  download_url: 'http://x/ucm_7.3_all.deb',
}
const check = (over = {}) => ({
  data: {
    update_available: false, can_auto_update: true, current_version: '2.254.1',
    latest_version: '2.254.1', security_maintenance: true, major_upgrade: UPGRADE, ...over,
  },
})
const flush = () => act(async () => {})
const title = (version) => `settings.majorUpgradeTitle:${JSON.stringify({ version })}`

describe('upgrade to a later major version', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset().mockResolvedValue({})
    mocks.showConfirm.mockReset().mockResolvedValue(true)
    mocks.waitForRestart.mockReset()
  })

  it('shows the recommended section with the version of the data and installs on confirmation', async () => {
    mocks.get.mockResolvedValue(check())
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(title('7.3'))).toBeInTheDocument()
    expect(screen.getByText('settings.majorUpgradeRecommended')).toBeInTheDocument()
    expect(screen.getByText('settings.majorUpgradeDesc')).toBeInTheDocument()
    expect(screen.getByText('settings.majorUpgradeNotes').closest('a'))
      .toHaveAttribute('href', 'https://example.invalid/releases/v7.3')

    fireEvent.click(screen.getByText('settings.majorUpgradeInstall'))
    await flush()
    expect(mocks.showConfirm).toHaveBeenCalledTimes(1)
    expect(mocks.post).toHaveBeenCalledWith('/system/updates/install', { major_upgrade: true, version: '7.3' })
    expect(mocks.waitForRestart).toHaveBeenCalledWith(expect.objectContaining({ expectedVersion: '7.3' }))
  })

  it('installs nothing when the confirmation is declined', async () => {
    mocks.get.mockResolvedValue(check())
    mocks.showConfirm.mockResolvedValue(false)
    render(<UpdateChecker />)
    await flush()
    fireEvent.click(screen.getByText('settings.majorUpgradeInstall'))
    await flush()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('appears and disappears with the data', async () => {
    mocks.get.mockResolvedValueOnce(check({ major_upgrade: null }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.queryByText(/settings\.majorUpgrade/)).toBeNull()

    mocks.get.mockResolvedValueOnce(check({ major_upgrade: { ...UPGRADE, version: '8.0' } }))
    fireEvent.click(screen.getByText('settings.checkNow'))
    await flush()
    expect(screen.getByText(title('8.0'))).toBeInTheDocument()

    mocks.get.mockResolvedValueOnce(check({ major_upgrade: null }))
    fireEvent.click(screen.getByText('settings.checkNow'))
    await flush()
    expect(screen.queryByText(/settings\.majorUpgrade/)).toBeNull()
  })

  it('under Docker names the image tag and offers no button', async () => {
    mocks.get.mockResolvedValue(check({ can_auto_update: false }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(title('7.3'))).toBeInTheDocument()
    expect(screen.getByText(
      `settings.majorUpgradeDocker:${JSON.stringify({ image: 'ghcr.io/neyslim/ultimate-ca-manager:7.3' })}`,
    )).toBeInTheDocument()
    expect(screen.queryByText('settings.majorUpgradeInstall')).toBeNull()
  })
})

describe('security maintenance notice', () => {
  beforeEach(() => { mocks.get.mockReset() })

  it('is shown without a later major, with no upgrade sentence', async () => {
    mocks.get.mockResolvedValue(check({ major_upgrade: null }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText('settings.securityMaintenanceTitle')).toBeInTheDocument()
    expect(screen.getByText('settings.securityMaintenanceNotice')).toBeInTheDocument()
    expect(screen.queryByText(/settings\.securityMaintenanceUpgrade/)).toBeNull()
  })

  it('recommends the later major the data names', async () => {
    mocks.get.mockResolvedValue(check())
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(
      `settings.securityMaintenanceUpgrade:${JSON.stringify({ version: '7.3' })}`,
    )).toBeInTheDocument()
  })

  it('follows the data, not a constant', async () => {
    mocks.get.mockResolvedValue(check({ security_maintenance: false, major_upgrade: null }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.queryByText('settings.securityMaintenanceNotice')).toBeNull()
  })
})
