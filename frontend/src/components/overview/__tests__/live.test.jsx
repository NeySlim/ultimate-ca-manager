/**
 * The overview cards follow the data: an event that concerns a card reloads that card only,
 * a burst reloads it once, a reconnection and the tab coming back reload it, and the button reloads all.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k, o) => (o?.defaultValue ?? k) }) }))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getHealth: vi.fn(), getCompliance: vi.fn(), getIssuance: vi.fn(),
  getStats: vi.fn(), getAll: vi.fn(), getNext: vi.fn(), getActivity: vi.fn(),
}))
const ws = vi.hoisted(() => ({ state: 'connected' }))
vi.mock('../../../services', () => ({
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getCompliance: api.getCompliance, getIssuance: api.getIssuance },
  certificatesService: { getStats: api.getStats },
  casService: { getAll: api.getAll },
  dashboardService: { getNextExpirations: api.getNext, getActivityLog: api.getActivity },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: ws.state }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))

import { QueueCard, ComplianceCard, HealthCard, HierarchyCard, HorizonCard, ActivityCard } from '..'
import { REFRESH_EVENT } from '../../../lib/overviewRefresh'

const CARDS = { queue: [QueueCard, api.getQueue], compliance: [ComplianceCard, api.getCompliance],
  health: [HealthCard, api.getHealth], hierarchy: [HierarchyCard, api.getAll],
  horizon: [HorizonCard, api.getStats], activity: [ActivityCard, api.getActivity] }

const announce = (type) => act(() => { window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type } })) })
const settle = async (ms = 0) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
const counts = () => Object.fromEntries(Object.entries(CARDS).map(([id, [, fn]]) => [id, fn.mock.calls.length]))

async function mountAll() {
  render(<MemoryRouter>{Object.entries(CARDS).map(([id, [Card]]) => <Card key={id} />)}</MemoryRouter>)
  await settle()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  ws.state = 'connected'
  api.getQueue.mockResolvedValue({ data: { items: [], counts: {}, total: 0 } })
  api.getCompliance.mockResolvedValue({ data: { total: 1, counters: {}, by_key_algorithm: [] } })
  api.getHealth.mockResolvedValue({ data: { protocols: { acme: { periods: [], last_status: 'ok' } } } })
  api.getAll.mockResolvedValue({ data: [] })
  api.getStats.mockResolvedValue({ data: { total: 1 } })
  api.getNext.mockResolvedValue({ data: [] })
  api.getActivity.mockResolvedValue({ data: { activity: [] } })
  api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
})
afterEach(() => { vi.useRealTimers() })

describe('overview cards follow the data', () => {
  it('an event reloads the cards it concerns and not the others', async () => {
    await mountAll()
    const before = counts()
    announce('user')
    await settle(5000)
    const after = counts()
    expect(after.activity).toBe(before.activity + 1)
    for (const id of Object.keys(CARDS).filter((c) => c !== 'activity')) expect(after[id], id).toBe(before[id])
  })

  it('a burst of events reloads a card once', async () => {
    await mountAll()
    const before = counts()
    for (let i = 0; i < 25; i += 1) announce('certificate')
    await settle(5000)
    const after = counts()
    expect(after.horizon).toBe(before.horizon + 1)
    expect(after.queue).toBe(before.queue + 1)
  })

  it('keeps showing the data while it reloads', async () => {
    api.getQueue.mockResolvedValue({ data: { items: [{ kind: 'manual_renewal_due', tier: 'warning', id: 1, label: 'cert-one', href_hint: '/certificates/1' }], counts: {}, total: 1 } })
    await mountAll()
    expect(screen.getByText('cert-one')).toBeTruthy()
    api.getQueue.mockReturnValue(new Promise(() => {}))
    announce('certificate')
    await settle(2500)
    expect(screen.getByText('cert-one')).toBeTruthy()
    expect(screen.queryByText('overview.state.loading')).toBeNull()
  })

  it('a reconnection reloads every card', async () => {
    const tree = () => <MemoryRouter>{Object.entries(CARDS).map(([id, [Card]]) => <Card key={id} />)}</MemoryRouter>
    const view = render(tree())
    await settle()
    const before = counts()
    ws.state = 'disconnected'
    view.rerender(tree())
    await settle(1000)
    expect(counts()).toEqual(before)
    ws.state = 'connected'
    view.rerender(tree())
    await settle(5000)
    const after = counts()
    for (const id of Object.keys(CARDS)) expect(after[id], id).toBe(before[id] + 1)
  })

  it('the tab coming back to the foreground reloads the cards', async () => {
    await mountAll()
    const before = counts()
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await settle(5000)
    for (const id of Object.keys(CARDS)) expect(counts()[id], id).toBe(before[id] + 1)
  })

  it('the refresh button reloads every card at once', async () => {
    await mountAll()
    const before = counts()
    act(() => { window.dispatchEvent(new Event(REFRESH_EVENT)) })
    await settle(0)
    for (const id of Object.keys(CARDS)) expect(counts()[id], id).toBe(before[id] + 1)
  })

  it('does not poll while the socket is up', async () => {
    await mountAll()
    const before = counts()
    await settle(10 * 60 * 1000)
    expect(counts()).toEqual(before)
  })

  it('polls slowly while the socket is down', async () => {
    ws.state = 'disconnected'
    await mountAll()
    const before = counts()
    await settle(65 * 1000)
    for (const id of Object.keys(CARDS)) expect(counts()[id], id).toBe(before[id] + 1)
  })
})
