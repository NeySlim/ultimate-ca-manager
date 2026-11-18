/** A later major version is an explicit, confirmed upgrade shown apart from the update. */
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
  version: '4.3', html_url: 'https://example.invalid/releases/v4.3', release_notes: '',
  download_url: 'http://x/ucm_4.3_all.deb',
}
const check = (over = {}) => ({
  data: {
    update_available: false, can_auto_update: true, current_version: '3.1',
    latest_version: '3.1', major_upgrade: UPGRADE, ...over,
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

  it('shows the section with the version of the data and installs on confirmation', async () => {
    mocks.get.mockResolvedValue(check())
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(title('4.3'))).toBeInTheDocument()
    expect(screen.getByText('settings.majorUpgradeDesc')).toBeInTheDocument()
    expect(screen.getByText('settings.majorUpgradeNotes').closest('a'))
      .toHaveAttribute('href', 'https://example.invalid/releases/v4.3')

    fireEvent.click(screen.getByText('settings.majorUpgradeInstall'))
    await flush()
    expect(mocks.showConfirm).toHaveBeenCalledTimes(1)
    expect(mocks.post).toHaveBeenCalledWith('/system/updates/install', { major_upgrade: true, version: '4.3' })
    expect(mocks.waitForRestart).toHaveBeenCalledWith(expect.objectContaining({ expectedVersion: '4.3' }))
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

    mocks.get.mockResolvedValueOnce(check({ major_upgrade: { ...UPGRADE, version: '5.0' } }))
    fireEvent.click(screen.getByText('settings.checkNow'))
    await flush()
    expect(screen.getByText(title('5.0'))).toBeInTheDocument()

    mocks.get.mockResolvedValueOnce(check({ major_upgrade: null }))
    fireEvent.click(screen.getByText('settings.checkNow'))
    await flush()
    expect(screen.queryByText(/settings\.majorUpgrade/)).toBeNull()
  })

  it('under Docker names the image tag and offers no button', async () => {
    // Under Docker the server names no package: the tag is built from the version
    mocks.get.mockResolvedValue(check({ can_auto_update: false, major_upgrade: { ...UPGRADE, download_url: null } }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(title('4.3'))).toBeInTheDocument()
    expect(screen.getByText(
      `settings.majorUpgradeDocker:${JSON.stringify({ image: 'ghcr.io/neyslim/ultimate-ca-manager:4.3' })}`,
    )).toBeInTheDocument()
    expect(screen.queryByText('settings.majorUpgradeInstall')).toBeNull()
  })

  it('under Docker shows the image the server names', async () => {
    const image = 'ghcr.io/neyslim/ultimate-ca-manager:4.3-fips'
    mocks.get.mockResolvedValue(check({
      can_auto_update: false,
      major_upgrade: { version: '4.3', html_url: 'https://example.invalid/r', download_url: image },
    }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(`settings.majorUpgradeDocker:${JSON.stringify({ image })}`)).toBeInTheDocument()
  })

  it('asks the confirmation that fits the mode: a restart, or a rolling update in HA', async () => {
    const values = JSON.stringify({ current: '3.1', version: '4.3' })
    mocks.get.mockResolvedValueOnce(check())
    const first = render(<UpdateChecker />)
    await flush()
    fireEvent.click(screen.getByText('settings.majorUpgradeInstall'))
    await flush()
    expect(mocks.showConfirm.mock.calls[0][0]).toBe(`settings.majorUpgradeConfirm:${values}`)
    first.unmount()

    mocks.get.mockResolvedValueOnce(check({ ha_mode: true }))
    render(<UpdateChecker />)
    await flush()
    fireEvent.click(screen.getByText('settings.majorUpgradeInstall'))
    await flush()
    expect(mocks.showConfirm.mock.calls[1][0]).toBe(`settings.majorUpgradeConfirmHa:${values}`)
  })

  it('in HA starts a campaign instead of waiting for a restart', async () => {
    const campaign = { id: 'c1', status: 'stopped', target: '4.3', order: [], done: [], current: null, failed: null, skipped: [] }
    mocks.get.mockResolvedValue(check({ ha_mode: true }))
    mocks.post.mockResolvedValue({ data: { campaign } })
    render(<UpdateChecker />)
    await flush()
    fireEvent.click(screen.getByText('settings.majorUpgradeInstall'))
    await flush()
    expect(mocks.post).toHaveBeenCalledWith('/system/updates/install', { major_upgrade: true, version: '4.3' })
    expect(mocks.waitForRestart).not.toHaveBeenCalled()
  })
})

describe('docker hint of an ordinary update', () => {
  it('names the tag of the new version, never latest', async () => {
    mocks.get.mockResolvedValue(check({
      update_available: true, can_auto_update: false, latest_version: '3.2', major_upgrade: null,
      download_url: null,
    }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(/docker pull ghcr\.io\/neyslim\/ultimate-ca-manager:3\.2/)).toBeInTheDocument()
    expect(screen.queryByText(/:latest/)).toBeNull()
  })

  it('shows the image the server names when it names one', async () => {
    mocks.get.mockResolvedValue(check({
      update_available: true, can_auto_update: false, latest_version: '3.2', major_upgrade: null,
      download_url: 'ghcr.io/neyslim/ultimate-ca-manager:3.2-fips',
    }))
    render(<UpdateChecker />)
    await flush()
    expect(screen.getByText(/docker pull ghcr\.io\/neyslim\/ultimate-ca-manager:3\.2-fips/)).toBeInTheDocument()
  })
})
