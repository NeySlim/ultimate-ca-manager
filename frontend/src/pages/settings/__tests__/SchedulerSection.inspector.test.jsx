/**
 * The scheduler's tasks open in an inspector (E4), drawn in the settings' dock slot: every column of the list, those
 * folded for want of room included, and the task's action; the task lives in the address (`item`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

// One translation function for every render, as react-i18next gives: the section reloads when it changes
const { notify, api, i18n } = vi.hoisted(() => ({
  notify: { showSuccess: vi.fn(), showInfo: vi.fn(), showError: vi.fn() },
  api: { getSchedulerTasks: vi.fn(), runSchedulerTask: vi.fn() },
  i18n: { t: (k, p) => (p?.count !== undefined ? `${k}:${p.count}` : p?.name ? `${k}:${p.name}` : k), i18n: { language: 'fr' } },
}))
vi.mock('react-i18next', () => ({ useTranslation: () => i18n }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../contexts', () => ({ useNotification: () => notify }))
vi.mock('../../../services', () => ({ systemService: api }))

import SchedulerSection from '../SchedulerSection'
import { DockSlot, DockSlotProvider } from '../../protocols/dockSlot'

function Loc() {
  return <output data-testid="loc">{useLocation().search}</output>
}
const page = (canRun = true, url = '/settings?tab=scheduler') => render(
  <MemoryRouter initialEntries={[url]}>
    <DockSlotProvider>
      <SchedulerSection hasPermission={() => canRun} />
      <DockSlot />
    </DockSlotProvider>
    <Loc />
  </MemoryRouter>,
)

beforeEach(() => {
  api.getSchedulerTasks.mockReset()
  api.runSchedulerTask.mockReset()
  api.getSchedulerTasks.mockResolvedValue({ data: { tasks: [
    { name: 'scheduled_backup', label: 'Scheduled backups', interval: 86400, last_run: '2026-11-20T10:00:00Z', next_run: '2026-11-21T10:00:00Z',
      last_duration_ms: 1400, run_count: 7, last_status: 'skipped', last_reason: 'not configured or disabled' },
    { name: 'crl_refresh', label: 'CRL refresh', interval: 3600, run_count: 2 },
  ], total: 2, warnings: 0 } })
  api.runSchedulerTask.mockResolvedValue({ data: {} })
})

describe('the scheduler inspector', () => {
  it('opens a task from its row: its name, its state and every column, the run at hand', async () => {
    page()
    // A task the test's translations do not know keeps the server's label
    fireEvent.click(await screen.findByRole('button', { name: 'table.openRow:Scheduled backups' }))
    expect(screen.getByTestId('loc').textContent).toContain('item=scheduled_backup')
    const dock = await screen.findByRole('complementary')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Scheduled backups')
    const terms = [...dock.querySelectorAll('dl.props dt')].map((d) => d.textContent)
    expect(terms).toEqual(['atelier.state', 'scheduler.colNote', 'scheduler.colSchedule', 'scheduler.colLastRun', 'scheduler.colNextRun',
      'scheduler.colDuration', 'scheduler.colRuns'])
    const value = (term) => [...dock.querySelectorAll('dl.props dt')].find((d) => d.textContent === term).nextElementSibling.textContent
    expect(value('scheduler.colSchedule')).toBe('scheduler.interval.daily')
    expect(value('scheduler.colRuns')).toBe('7')
    expect(value('scheduler.colDuration')).toBe('1,40 s')
    expect(value('scheduler.colLastRun')).toMatch(/2026/)
    expect(value('scheduler.colNote')).toContain('scheduler.skipped')
    // The action of its row, in the inspector
    fireEvent.click(within(dock).getByRole('button', { name: 'scheduler.runNow' }))
    expect(api.runSchedulerTask).toHaveBeenCalledWith('scheduled_backup')
    // The open row is the current one
    expect(document.querySelector('#scheduler-scroll tbody tr[aria-current="true"]')).toHaveTextContent('Scheduled backups')
  })

  it('reads the task from the address, offers no run without the right, and closes back to the list', async () => {
    page(false, '/settings?tab=scheduler&item=crl_refresh')
    const dock = await screen.findByRole('complementary')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('CRL refresh')
    expect(within(dock).queryByRole('button', { name: 'scheduler.runNow' })).toBeNull()
    fireEvent.click(within(dock).getByRole('button', { name: 'inspector.close' }))
    expect(screen.queryByRole('complementary')).toBeNull()
    expect(screen.getByTestId('loc').textContent).not.toContain('item=')
  })
})
