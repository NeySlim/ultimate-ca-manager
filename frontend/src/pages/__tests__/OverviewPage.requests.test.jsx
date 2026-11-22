/**
 * The real cards under the real figures strip: a route two of them read is requested once,
 * at load and at each reload, whether or not its card is shown.
 */
// The setup assistant reads the shared counters; an instance with certificates asks nothing more
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ Trans: ({ i18nKey }) => i18nKey, useTranslation: () => ({ t: (k, o) => (o?.defaultValue ?? k) }) }))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getHealth: vi.fn(), getCompliance: vi.fn(), getIssuance: vi.fn(), getCertStats: vi.fn(),
  getCas: vi.fn(), getNext: vi.fn(), getActivity: vi.fn(), getStats: vi.fn(), getTrend: vi.fn(), getStatus: vi.fn(),
  getScores: vi.fn(),
}))
vi.mock('../../services', () => ({
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getCompliance: api.getCompliance, getIssuance: api.getIssuance },
  certificatesService: { getStats: api.getCertStats, getComplianceStats: api.getScores },
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
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => ({ showInfo: vi.fn() }) }))
const store = vi.hoisted(() => ({ prefs: {} }))
vi.mock('../../stores/userPreferencesStore', () => ({
  getPreferences: () => store.prefs, persistPreference: vi.fn(), subscribePreferences: () => () => {},
}))

import OverviewPage from '../OverviewPage'

const calls = () => Object.fromEntries(Object.entries(api).map(([name, fn]) => [name, fn.mock.calls.length]))
// No card reads the certificates' own counters any more: the horizon shares the dashboard's
const ONCE = { ...Object.fromEntries(Object.keys(api).map((name) => [name, 1])), getCertStats: 0 }
const metric = (id) => document.querySelector(`[data-metric="${id}"]`)
const value = (id) => metric(id).querySelector('.value').textContent

beforeEach(() => {
  vi.clearAllMocks()
  store.prefs = {}
  api.getQueue.mockResolvedValue({ data: { items: [{ kind: 'manual_renewal_due', tier: 'warning', id: 1, label: 'cert-one', href_hint: '/certificates/1' }], counts: { manual_renewal_due: 1 }, total: 1 } })
  api.getHealth.mockResolvedValue({ data: { days: 7, protocols: { acme: { periods: [{ date: 'd', ok: 1, failed: 2 }], last_status: 'ok' } } } })
  api.getCompliance.mockResolvedValue({ data: { total: 1, counters: {}, by_key_algorithm: [] } })
  api.getScores.mockResolvedValue({ data: { average_score: 90, distribution: { A: 1 }, total: 1 } })
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
  await waitFor(() => expect(value('failures')).toBe('2'))
  await waitFor(() => expect(document.querySelectorAll('.sk-card')).toHaveLength(0))
}

describe('requests of the overview', () => {
  it('asks each route once when the page opens, the strip and its cards sharing theirs', async () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    expect(calls()).toEqual(ONCE)
    // Both readers got the answer
    expect(value('queue')).toBe('1')
    expect(screen.getByText('cert-one')).toBeTruthy()
    expect(value('certificates')).toBe('4')
    expect(screen.getByText('overview.horizon.state.valid').parentElement.querySelector('strong').textContent).toBe('2')
    // The strip and the hierarchy read one issuance window, the strip and the health card one health window
    expect(api.getIssuance).toHaveBeenCalledWith(30)
    expect(api.getHealth).toHaveBeenCalledWith(30)
  })

  it('the refresh button asks each card route once more, not twice', async () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'overview.refresh' })) })
    await waitFor(() => expect(api.getActivity).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(api.getQueue).toHaveBeenCalledTimes(2))
    expect(calls()).toEqual({ ...Object.fromEntries(Object.keys(api).map((name) => [name, 2])), getStatus: 1, getCertStats: 0 })
  })

  it('with the queue and health cards hidden, the strip still gets its figures, once', async () => {
    store.prefs = { dashboard: { hidden: ['queue', 'health'] } }
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    expect(document.getElementById('card-queue')).toBeNull()
    expect(calls()).toEqual(ONCE)
    // Both figures bring the queue card back (the mockup's showQueue), the failures filtered on ACME
    expect(metric('failures').getAttribute('href')).toBe('#card-queue')
    fireEvent.click(metric('queue'))
    await waitFor(() => expect(document.getElementById('card-queue')).not.toBeNull())
  })

  it('a figure of the strip leads to its card when the card is shown', async () => {
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    fireEvent.click(metric('queue'))
    await waitFor(() => expect(document.activeElement).toBe(document.getElementById('card-queue-title')))
  })

  it('the failures figure opens the queue filtered on the ACME failures', async () => {
    api.getQueue.mockResolvedValue({ data: {
      items: [
        { kind: 'manual_renewal_due', tier: 'warning', id: 1, label: 'cert-one', href_hint: '/certificates/1' },
        { kind: 'acme_order_failed', tier: 'critical', id: 7, label: 'order-seven', href_hint: '/acme?order=7' },
      ],
      counts: { manual_renewal_due: 1, acme_order_failed: 1 }, total: 2 } })
    store.prefs = { dashboard: { hidden: ['queue'] } }
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await loaded()
    fireEvent.click(metric('failures'))
    await waitFor(() => expect(document.getElementById('queue-chip-acme')?.getAttribute('aria-pressed')).toBe('true'))
    expect(screen.getByText('order-seven')).toBeTruthy()
    expect(screen.queryByText('cert-one')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(document.getElementById('card-queue-title')))
  })

  it('a failure shared by two readers reaches both', async () => {
    api.getQueue.mockRejectedValue(Object.assign(new Error('down'), { status: 500 }))
    render(<MemoryRouter><OverviewPage /></MemoryRouter>)
    await waitFor(() => expect(document.getElementById('card-queue').textContent).toContain('overview.state.errorTitle'))
    expect(value('queue')).toBe('–')
    expect(api.getQueue).toHaveBeenCalledTimes(1)
  })
})
