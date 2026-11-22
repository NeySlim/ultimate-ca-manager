/**
 * The status bar's activity in short: pending approvals, background jobs, the overview's
 * interventions and the detached windows, each a way to its page, only what the role may read;
 * « Nothing pending » when all of it is calm; nothing asked when nothing may be read.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o ? `${k}|${Object.values(o).join(',')}` : k) }),
}))
vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => null }))
const api = vi.hoisted(() => ({ getStats: vi.fn(), getQueue: vi.fn(), list: vi.fn() }))
vi.mock('../../../services/approvals.service', () => ({ approvalsService: { getStats: api.getStats } }))
vi.mock('../../../services/overview.service', () => ({ overviewService: { getQueue: api.getQueue } }))
vi.mock('../../../services/jobs.service', () => ({ default: { list: api.list } }))

import { StatusBar } from '../StatusBar'
import { DetachedContext } from '../../detached/useDetached'
import { canFor } from './shellTestUtils'

const health = () => vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', version: '3.0.0', ha: false }) })
const bar = (perms, detached = null) => render(
  <MemoryRouter>
    <DetachedContext.Provider value={detached}><StatusBar can={canFor(perms)} /></DetachedContext.Provider>
  </MemoryRouter>,
)
const activity = () => screen.getByRole('group', { name: 'shell.activity.label' })
// Two interventions (one critical expiry of a CA counts), one CA only to watch
const QUEUE = {
  data: {
    total: 3, counts: { approval_pending: 1, crl_missing: 1, ca_expiring: 1 },
    items: [{ kind: 'crl_missing', tier: 'critical', id: 1 }, { kind: 'approval_pending', tier: 'warning', id: 2 }, { kind: 'ca_expiring', tier: 'warning', id: 3 }],
  },
}

beforeEach(() => {
  vi.stubGlobal('fetch', health())
  api.getStats.mockReset().mockResolvedValue({ data: { pending: 0 } })
  api.getQueue.mockReset().mockResolvedValue({ data: { total: 0, counts: {}, items: [] } })
  api.list.mockReset().mockResolvedValue({ data: [] })
})
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('status bar activity', () => {
  it('says « Nothing pending » once all it may read is calm', async () => {
    bar(['*'])
    expect(await screen.findByText('shell.activity.calm')).toBeInTheDocument()
    expect(within(activity()).queryByRole('link')).toBeNull()
  })

  it('links each part to its page: approvals, a running backup, the interventions of the overview', async () => {
    api.getStats.mockResolvedValue({ data: { pending: 2 } })
    api.getQueue.mockResolvedValue(QUEUE)
    api.list.mockResolvedValue({ data: [{ id: 'j1', kind: 'backup', state: 'running' }, { id: 'j2', kind: 'audit_verify', state: 'pending' }] })
    bar(['*'])
    expect(await screen.findByRole('link', { name: 'shell.approvalsPending|2' })).toHaveAttribute('href', '/approvals')
    expect(await screen.findByRole('link', { name: 'shell.activity.queue|2' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'shell.activity.jobs.backup' })).toHaveAttribute('href', '/settings?tab=backup')
    expect(screen.getByRole('link', { name: 'shell.activity.jobs.audit_verify' })).toHaveAttribute('href', '/audit')
    expect(screen.queryByText('shell.activity.calm')).toBeNull()
    expect(api.list).toHaveBeenCalledWith({ state: 'active', limit: 10 })
  })

  it('asks only what the role may read', async () => {
    bar(['read:dashboard'])
    expect(await screen.findByText('shell.activity.calm')).toBeInTheDocument()
    expect(api.getQueue).toHaveBeenCalledTimes(1)
    expect(api.getStats).not.toHaveBeenCalled()
    expect(api.list).not.toHaveBeenCalled()
  })

  it('asks nothing and shows nothing when nothing may be read', async () => {
    bar(['read:certificates'])
    await screen.findByText(/shell\.statusRunning/)
    expect(screen.queryByRole('group', { name: 'shell.activity.label' })).toBeNull()
    expect(api.getStats).not.toHaveBeenCalled()
    expect(api.getQueue).not.toHaveBeenCalled()
    expect(api.list).not.toHaveBeenCalled()
  })

  it('reads again on a data change and once a minute', async () => {
    vi.useFakeTimers()
    bar(['read:dashboard'])
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(api.getQueue).toHaveBeenCalledTimes(1)
    act(() => { window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate' } })) })
    expect(api.getQueue).toHaveBeenCalledTimes(2)
    await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
    expect(api.getQueue).toHaveBeenCalledTimes(3)
  })

  it('lists the detached windows, the chosen one brought in front with the focus', async () => {
    const front = vi.fn()
    const detached = { available: true, front, windows: [{ key: 'certificate:7', kind: 'certificate', title: 'vpn' }, { key: 'compare:7,8', kind: 'compare', title: 'Comparer 2' }] }
    bar(['read:certificates'], detached)
    const button = await screen.findByRole('button', { name: 'shell.activity.windows|2' })
    fireEvent.click(button)
    const menu = screen.getByRole('menu', { name: 'shell.activity.windowsLabel' })
    // The front window first
    expect(within(menu).getAllByRole('menuitem').map((b) => b.textContent)).toEqual(['Comparer 2', 'vpn'])
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'vpn' }))
    expect(front).toHaveBeenCalledWith('certificate:7', { focus: true })
  })

  it('lists no window where none can be drawn (a phone)', async () => {
    bar(['read:certificates'], { available: false, front: vi.fn(), windows: [{ key: 'certificate:7', kind: 'certificate', title: 'vpn' }] })
    await screen.findByText(/shell\.statusRunning/)
    expect(screen.queryByRole('button', { name: /shell\.activity\.windows/ })).toBeNull()
  })
})
