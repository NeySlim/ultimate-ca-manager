/**
 * Scheduler table in the interface language: intervals, last and next runs in the compact
 * relative form (minutes under an hour), task names translated, the server's label kept
 * for a task the interface does not know.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'

const KNOWN = new Set(['scheduler.tasks.scheduled_backup'])
const { notify, api, i18n } = vi.hoisted(() => ({
  notify: { showSuccess: vi.fn(), showInfo: vi.fn(), showError: vi.fn() },
  api: { getSchedulerTasks: vi.fn(), runSchedulerTask: vi.fn() },
  i18n: {
    t: (key, opts) => (key.startsWith('scheduler.tasks.') && !KNOWN.has(key) ? key
      : opts?.count !== undefined ? `${key}:${opts.count}` : key.startsWith('scheduler.tasks.') ? `tr(${key})` : key),
    i18n: { language: 'fr' },
  },
}))
vi.mock('react-i18next', () => ({ useTranslation: () => i18n }))
vi.mock('../../../contexts', () => ({ useNotification: () => notify }))
vi.mock('../../../services', () => ({ systemService: api }))
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
}))

import SchedulerSection from '../SchedulerSection'

const NOW = new Date('2026-11-20T12:00:00Z')
const at = (ms) => new Date(NOW.getTime() + ms).toISOString()

beforeEach(() => {
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  api.getSchedulerTasks.mockResolvedValue({ data: { tasks: [
    { name: 'scheduled_backup', label: 'Scheduled backups', interval: 21600, last_run: at(-56 * 60000), next_run: at(5 * 3600000), last_duration_ms: 1.4, run_count: 3 },
    { name: 'brand_new_task', label: 'Brand new task', interval: 86400, last_run: at(-13 * 3600000), next_run: at(-30000), run_count: 1 },
  ], total: 2, warnings: 0 } })
})
afterEach(() => vi.useRealTimers())

describe('SchedulerSection words', () => {
  it('words intervals and runs through the translations, minutes under an hour', async () => {
    render(<SchedulerSection hasPermission={() => false} />)
    const backup = (await screen.findByText('tr(scheduler.tasks.scheduled_backup)')).closest('tr')
    const cells = within(backup).getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(1, 5)).toEqual(['scheduler.interval.everyHours:6', 'time.compact.minutesAgo:56', 'time.compact.inHours:5', '1,4 ms'])
    const other = screen.getByText('Brand new task').closest('tr')
    const more = within(other).getAllByRole('cell').map((c) => c.textContent)
    expect(more.slice(1, 4)).toEqual(['scheduler.interval.daily', 'time.compact.hoursAgo:13', 'time.compact.minutesAgo:1'])
  })
})
