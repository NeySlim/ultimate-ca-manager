/** The status bar shows what /health reports, and invents nothing. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o ? `${k}|${Object.values(o).join(',')}` : k) }),
}))

vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => <span data-testid="ws" /> }))
const getStats = vi.hoisted(() => vi.fn())
vi.mock('../../../services/approvals.service', () => ({ approvalsService: { getStats } }))

import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { StatusBar } from '../StatusBar'
import { canFor } from './shellTestUtils'

const answer = (body, ok = true) => vi.fn().mockResolvedValue({ ok, json: async () => body })

beforeEach(() => { vi.useRealTimers() })
afterEach(() => { vi.unstubAllGlobals() })

describe('StatusBar', () => {
  it('says the version and the service state in one sentence, as the mockup', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false }))
    render(<StatusBar />)
    const line = await screen.findByText('shell.version|3.0.0 · shell.statusRunning')
    expect(line.tagName).toBe('SPAN')
  })

  it('links the pending approvals to their module, for who may read them', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false }))
    getStats.mockResolvedValue({ data: { pending: 2 } })
    const { unmount } = render(<MemoryRouter><StatusBar can={canFor(['read:approvals'])} /></MemoryRouter>)
    const link = await screen.findByRole('link', { name: 'shell.approvalsPending|2' })
    expect(link).toHaveAttribute('href', '/approvals')
    unmount()
    getStats.mockResolvedValue({ data: { pending: 0 } })
    render(<MemoryRouter><StatusBar can={canFor(['read:approvals'])} /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'shell.approvalsNone' })).toHaveAttribute('href', '/approvals')
  })

  it('has no approvals link without read:approvals, and does not ask', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false }))
    getStats.mockClear()
    render(<MemoryRouter><StatusBar can={canFor(['read:certificates'])} /></MemoryRouter>)
    await screen.findByText(/shell\.statusRunning/)
    expect(screen.queryByRole('link')).toBeNull()
    expect(getStats).not.toHaveBeenCalled()
  })

  it('reminds the shortcuts: Ctrl K searches, Escape closes the inspector', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false }))
    const { container } = render(<StatusBar />)
    await screen.findByText(/shell\.statusRunning/)
    const keys = [...container.querySelectorAll('.shortcut kbd')].map((k) => k.textContent)
    expect(keys).toEqual(['Ctrl K', 'shell.escapeKey'])
    expect(container.querySelector('.shortcut > span')).toHaveTextContent('shell.escapeKey inspector.close')
  })

  it('shows no HA part outside HA mode', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false, node_id: 'n1', leader: true }))
    render(<StatusBar />)
    await screen.findByText(/shell\.statusRunning/)
    expect(screen.queryByText(/shell\.haNode/)).toBeNull()
    expect(screen.queryByText('shell.haLeader')).toBeNull()
  })

  it('shows the node, its role and the cluster in HA mode', async () => {
    vi.stubGlobal('fetch', answer({
      status: 'ok', version: '3.0.0', ha: true, node_id: 'n2', leader: false,
      cluster: { leader_node_id: 'n1', nodes: 3, stale: 0 },
    }))
    render(<StatusBar />)
    expect(await screen.findByText(/shell\.haNode\|n2/)).toBeInTheDocument()
    expect(screen.getByText(/shell\.haFollower/)).toBeInTheDocument()
    expect(screen.getByText('shell.haNodes|3').closest('.ha-link')).toHaveClass('good')
  })

  // On a phone the mockup's bar holds the version line, then approvals and the cluster state on one
  // line: the node and its role are kept for assistive technology only (the node list has them)
  it('marks the node and its role as the part a phone keeps out of sight, never the indicator', async () => {
    vi.stubGlobal('fetch', answer({
      status: 'ok', version: '3.0.0', ha: true, node_id: 'n1', leader: true,
      cluster: { leader_node_id: 'n1', nodes: 2, stale: 1 },
    }))
    const { container } = render(<StatusBar />)
    await screen.findByText(/shell\.haNode\|n1/)
    expect(container.querySelector('.live .ha-node').textContent).toBe(' · shell.haNode|n1 · shell.haLeader')
    expect(screen.getByText('shell.haLate|1').closest('.ha-node')).toBeNull()
  })

  it('says how many nodes are late, as a warning, in place of the node count', async () => {
    vi.stubGlobal('fetch', answer({
      status: 'ok', version: '3.0.0', ha: true, node_id: 'n2', leader: false,
      cluster: { leader_node_id: 'n1', nodes: 3, stale: 1 },
    }))
    render(<StatusBar />)
    expect((await screen.findByText('shell.haLate|1')).closest('.ha-link')).toHaveClass('warn')
    expect(screen.queryByText('shell.haNodes|3')).toBeNull()
  })

  it('says a maintenance is in progress', async () => {
    vi.stubGlobal('fetch', answer({
      status: 'ok', version: '3.0.0', ha: true, node_id: 'n1', leader: true,
      cluster: { leader_node_id: 'n1', nodes: 2, stale: 0 }, maintenance: { reason: 'restore', phase: 'draining' },
    }))
    render(<StatusBar />)
    expect((await screen.findByText('shell.haMaintenanceShort')).closest('.ha-link')).toHaveClass('warn')
  })

  it('opens the node list from the indicator when it may, and is plain text otherwise', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: true, node_id: 'n1', leader: true,
      cluster: { leader_node_id: 'n1', nodes: 2, stale: 0 } }))
    const onShowNodes = vi.fn()
    const { unmount } = render(<StatusBar onShowNodes={onShowNodes} />)
    const button = await screen.findByRole('button', { name: /shell\.haIndicatorLabel/ })
    await userEvent.click(button)
    expect(onShowNodes).toHaveBeenCalledTimes(1)
    unmount()
    render(<StatusBar />)
    await screen.findByText('shell.haNodes|2')
    expect(screen.queryByRole('button', { name: /shell\.haIndicatorLabel/ })).toBeNull()
  })

  it('keeps the live connection indicator in the bar', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false }))
    render(<StatusBar />)
    await screen.findByText(/shell\.statusRunning/)
    expect(screen.getByTestId('ws')).toBeInTheDocument()
    // drawn with the mockup's rules: nothing of the bar is left to the product's own styles
    expect(document.querySelector('.statusbar .atl-out')).toBeNull()
  })

  it('leaves the role out when the node does not know it', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: true, node_id: 'n2', leader: null, cluster: null }))
    render(<StatusBar />)
    await screen.findByText(/shell\.haNode\|n2/)
    expect(screen.queryByText(/shell\.haLeader/)).toBeNull()
    expect(screen.queryByText(/shell\.haFollower/)).toBeNull()
    expect(screen.queryByText(/shell\.haNodes/)).toBeNull()
  })

  it('reports safe mode as a warning, not as running', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', safe_mode: true }))
    render(<StatusBar />)
    expect(await screen.findByText(/shell\.statusSafeMode/)).toBeInTheDocument()
    expect(screen.queryByText(/shell\.statusRunning/)).toBeNull()
  })

  it.each([
    ['a network failure', () => vi.fn().mockRejectedValue(new Error('down'))],
    ['an error status', () => answer({}, false)],
  ])('says the service is unreachable on %s, with no version', async (_name, make) => {
    vi.stubGlobal('fetch', make())
    render(<StatusBar />)
    expect(await screen.findByText('shell.statusUnreachable')).toBeInTheDocument()
    expect(screen.queryByText(/shell\.version/)).toBeNull()
  })

  it('polls again and recovers', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', version: '3.0.1' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<StatusBar />)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(screen.getByText('shell.statusUnreachable')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(screen.getByText(/shell\.version\|3\.0\.1/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('stops polling on unmount', async () => {
    vi.useFakeTimers()
    const fetchMock = answer({ status: 'ok', version: '3.0.0' })
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = render(<StatusBar />)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(120000) })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
