/** Latest operations: a timeline by day, successive sign-ins folded, each entry with its time and the exact date behind it. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({ t: (k, o) => (o && Object.keys(o).length > 0 ? `${k}:${Object.values(o).join(',')}` : k) }),
}))
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

const login = (i, user = 'admin') => ({ action: 'login_success', message: 'Logged in', user, timestamp: new Date(Date.now() - i * 60000).toISOString() })
const rowsOf = () => [...document.querySelectorAll('#card-activity .activity-row')]

describe('latest operations', () => {
  it('draws each operation on the timeline: icon, operation, object, who, time with the exact date in the tooltip', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(3)] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    const row = (await screen.findByText('event 3')).closest('.activity-row')
    expect(row.tagName).toBe('LI')
    expect(row.closest('ol.timeline')).not.toBeNull()
    expect([...row.children].map((c) => c.tagName.toLowerCase())).toEqual(['svg', 'div', 'time'])
    expect(row.querySelector('strong').textContent).toBe('Cert created')
    expect(row.querySelector('.muted.small').textContent).toBe('admin')
    expect(row.dataset.family).toBe('issued')
    const time = row.querySelector('time')
    expect(time.textContent).toMatch(/^\d{2}:\d{2}$/)
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

  it('folds successive sign-ins of one user into one line with their count and time span', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [login(1), login(2), login(3), login(4), login(5), entry(6)] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 6')
    const rows = rowsOf()
    expect(rows).toHaveLength(2)
    expect(rows[0].dataset.folded).toBe('5')
    expect(rows[0].querySelector('button').textContent).toBe('overview.activity.folded:5,admin')
    expect(rows[0].querySelector('time').textContent).toMatch(/^overview\.activity\.span:\d{2}:\d{2},\d{2}:\d{2}$/)
    fireEvent.click(rows[0].querySelector('button'))
    expect(nav).toHaveBeenCalledWith('/audit?search=login_success')
  })

  it('reads fifty entries and shows six lines at most, a failure standing out', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [entry(1, 'login_failed'), ...[2, 3, 4, 5, 6, 7, 8].map((i) => entry(i))] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    const rows = rowsOf()
    expect(rows).toHaveLength(6)
    expect(api.getActivity).toHaveBeenCalledWith(50)
    for (const row of rows) expect(row.querySelector('svg')).not.toBeNull()
    expect(rows.map((row) => row.getAttribute('data-tone'))).toEqual(['bad', null, null, null, null, null])
  })

  it('groups the lines under their day', async () => {
    const days = (n) => new Date(Date.now() - n * 86400000).toISOString()
    api.getActivity.mockResolvedValue({ data: { activity: [
      { ...entry(0), timestamp: new Date().toISOString() },
      { ...entry(1), message: 'event y', timestamp: days(1) },
      { ...entry(2), message: 'event old', timestamp: days(5) },
    ] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event old')
    expect([...document.querySelectorAll('.tl-day > h3')].map((h) => h.textContent).slice(0, 2)).toEqual(['overview.activity.today', 'overview.activity.yesterday'])
    expect(document.querySelectorAll('.tl-day')).toHaveLength(3)
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

describe('latest operations: Tout, PKI, Accès', () => {
  const rows = [entry(1, 'cert_revoked'), login(2), entry(3, 'user_created'), entry(4, 'settings_updated'), entry(5, 'crl_generated')]
  const families = () => rowsOf().map((r) => r.dataset.family)

  it('shows everything first, then the PKI operations only, then the sign-ins and accounts only', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: rows } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('event 1')
    expect(screen.getByRole('button', { name: 'overview.activity.filter.all' }).getAttribute('aria-pressed')).toBe('true')
    expect(families()).toEqual(['revoked', 'auth', 'users', 'settings', 'crl'])
    fireEvent.click(screen.getByRole('button', { name: 'overview.activity.filter.pki' }))
    expect(families()).toEqual(['revoked', 'crl'])
    fireEvent.click(screen.getByRole('button', { name: 'overview.activity.filter.access' }))
    expect(families()).toEqual(['auth', 'users'])
  })

  it('says in one line that a filter keeps nothing', async () => {
    api.getActivity.mockResolvedValue({ data: { activity: [login(1)] } })
    render(<MemoryRouter><ActivityCard /></MemoryRouter>)
    await screen.findByText('overview.activity.filter.pki')
    fireEvent.click(screen.getByRole('button', { name: 'overview.activity.filter.pki' }))
    expect(screen.getByText('overview.activity.noneOfKind:overview.activity.filter.pki')).toBeTruthy()
  })
})
