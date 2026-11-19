/** Latest operations: a delay with the exact date behind it, a mark while the live link is up, six rows at most. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))
const api = vi.hoisted(() => ({ getActivity: vi.fn(), can: vi.fn() }))
const ws = vi.hoisted(() => ({ state: 'connected' }))
vi.mock('../../../services', () => ({ dashboardService: { getActivityLog: api.getActivity } }))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: ws.state }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: api.can }) }))

import { ActivityCard } from '..'

const HOUR = 3600000
const entry = (i, action = 'create') => ({ action, message: `event ${i}`, user: 'admin', timestamp: new Date(Date.now() - i * HOUR).toISOString() })

beforeEach(() => { vi.clearAllMocks(); ws.state = 'connected'; api.can.mockReturnValue(true) })

describe('latest operations', () => {
  it('gives each operation its delay, with the exact date in the tooltip', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(3)] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    const time = (await screen.findByText('event 3')).closest('li').querySelector('time')
    expect(time.textContent).toBe('3 hours ago')
    expect(time.getAttribute('title')).toMatch(/\d{4}/)
    expect(time.getAttribute('datetime')).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('marks the list live while the link is up, and not when it is down', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1)] } })
    const view = render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    expect(screen.getByTestId('activity-live').textContent).toBe('common.live')
    view.unmount()
    ws.state = 'disconnected'
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    expect(screen.queryByTestId('activity-live')).toBeNull()
  })

  it('shows six rows at most, each with an icon, a failure standing out', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1, 'login_failed'), ...[2, 3, 4, 5, 6, 7, 8].map((i) => entry(i))] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    const rows = [...document.querySelectorAll('.ov-activity li')]
    expect(rows).toHaveLength(6)
    expect(api.getActivity).toHaveBeenCalledWith(6)
    for (const li of rows) expect(li.querySelector('svg')).not.toBeNull()
    expect(rows.map((li) => li.getAttribute('data-tone'))).toEqual(['bad', null, null, null, null, null])
  })

  it('says whose operations are listed', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1)] } })
    api.can.mockReturnValue(false)
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    expect(screen.getByTestId('card-activity').textContent).toContain('overview.activity.subOwn')
  })
})
