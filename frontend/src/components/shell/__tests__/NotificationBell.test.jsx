/** Bell: items from the queue and the journal only, counter = unread items, rights, read marks, refresh. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ROLES, canFor, tStub } from './shellTestUtils'

const m = vi.hoisted(() => ({
  getQueue: vi.fn(), getLogs: vi.fn(), persistPreference: vi.fn(),
  prefs: {}, listeners: new Set(), lastEvent: null, extraLogs: [],
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o && o.count != null ? `${k}|${o.count}` : tStub(k, o)), i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../services/dashboard.service', () => ({ dashboardService: { getQueue: m.getQueue } }))
vi.mock('../../../services/audit.service', () => ({ default: { getLogs: m.getLogs } }))
vi.mock('../../../hooks/useWebSocket', () => ({ useWebSocket: () => ({ lastEvent: m.lastEvent }) }))
vi.mock('../../../stores/userPreferencesStore', () => ({
  getPreferences: () => m.prefs,
  subscribePreferences: (cb) => { m.listeners.add(cb); return () => m.listeners.delete(cb) },
  persistPreference: (key, value) => {
    m.persistPreference(key, value)
    m.prefs = { ...m.prefs, [key]: value }
    m.listeners.forEach(cb => cb(m.prefs))
  },
}))

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { NotificationBell } from '../NotificationBell'
import { REQUEST_REFUSED } from '../notifications'

const QUEUE = { data: { counts: {}, items: [
  { kind: 'acme_order_failed', tier: 'critical', id: 7, label: 'web.example', due_at: '2026-11-09T10:00:00Z', href_hint: '/acme?tab=orders&order=7' },
  { kind: 'approval_pending', tier: 'warning', id: 3, label: 'Sign CSR', due_at: null, href_hint: '/approvals?request=3' },
  { kind: 'client_renewal_overdue', tier: 'warning', id: 9, label: 'noise', due_at: null, href_hint: '/certificates' },
] } }
const LOGS = { data: [
  { id: 41, action: 'system_backup', success: false, username: 'root', resource_name: null, timestamp: '2026-11-09T09:00:00Z' },
  { id: 42, action: 'system_backup', success: true, username: 'root', resource_name: null, timestamp: '2026-11-09T08:00:00Z' },
  { id: 43, action: 'session_revoke', success: true, username: 'alice', resource_name: null, timestamp: '2026-11-09T07:00:00Z' },
] }

function setup(permissions = ROLES.admin) {
  const user = userEvent.setup()
  render(<MemoryRouter><NotificationBell can={canFor(permissions)} /></MemoryRouter>)
  return user
}
const bell = () => screen.getByRole('button', { name: /shell\.bell\.title/ })

beforeEach(() => {
  m.getQueue.mockReset().mockResolvedValue(QUEUE)
  // The server filters: sessions in one request, failed backups/restores in the other
  // Newest first, filtered by the server, then cut to the page like the API does
  m.getLogs.mockReset().mockImplementation(async params => ({
    data: [...LOGS.data, ...(m.extraLogs || [])]
      .filter(e => params.action.includes(e.action) && (params.success === undefined || e.success === params.success))
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      .slice(0, params.per_page ?? 50),
  }))
  m.persistPreference.mockReset()
  m.prefs = {}
  m.extraLogs = []
  m.listeners.clear()
  m.lastEvent = null
})
afterEach(() => { vi.useRealTimers() })

describe('NotificationBell', () => {
  it('lists critical queue items, approvals and notable journal events, nothing else', async () => {
    const user = setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/shell\.bell\.unread\|4/))
    await user.click(bell())
    const panel = screen.getByRole('region', { name: 'shell.bell.title' })
    const rows = within(panel).getAllByRole('listitem').map(li => li.getAttribute('data-notification'))
    expect(rows).toEqual(['acme_order_failed:7', 'approval_pending:3', 'audit:41', 'audit:43'])
    expect(m.getQueue).toHaveBeenCalledWith(expect.arrayContaining(['acme_order_failed', 'approval_pending']))
  })

  it('shows a count equal to the unread items of the panel', async () => {
    const user = setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|4/))
    await user.click(bell())
    const unread = document.querySelectorAll('.shell-bell-item.is-unread').length
    expect(bell()).toHaveAccessibleName(`shell.bell.title: shell.bell.unread|${unread}`)
    await user.click(screen.getByRole('button', { name: /shell\.bell\.markRead: web\.example/ }))
    expect(document.querySelectorAll('.shell-bell-item.is-unread').length).toBe(unread - 1)
    expect(bell()).toHaveAccessibleName(`shell.bell.title: shell.bell.unread|${unread - 1}`)
    expect(m.persistPreference).toHaveBeenLastCalledWith('notifications_read', ['acme_order_failed:7'])
  })

  it('marks everything read in one write, and says so', async () => {
    const user = setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|4/))
    await user.click(bell())
    await user.click(screen.getByRole('button', { name: 'shell.bell.markAllRead' }))
    expect(m.persistPreference).toHaveBeenCalledTimes(1)
    expect(m.persistPreference.mock.calls[0][1]).toHaveLength(4)
    expect(bell()).toHaveAccessibleName('shell.bell.title: shell.bell.allRead')
    expect(screen.getByRole('status')).toHaveTextContent('shell.bell.allRead')
  })

  it('reads the marks from the user preferences and drops marks of items that left', async () => {
    m.prefs = { notifications_read: ['approval_pending:3', 'gone:1'] }
    const user = setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|3/))
    await user.click(bell())
    await user.click(screen.getByRole('button', { name: /shell\.bell\.markRead: web\.example/ }))
    expect(m.persistPreference).toHaveBeenLastCalledWith('notifications_read', ['approval_pending:3', 'acme_order_failed:7'])
  })

  it('opens the page of the item through its href_hint and marks it read', async () => {
    const user = setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|4/))
    await user.click(bell())
    const link = screen.getByRole('link', { name: /shell\.bell\.open: web\.example/ })
    expect(link).toHaveAttribute('href', '/acme?tab=orders&order=7')
    await user.click(link)
    expect(m.persistPreference).toHaveBeenLastCalledWith('notifications_read', ['acme_order_failed:7'])
  })

  it('asks only the sources the user may read, and shows no error for the others', async () => {
    setup(ROLES.operator)   // no read:dashboard, no read:audit
    await act(async () => {})
    expect(m.getQueue).not.toHaveBeenCalled()
    expect(m.getLogs).not.toHaveBeenCalled()
    expect(bell()).toHaveAccessibleName('shell.bell.title: shell.bell.allRead')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('an auditor sees the journal events but never the queue', async () => {
    setup(['read:audit'])
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|2/))
    expect(m.getQueue).not.toHaveBeenCalled()
  })

  it('a refused source (403) empties it without an error', async () => {
    m.getQueue.mockRejectedValue(Object.assign(new Error('Forbidden'), { status: 403 }))
    setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|2/))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('refreshes when the panel opens and after a real-time event, without polling', async () => {
    const user = setup()
    await waitFor(() => expect(m.getQueue).toHaveBeenCalledTimes(1))
    await user.click(bell())
    await waitFor(() => expect(m.getQueue).toHaveBeenCalledTimes(2))
    vi.useFakeTimers()
    await act(async () => { vi.advanceTimersByTime(5 * 60 * 1000) })
    expect(m.getQueue).toHaveBeenCalledTimes(2)
  })

  it('refreshes after a WebSocket event', async () => {
    const { rerender } = render(<MemoryRouter><NotificationBell can={canFor(ROLES.admin)} /></MemoryRouter>)
    await waitFor(() => expect(m.getQueue).toHaveBeenCalledTimes(1))
    m.lastEvent = { type: 'approval.created' }
    rerender(<MemoryRouter><NotificationBell can={canFor(ROLES.admin)} /></MemoryRouter>)
    await waitFor(() => expect(m.getQueue).toHaveBeenCalledTimes(2), { timeout: 3000 })
  })

  it('moves the focus to the panel title on open and back to the bell on Escape', async () => {
    const user = setup()
    await user.click(bell())
    expect(screen.getByRole('heading', { name: 'shell.bell.title' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(bell()).toHaveFocus()
  })

  it('asks for failed backups and restores in their own request, and for nothing else', async () => {
    setup()
    await waitFor(() => expect(m.getLogs).toHaveBeenCalledWith(
      expect.objectContaining({ action: ['system_backup', 'system_restore'], success: false })))
  })

  it('brings a failed restore back to the bell', async () => {
    m.extraLogs = [
      { id: 60, action: 'system_restore', success: false, username: 'root', resource_name: 'b.ucmbkp', timestamp: '2026-11-09T11:00:00Z' },
      { id: 61, action: 'system_restore', success: true, username: 'root', resource_name: 'b.ucmbkp', timestamp: '2026-11-09T12:00:00Z' },
    ]
    setup()
    const user = userEvent.setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|5/))
    await user.click(bell())
    const rows = within(screen.getByRole('region', { name: 'shell.bell.title' })).getAllByRole('listitem').map(li => li.getAttribute('data-notification'))
    expect(rows).toContain('audit:60')
    expect(rows).not.toContain('audit:61')
  })

  it('ignores a restore the form refused before it started', async () => {
    const refused = ['Restore request refused: no file provided', 'Restore request refused: mode not allowed here',
      'Restore request refused: a future refusal', 'Restore refused: password missing']
    m.extraLogs = [
      ...refused.map((details, i) => ({ id: 70 + i, action: 'system_restore', success: false, username: 'root',
        resource_name: 'upload', details, timestamp: '2026-11-09T11:00:00Z' })),
      { id: 80, action: 'system_restore', success: false, username: 'root', resource_name: 'b.ucmbkp',
        details: 'Restore failed: unexpected error', timestamp: '2026-11-09T11:30:00Z' },
    ]
    setup()
    const user = userEvent.setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|5/))
    await user.click(bell())
    const rows = within(screen.getByRole('region', { name: 'shell.bell.title' })).getAllByRole('listitem').map(li => li.getAttribute('data-notification'))
    expect(rows).toContain('audit:80')
    for (let i = 0; i < refused.length; i++) expect(rows).not.toContain(`audit:${70 + i}`)
  })

  it('keeps a failed backup in the bell when 25 newer backups succeeded', async () => {
    m.extraLogs = Array.from({ length: 25 }, (_, i) => ({
      id: 100 + i, action: 'system_backup', success: true, username: 'root', resource_name: null,
      timestamp: `2026-11-10T${String(i).padStart(2, '0')}:00:00Z`,
    }))
    setup()
    await waitFor(() => expect(bell()).toHaveAccessibleName(/\|4/))
    const user = userEvent.setup()
    await user.click(bell())
    const rows = within(screen.getByRole('region', { name: 'shell.bell.title' })).getAllByRole('listitem').map(li => li.getAttribute('data-notification'))
    expect(rows).toContain('audit:41')
    expect(rows).not.toContain('audit:100')
  })

  it('keys on the marker the backend writes for a refused restore request', () => {
    const here = dirname(fileURLToPath(import.meta.url))
    const source = readFileSync(join(here, '..', '..', '..', '..', '..', 'backend', 'services', 'backup', 'restore_completion.py'), 'utf8')
    expect(source).toMatch(/^REQUEST_REFUSED = '([^']+)'$/m)
    expect(source.match(/^REQUEST_REFUSED = '([^']+)'$/m)[1]).toBe(REQUEST_REFUSED)
  })
})
