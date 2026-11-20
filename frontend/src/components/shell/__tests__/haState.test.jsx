/** HA from /health: one shared poll, the banner (maintenance, degraded, nothing outside HA), the write guard, the nodes. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const getServiceStatus = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o ? `${k}|${Object.values(o).join(',')}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../services/system.service', () => ({ systemService: { getServiceStatus } }))

import { haState, guardProps, useHealth, useWriteGuard, resetHealthForTests, WRITES_NOTE_ID, OFFLINE_NOTE_ID } from '../health'
import { StateBanners } from '../StateBanners'
import { NodesDialog } from '../NodesDialog'

const answer = (body) => vi.fn().mockResolvedValue({ ok: true, json: async () => body })
const HA = (extra = {}) => ({ status: 'ok', version: '3.0', ha: true, node_id: 'n1', leader: true,
  cluster: { leader_node_id: 'n1', nodes: 3, stale: 0 }, ...extra })

// The browser's network state, switched as a real one: the property, then its event
let online = true
const goOnline = (value) => act(() => { online = value; window.dispatchEvent(new Event(value ? 'online' : 'offline')) })

beforeEach(() => {
  resetHealthForTests()
  online = true
  vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => online)
})
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('haState', () => {
  it('is null outside HA mode and before an answer', () => {
    expect(haState(null)).toBeNull()
    expect(haState(false)).toBeNull()
    expect(haState({ status: 'ok', ha: false })).toBeNull()
  })

  it('reads nodes, silent nodes, the leader and a maintenance', () => {
    const s = haState(HA({ cluster: { leader_node_id: null, nodes: 3, stale: 1 }, maintenance: { reason: 'manual' } }))
    expect(s).toMatchObject({ node: 'n1', nodes: 3, stale: 1, leaderless: true, maintenance: { reason: 'manual' } })
  })
})

describe('guardProps', () => {
  it('leaves a control as it is when writes run, disables it with the reason during a maintenance', () => {
    expect(guardProps({ suspended: false }, false)).toEqual({ disabled: false })
    expect(guardProps({ suspended: true, noteId: WRITES_NOTE_ID }, false))
      .toEqual({ disabled: true, 'aria-describedby': WRITES_NOTE_ID, 'data-blocked': 'writes' })
  })
})

function Probe() {
  const h = useHealth()
  const g = useWriteGuard()
  return <p data-testid="probe">{`${h ? h.version : String(h)}/${g.suspended}`}</p>
}

describe('shared poll', () => {
  it('asks /health once for every reader, and stops with the last one', async () => {
    vi.useFakeTimers()
    const fetchMock = answer(HA())
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = render(<><Probe /><Probe /><StateBanners /></>)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(90000) })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('suspends writes only while the cluster is in maintenance', async () => {
    vi.stubGlobal('fetch', answer(HA({ maintenance: { reason: 'restore', phase: 'draining' } })))
    render(<Probe />)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('3.0/true'))
  })

  it('never suspends writes outside HA mode', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0', ha: false, maintenance: { reason: 'restore' } }))
    render(<Probe />)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('3.0/false'))
  })
})

describe('offline', () => {
  function Guard() {
    const g = useWriteGuard()
    return <p data-testid="guard">{`${g.suspended}/${g.reason}/${g.noteId}`}</p>
  }

  it('suspends writes while the browser is offline, pointing to the offline sentence, and resumes with the network', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0', ha: false }))
    render(<Guard />)
    expect(screen.getByTestId('guard')).toHaveTextContent('false/null/undefined')
    goOnline(false)
    expect(screen.getByTestId('guard')).toHaveTextContent(`true/offline/${OFFLINE_NOTE_ID}`)
    goOnline(true)
    expect(screen.getByTestId('guard')).toHaveTextContent('false/null/undefined')
  })

  it('shows the neutral offline banner of the mockup, whose sentence the guard points to', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0', ha: false }))
    const { container } = render(<StateBanners />)
    expect(container.querySelector('.shell-state-banner')).toBeNull()
    goOnline(false)
    const banner = container.querySelector('#shell-offline-banner')
    expect(banner).not.toHaveClass('is-warn')
    expect(banner.querySelector('p')).toHaveAttribute('id', OFFLINE_NOTE_ID)
    expect(banner).toHaveTextContent('shell.offline.title shell.offline.text')
  })

  it('says the network went, then says it came back in a message', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0', ha: false }))
    const onNotice = vi.fn()
    render(<StateBanners onNotice={onNotice} />)
    goOnline(false)
    expect(screen.getByRole('status')).toHaveTextContent('shell.offline.said')
    expect(onNotice).not.toHaveBeenCalled()
    goOnline(true)
    expect(onNotice).toHaveBeenCalledWith('shell.offline.back')
    expect(screen.getByRole('status')).toHaveTextContent('')
    expect(document.getElementById('shell-offline-banner')).toBeNull()
  })
})

describe('StateBanners', () => {
  it('renders nothing outside HA mode', async () => {
    vi.stubGlobal('fetch', answer({ status: 'ok', version: '3.0', ha: false }))
    const { container } = render(<><Probe /><StateBanners /></>)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('3.0/false'))
    expect(container.querySelector('.shell-state-banner')).toBeNull()
  })

  it('renders nothing for a healthy cluster', async () => {
    vi.stubGlobal('fetch', answer(HA()))
    const { container } = render(<><Probe /><StateBanners /></>)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('3.0/false'))
    expect(container.querySelector('.shell-state-banner')).toBeNull()
  })

  it('says the writes are suspended during a maintenance, in the sentence the guard points to', async () => {
    vi.stubGlobal('fetch', answer(HA({ maintenance: { reason: 'restore', phase: 'draining', expires_at: null } })))
    render(<StateBanners />)
    const note = await screen.findByText(/shell\.ha\.maintenanceOpen/)
    expect(note.closest('p')).toHaveAttribute('id', WRITES_NOTE_ID)
    expect(screen.getByText(/shell\.ha\.maintenanceTitle\|shell\.ha\.reasons\.restore/)).toBeInTheDocument()
  })

  it('says how many nodes are silent and what still works, and waits for a leader when none is left', async () => {
    vi.stubGlobal('fetch', answer(HA({ node_id: 'n2', leader: false, cluster: { leader_node_id: null, nodes: 3, stale: 1 } })))
    render(<StateBanners />)
    expect(await screen.findByText('shell.ha.degradedOf|1,3')).toBeInTheDocument()
    expect(screen.getByText('shell.ha.canRead')).toBeInTheDocument()
    expect(screen.getByText('shell.ha.canWriteOn|n2')).toBeInTheDocument()
    expect(screen.getByText('shell.ha.scheduleWaits')).toBeInTheDocument()
  })

  it('names the leader carrying the scheduled tasks, and opens the node list when it may', async () => {
    vi.stubGlobal('fetch', answer(HA({ cluster: { leader_node_id: 'n1', nodes: 3, stale: 2 } })))
    const onShowNodes = vi.fn()
    render(<StateBanners onShowNodes={onShowNodes} />)
    expect(await screen.findByText('shell.ha.scheduleOn|n1')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'shell.ha.showNodes' }))
    expect(onShowNodes).toHaveBeenCalledTimes(1)
  })

  it('has no node button without the right to read them', async () => {
    vi.stubGlobal('fetch', answer(HA({ cluster: { leader_node_id: 'n1', nodes: 3, stale: 1 } })))
    render(<StateBanners />)
    await screen.findByText('shell.ha.degradedOf|1,3')
    expect(screen.queryByRole('button', { name: 'shell.ha.showNodes' })).toBeNull()
  })
})

describe('NodesDialog', () => {
  it('lists the nodes of the service status: role, heartbeat, state, version', async () => {
    const beat = new Date(Date.now() - 12000).toISOString()
    getServiceStatus.mockResolvedValue({ data: { cluster: { node_id: 'n1', nodes: [
      { node_id: 'n1', leader: true, stopped: false, stale: false, version: '3.0', heartbeat_at: beat },
      { node_id: 'n2', leader: false, stopped: false, stale: true, version: '3.0', heartbeat_at: beat },
    ] } } })
    render(<NodesDialog open onClose={() => {}} ha={{ stale: 1 }} />)
    expect(await screen.findByText('n2')).toBeInTheDocument()
    expect(screen.getByText('shell.nodes.leader')).toBeInTheDocument()
    expect(screen.getByText('shell.nodes.secondary')).toBeInTheDocument()
    expect(screen.getByText('shell.nodes.silent')).toBeInTheDocument()
    expect(screen.getAllByText(/^shell\.nodes\.secondsAgo\|1[12]$/)).toHaveLength(2)
    expect(screen.getByText('shell.nodes.introLate|1')).toBeInTheDocument()
  })

  it('is the list template dialog of the mockup: wide, its state on one line, closed by its Close button', async () => {
    getServiceStatus.mockResolvedValue({ data: { cluster: { nodes: [
      { node_id: 'n1', leader: true, stopped: false, stale: false, version: '3.0', heartbeat_at: new Date().toISOString() }] } } })
    const onClose = vi.fn()
    render(<NodesDialog open onClose={onClose} ha={{ stale: 0 }} />)
    const dialog = await screen.findByRole('dialog', { name: 'shell.nodes.title' })
    expect(dialog).toHaveClass('lv-dialog', 'is-wide')
    const state = (await screen.findByText('shell.nodes.live')).closest('span')
    expect(state.tagName).toBe('SPAN')
    expect(state.querySelector('svg')).toHaveAttribute('width', '13')
    const close = screen.getByRole('button', { name: 'common.close' })
    expect(close).toHaveClass('lv-btn', 'is-primary')
    expect(close).toHaveAttribute('data-write', 'false')
    await userEvent.click(close)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('says when the list cannot be read', async () => {
    getServiceStatus.mockRejectedValue(new Error('403'))
    render(<NodesDialog open onClose={() => {}} ha={{ stale: 0 }} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('shell.nodes.loadFailed')
  })
})
