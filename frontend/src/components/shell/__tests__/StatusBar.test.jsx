/** The status bar shows what /health reports, and invents nothing. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o ? `${k}|${Object.values(o).join(',')}` : k) }),
}))

import { StatusBar } from '../StatusBar'

const answer = (body, ok = true) => vi.fn().mockResolvedValue({ ok, json: async () => body })

beforeEach(() => { vi.useRealTimers() })
afterEach(() => { vi.unstubAllGlobals() })

describe('StatusBar', () => {
  it('shows the version and a running service', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false }))
    render(<StatusBar />)
    expect(await screen.findByText('shell.version|3.0.0')).toBeInTheDocument()
    expect(screen.getByText('shell.statusRunning')).toBeInTheDocument()
  })

  it('shows no HA part outside HA mode', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: false, node_id: 'n1', leader: true }))
    render(<StatusBar />)
    await screen.findByText('shell.statusRunning')
    expect(screen.queryByText(/shell\.haNode/)).toBeNull()
    expect(screen.queryByText('shell.haLeader')).toBeNull()
  })

  it('shows the node, its role and the cluster in HA mode', async () => {
    vi.stubGlobal('fetch', answer({
      status: 'ok', version: '3.0.0', ha: true, node_id: 'n2', leader: false,
      cluster: { leader_node_id: 'n1', nodes: 3, stale: 1 },
    }))
    render(<StatusBar />)
    expect(await screen.findByText('shell.haNode|n2')).toBeInTheDocument()
    expect(screen.getByText('shell.haFollower')).toBeInTheDocument()
    expect(screen.getByText('shell.haNodes|3')).toBeInTheDocument()
    expect(screen.getByText('shell.haLate|1')).toBeInTheDocument()
  })

  it('leaves the role out when the node does not know it', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', ha: true, node_id: 'n2', leader: null, cluster: null }))
    render(<StatusBar />)
    await screen.findByText('shell.haNode|n2')
    expect(screen.queryByText('shell.haLeader')).toBeNull()
    expect(screen.queryByText('shell.haFollower')).toBeNull()
    expect(screen.queryByText(/shell\.haNodes/)).toBeNull()
  })

  it('reports safe mode as a warning, not as running', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0.0', safe_mode: true }))
    render(<StatusBar />)
    expect(await screen.findByText('shell.statusSafeMode')).toBeInTheDocument()
    expect(screen.queryByText('shell.statusRunning')).toBeNull()
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
    expect(screen.getByText('shell.version|3.0.1')).toBeInTheDocument()
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
