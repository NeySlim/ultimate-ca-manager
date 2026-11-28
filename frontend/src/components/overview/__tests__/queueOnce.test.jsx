/** The shell and the Overview cards read the queue once when the page opens. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, renderHook, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ Trans: ({ i18nKey }) => i18nKey, useTranslation: () => ({ t: (k) => k }) }))
const get = vi.hoisted(() => vi.fn())
vi.mock('../../../services/apiClient', async (importOriginal) => ({
  ...(await importOriginal()),
  apiClient: { get },
  buildQueryString: (q) => `?limit=${q.limit}`,
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { QueueCard, MetricStrip } from '..'
import { overviewService } from '../../../services/overview.service'
import { useActivity } from '../../shell/useActivity'
import { dropSharedRequests } from '../../../lib/sharedRequest'

const queue = { data: { items: [], total: 0, counts: {}, filter_hints: {} } }

beforeEach(() => {
  dropSharedRequests()
  get.mockReset()
  get.mockResolvedValue(queue)
})

describe('queue reads on opening', () => {
  it('serves the cards from the shell read that just ended', async () => {
    await overviewService.getQueue()
    render(<MemoryRouter><QueueCard /><MetricStrip showQueue /></MemoryRouter>)
    await screen.findByText('overview.cards.queue')
    await new Promise((r) => setTimeout(r, 50))
    const queueReads = get.mock.calls.filter(([url]) => url.startsWith('/dashboard/queue'))
    expect(queueReads).toHaveLength(1)
  })

  it('asks again for a reload after the opening', async () => {
    await overviewService.getQueue()
    await overviewService.getQueue()
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('the shell opening while the cards read joins their read', async () => {
    let release
    get.mockImplementation(() => new Promise((r) => { release = () => r(queue) }))
    const cards = overviewService.getQueue(100, { reuse: true })
    const can = { hasPermission: (p) => p === 'read:dashboard' }
    renderHook(() => useActivity(can))
    const queueReads = () => get.mock.calls.filter(([url]) => url.startsWith('/dashboard/queue')).length
    await act(async () => { await new Promise((r) => setTimeout(r, 10)) })
    expect(queueReads()).toBe(1)
    await act(async () => { release(); await cards })
  })
})
