/**
 * The real cards under the real figures strip: a route two of them read is requested once,
 * at load and at each reload, whether or not its card is shown.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k, o) => (o?.defaultValue ?? k) }) }))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getHealth: vi.fn(), getCompliance: vi.fn(), getIssuance: vi.fn(), getCertStats: vi.fn(),
  getCas: vi.fn(), getNext: vi.fn(), getActivity: vi.fn(), getStats: vi.fn(), getTrend: vi.fn(), getStatus: vi.fn(),
}))
vi.mock('../../services', () => ({
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getCompliance: api.getCompliance, getIssuance: api.getIssuance },
  certificatesService: { getStats: api.getCertStats },
  casService: { getAll: api.getCas },
  dashboardService: { getNextExpirations: api.getNext, getActivityLog: api.getActivity, getStats: api.getStats,
    getCertificateTrend: api.getTrend, getSystemStatus: api.getStatus },
}))
vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ isAdmin: () => true, hasPermission: () => true, canWrite: () => true }),
}))
vi.mock('../../components/KofiSupportCard', () => ({ KofiSupportCard: () => null }))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => ({}) }))
const store = vi.hoisted(() => ({ prefs: {} }))
vi.mock('../../stores/userPreferencesStore', () => ({
  getPreferences: () => store.prefs, persistPreference: vi.fn(), subscribePreferences: () => () => {},
}))

import OverviewPage from '../OverviewPage'
import { REFRESH_EVENT } from '../../lib/overviewRefresh'

const calls = () => Object.fromEntries(Object.entries(api).map(([name, fn]) => [name, fn.mock.calls.length]))
const ONCE = Object.fromEntries(Object.keys(api).map((name) => [name, 1]))

beforeEach(() => {
  vi.clearAllMocks()
  store.prefs = {}
  api.getQueue.mockResolvedValue({ data: { items: [{ kind: 'manual_renewal_due', tier: 'warning', id: 1, label: 'cert-one', href_hint: '/certificates/1' }], counts: { manual_renewal_due: 1 }, total: 1 } })
  api.getHealth.mockResolvedValue({ data: { days: 7, protocols: { acme: { periods: [{ date: 'd', ok: 1, failed: 2 }], last_status: 'ok' } } } })
  api.getCompliance.mockResolvedValue({ data: { total: 1, counters: {}, by_key_algorithm: [] } })
  api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
  api.getCertStats.mockResolvedValue({ data: { total: 4, expiring: 1, expired: 1 } })
  api.getCas.mockResolvedValue({ data: [{ id: 1, refid: 'r', descr: 'Root' }], meta: { total: 1 } })
  api.getNext.mockResolvedValue({ data: [] })
  api.getActivity.mockResolvedValue({ data: { activity: [{ action: 'create', message: 'made', user: 'u', timestamp: null }] } })
  api.getStats.mockResolvedValue({ data: { total_certificates: 4, total_cas: 1, valid: 2, expiring_soon: 1, expired: 1, revoked: 0 } })
  api.getTrend.mockResolvedValue({ data: { trend: [{ date: '2026-11-19', issued: 1, revoked: 0, expired: 0 }] } })
  api.getStatus.mockResolvedValue({ data: {} })
})

const loaded = async () => {
  await waitFor(() => expect(screen.getByTestId('metric-failures').querySelector('.ov-metric-value').textContent).toBe('2'))
  await waitFor(() => expect(screen.queryAllByRole('status')).toHaveLength(0))
}

describe('requests of the overview', () => {
  it('asks each route once when the page opens, the strip and its cards sharing theirs', async () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    expect(calls()).toEqual(ONCE)
    // Both readers got the answer
    expect(screen.getByTestId('metric-queue').querySelector('.ov-metric-value').textContent).toBe('1')
    expect(screen.getByText('cert-one')).toBeTruthy()
    expect(screen.getByTestId('metric-certificates').querySelector('.ov-metric-value').textContent).toBe('4')
    expect(screen.getByTestId('states-donut')).toBeTruthy()
  })

  it('the refresh button asks each card route once more, not twice', async () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'overview.refresh' })) })
    await waitFor(() => expect(api.getActivity).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(api.getQueue).toHaveBeenCalledTimes(2))
    expect(calls()).toEqual({ ...Object.fromEntries(Object.keys(api).map((name) => [name, 2])), getStatus: 1 })
  })

  it('with the queue and health cards hidden, the strip still gets its figures, once', async () => {
    store.prefs = { dashboard: { hidden: ['queue', 'health', 'states'] } }
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    expect(screen.queryByTestId('card-queue')).toBeNull()
    expect(calls()).toEqual(ONCE)
    // No card to lead to: the figures are plain
    expect(screen.getByTestId('metric-queue').tagName).toBe('DIV')
    expect(screen.getByTestId('metric-failures').tagName).toBe('DIV')
  })

  it('a figure of the strip leads to its card when the card is shown', async () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    fireEvent.click(screen.getByTestId('metric-queue'))
    expect(document.activeElement).toBe(screen.getByTestId('card-queue').querySelector('h2'))
    fireEvent.click(screen.getByTestId('metric-failures'))
    expect(document.activeElement).toBe(screen.getByTestId('card-health').querySelector('h2'))
  })

  it('a failure shared by two readers reaches both', async () => {
    api.getQueue.mockRejectedValue(Object.assign(new Error('down'), { status: 500 }))
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('card-queue').textContent).toContain('overview.state.error'))
    expect(screen.getByTestId('metric-queue').querySelector('.ov-metric-value').textContent).toBe('–')
    expect(api.getQueue).toHaveBeenCalledTimes(1)
  })
})
