/**
 * HA: the update screen follows the rolling update instead of waiting for a restart,
 * and names the node where a stopped campaign failed, with its reason.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), showConfirm: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, values) => (values ? `${key}:${Object.values(values).join('|')}` : key),
  }),
}))
vi.mock('../../services', () => ({ apiClient: { get: mocks.get, post: mocks.post } }))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: mocks.showConfirm }),
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

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })

const running = {
  id: 'c1', status: 'running', target: '3.1', order: ['n1', 'n2', 'n3'], done: ['n1'],
  current: { node: 'n2', state: 'installing' }, failed: null, skipped: [],
}

function checkAnswer(campaign) {
  return {
    data: {
      update_available: true, can_auto_update: true, ha_mode: true, download_url: 'x',
      latest_version: '3.1', current_version: '3.0', update_campaign: campaign,
    },
  }
}

describe('rolling update on the update screen', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.showConfirm.mockResolvedValue(true)
  })
  afterEach(() => vi.useRealTimers())

  it('starts a campaign without the restart overlay and shows its nodes', async () => {
    mocks.get.mockResolvedValue(checkAnswer(null))
    mocks.post.mockResolvedValue({ data: { campaign: running } })
    render(<UpdateChecker />)
    await tick(0)
    fireEvent.click(screen.getByText('Install Update'))
    await tick(0)
    expect(mocks.post).toHaveBeenCalledWith('/system/updates/install', expect.anything())
    expect(screen.queryByText(/reconnect\.updateNote/)).toBeNull()
    expect(screen.getByText('settings.updateCampaign.title:3.1')).toBeInTheDocument()
    expect(screen.getByText('n1')).toBeInTheDocument()
    expect(screen.getByText('n2')).toBeInTheDocument()
    expect(screen.getByText('n3')).toBeInTheDocument()
    expect(screen.queryByText('Install Update')).toBeNull()

    mocks.get.mockResolvedValue({ data: { campaign: { ...running, done: ['n1', 'n2'], current: { node: 'n3' } } } })
    await tick(10000)
    expect(mocks.get).toHaveBeenCalledWith('/system/updates/campaign')
    expect(screen.getByText('n1, n2')).toBeInTheDocument()
  })

  it('shows the package family each node installs', async () => {
    mocks.get.mockResolvedValue(checkAnswer({ ...running, families: { n1: 'deb', n2: 'rpm-el9', n3: 'rpm-fedora' } }))
    render(<UpdateChecker />)
    await tick(0)
    expect(screen.getByText('settings.updateCampaign.packages')).toBeInTheDocument()
    expect(screen.getByText('n1: deb, n2: rpm-el9, n3: rpm-fedora')).toBeInTheDocument()
  })

  it('names a node of no reported family in the interface language', async () => {
    mocks.get.mockResolvedValue(checkAnswer({ ...running, families: { n1: 'deb', n2: null } }))
    render(<UpdateChecker />)
    await tick(0)
    expect(screen.getByText('n1: deb, n2: common.unknown')).toBeInTheDocument()
  })

  it('names the failed node and its reason, and resumes on request', async () => {
    const stopped = { ...running, status: 'stopped', current: null,
      failed: { node: 'n2', reason: 'not back within 900s' } }
    mocks.get.mockResolvedValue(checkAnswer(stopped))
    mocks.post.mockResolvedValue({ data: { campaign: { ...stopped, status: 'running', failed: null } } })
    render(<UpdateChecker />)
    await tick(0)
    expect(screen.getByText('settings.updateCampaign.failed:n2|not back within 900s')).toBeInTheDocument()
    fireEvent.click(screen.getByText('settings.updateCampaign.resume'))
    await tick(0)
    expect(mocks.post).toHaveBeenCalledWith('/system/updates/campaign/resume', {})
    expect(screen.queryByText(/settings\.updateCampaign\.failed/)).toBeNull()
  })
})
