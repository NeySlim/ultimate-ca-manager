/** Latest operations: the mockup's activity rows, five at most, each with its time and the exact date behind it. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ Trans: ({ i18nKey }) => i18nKey, useTranslation: () => ({ t: (k) => k }) }))
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
const nav = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', async (orig) => ({ ...(await orig()), useNavigate: () => nav }))
const entry = (i, action = 'cert_created') => ({ action, message: `event ${i}`, user: 'admin', timestamp: new Date(Date.now() - i * HOUR).toISOString() })

beforeEach(() => { vi.clearAllMocks(); ws.state = 'connected'; api.can.mockReturnValue(true) })

describe('latest operations', () => {
  it('draws each operation as the mockup: icon, operation, object, who, time with the exact date in the tooltip', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(3)] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    const row = (await screen.findByText('event 3')).closest('.activity-row')
    expect([...row.children].map((c) => c.tagName.toLowerCase())).toEqual(['svg', 'div', 'time'])
    expect(row.querySelector('strong').textContent).toBe('Cert created')
    expect(row.querySelector('.muted.small').textContent).toBe('admin')
    const time = row.querySelector('time')
    expect(time.textContent).toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(time.getAttribute('title')).toMatch(/\d{4}/)
    expect(time.getAttribute('datetime')).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('the object opens the journal on that operation, for who may read the journal', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1, 'cert_revoked')] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'event 1' }))
    expect(nav).toHaveBeenCalledWith('/audit?search=cert_revoked')
    expect(screen.getByRole('link', { name: /overview.activity.all/ }).getAttribute('href')).toBe('/audit')
  })

  it('shows five rows at most, each with an icon, a failure standing out', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1, 'login_failed'), ...[2, 3, 4, 5, 6, 7, 8].map((i) => entry(i))] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    const rows = [...document.querySelectorAll('#card-activity .activity-row')]
    expect(rows).toHaveLength(5)
    expect(api.getActivity).toHaveBeenCalledWith(5)
    for (const row of rows) expect(row.querySelector('svg')).not.toBeNull()
    expect(rows.map((row) => row.getAttribute('data-tone'))).toEqual(['bad', null, null, null, null])
  })

  it('says whose operations are listed, and gives no journal link without the right to read it', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1)] } })
    api.can.mockReturnValue(false)
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    expect(document.getElementById('card-activity').textContent).toContain('overview.activity.subOwn')
    expect(screen.queryByRole('button', { name: 'event 1' })).toBeNull()
    expect(screen.queryByRole('link', { name: /overview.activity.all/ })).toBeNull()
  })
})
