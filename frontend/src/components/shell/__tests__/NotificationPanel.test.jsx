/** Bell panel: grouped by day, line actions only where the API has one, the write guard, the mail foot. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ROLES, canFor, tStub } from './shellTestUtils'

const m = vi.hoisted(() => ({
  getQueue: vi.fn(), getLogs: vi.fn(), renewOrder: vi.fn(), regenerate: vi.fn(), getExpiryAlerts: vi.fn(),
  persistPreference: vi.fn(), prefs: {},
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o && o.state && o.count == null ? `${k}|${o.state}` : o && o.count != null ? `${k}|${o.count}` : o && o.date ? `${k}|${o.date}` : tStub(k, o)), i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../services/dashboard.service', () => ({ dashboardService: { getQueue: m.getQueue } }))
vi.mock('../../../services/audit.service', () => ({ default: { getLogs: m.getLogs } }))
vi.mock('../../../services', () => ({
  acmeService: { renewOrder: m.renewOrder }, crlService: { regenerate: m.regenerate },
  settingsService: { getExpiryAlerts: m.getExpiryAlerts },
}))
vi.mock('../../../hooks/useWebSocket', () => ({ useWebSocket: () => ({ lastEvent: null }) }))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../../../stores/userPreferencesStore', () => ({
  getPreferences: () => m.prefs,
  subscribePreferences: () => () => {},
  persistPreference: (key, value) => { m.persistPreference(key, value); m.prefs = { ...m.prefs, [key]: value } },
}))

import { NotificationBell } from '../NotificationBell'

const NOW = Date.parse('2026-11-08T12:00:00Z')
const QUEUE = { data: { counts: {}, items: [
  { kind: 'acme_client_renewal_failed', tier: 'critical', id: 11, label: 'cdn.example', due_at: '2026-11-08T05:40:00Z', href_hint: '/acme?tab=letsencryptorders&order=11' },
  { kind: 'acme_order_failed', tier: 'critical', id: 7, label: 'web.example', due_at: '2026-11-07T22:05:00Z', href_hint: '/acme?tab=localorders&order=7' },
  { kind: 'crl_missing', tier: 'critical', id: 3, label: 'Services CA', due_at: '2026-11-09T06:00:00Z', href_hint: '/crl-ocsp?ca=3' },
] } }

const health = (body) => vi.fn().mockResolvedValue({ ok: true, json: async () => body })

function setup(permissions = ROLES.admin) {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  render(<MemoryRouter><NotificationBell can={canFor(permissions)} /></MemoryRouter>)
  return user
}
const bell = () => screen.getByRole('button', { name: /^shell\.bell\.label\|/ })
const panel = () => screen.getByRole('complementary', { name: 'shell.bell.title' })
const row = (key) => panel().querySelector(`[data-notification="${key}"]`)

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  m.getQueue.mockReset().mockResolvedValue(QUEUE)
  m.getLogs.mockReset().mockResolvedValue({ data: [] })
  m.renewOrder.mockReset().mockResolvedValue({})
  m.regenerate.mockReset().mockResolvedValue({})
  m.getExpiryAlerts.mockReset().mockResolvedValue({ data: { enabled: true } })
  m.persistPreference.mockReset()
  m.prefs = {}
  vi.stubGlobal('fetch', health({ status: 'ok', ha: false }))
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

async function open(user) {
  await waitFor(() => expect(bell()).toHaveAccessibleName(/shell\.bell\.unread\|3/))
  await user.click(bell())
}

describe('Notification panel', () => {
  it('groups the items by day, today first, a future due date under today', async () => {
    const user = setup()
    await open(user)
    const days = within(panel()).getAllByRole('heading', { level: 3 }).map(h => h.textContent)
    expect(days).toHaveLength(2)
    expect(days[0]).toMatch(/^shell\.bell\.today\|/)
    expect(days[1]).toMatch(/^shell\.bell\.yesterday\|/)
    const today = panel().querySelectorAll('.shell-notif-group')[0]
    expect([...today.querySelectorAll('[data-notification]')].map(li => li.dataset.notification))
      .toEqual(['crl_missing:3', 'acme_client_renewal_failed:11'])
    expect(row('acme_client_renewal_failed:11').querySelector('time')).toHaveAttribute('dateTime', '2026-11-08T05:40:00.000Z')
  })

  it('offers Retry on a failed ACME renewal and calls the API, then marks the line read', async () => {
    const user = setup()
    await open(user)
    await user.click(within(row('acme_client_renewal_failed:11')).getByRole('button', { name: /shell\.bell\.retryLabel/ }))
    expect(m.renewOrder).toHaveBeenCalledWith(11)
    await waitFor(() => expect(m.persistPreference).toHaveBeenCalledWith('notifications_read', ['acme_client_renewal_failed:11']))
  })

  it('offers Publish on a CRL and calls the API', async () => {
    const user = setup()
    await open(user)
    await user.click(within(row('crl_missing:3')).getByRole('button', { name: /shell\.bell\.publishLabel/ }))
    expect(m.regenerate).toHaveBeenCalledWith(3)
  })

  it('offers no action without a route: a failed order of the ACME server only opens', async () => {
    const user = setup()
    await open(user)
    const buttons = within(row('acme_order_failed:7')).getAllByRole('button').map(b => b.textContent)
    expect(buttons).toEqual(['shell.bell.markRead'])
    expect(within(row('acme_order_failed:7')).getByRole('link')).toHaveAttribute('href', '/acme?tab=localorders&order=7')
  })

  it('shows no Retry nor Publish without the write rights', async () => {
    const user = setup(['read:dashboard', 'read:acme', 'read:crl'])
    await open(user)
    expect(within(panel()).queryByRole('button', { name: /shell\.bell\.(retry|publish)Label/ })).toBeNull()
  })

  it('disables the line actions during a cluster maintenance and says why', async () => {
    vi.stubGlobal('fetch', health({ status: 'ok', ha: true, node_id: 'n1', cluster: { nodes: 2, stale: 0, leader_node_id: 'n1' },
      maintenance: { reason: 'restore', phase: 'draining' } }))
    const user = setup()
    await open(user)
    const retry = within(row('acme_client_renewal_failed:11')).getByRole('button', { name: /shell\.bell\.retryLabel/ })
    await waitFor(() => expect(retry).toBeDisabled())
    expect(retry).toHaveAttribute('aria-describedby', 'shell-writes-note')
    await user.click(retry)
    expect(m.renewOrder).not.toHaveBeenCalled()
  })

  it('says whether mail notification is on and links to its settings, for who may read them', async () => {
    const user = setup()
    await open(user)
    await waitFor(() => expect(within(panel()).getByText(/shell\.bell\.mailOn/)).toBeInTheDocument())
    expect(within(panel()).getByRole('link', { name: 'shell.bell.mailSettings' })).toHaveAttribute('href', '/settings?tab=email')
  })

  it('has no mail foot without read:settings', async () => {
    const user = setup(['read:dashboard'])
    await open(user)
    expect(within(panel()).queryByRole('link', { name: 'shell.bell.mailSettings' })).toBeNull()
    expect(m.getExpiryAlerts).not.toHaveBeenCalled()
  })
})
