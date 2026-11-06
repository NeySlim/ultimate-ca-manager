/**
 * Scheduler page: a run still going in the scheduler process says it started,
 * not that it ran, and a state the process stopped publishing is flagged.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Stable references: the page reloads whenever t or showError change
const { notify, api, i18n } = vi.hoisted(() => ({
  notify: { showSuccess: vi.fn(), showInfo: vi.fn(), showError: vi.fn() },
  api: { getSchedulerTasks: vi.fn(), runSchedulerTask: vi.fn() },
  i18n: { t: (key) => key },
}))

vi.mock('react-i18next', () => ({ useTranslation: () => i18n }))
vi.mock('../../../contexts', () => ({ useNotification: () => notify }))
vi.mock('../../../services', () => ({ systemService: api }))
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

import SchedulerSection from '../SchedulerSection'

const task = { name: 'scheduled_backup', label: 'Scheduled backups', interval: 3600, run_count: 1 }

const listed = (stale) => {
  api.getSchedulerTasks.mockResolvedValue({ data: { tasks: [task], total: 1, warnings: 0, stale } })
}

beforeEach(() => {
  vi.clearAllMocks()
})

const runNow = async (data) => {
  listed(false)
  api.runSchedulerTask.mockResolvedValue({ data, message: 'x' })
  render(<SchedulerSection hasPermission={() => true} />)
  fireEvent.click(await screen.findByText('scheduler.runNow'))
  await waitFor(() => expect(api.runSchedulerTask).toHaveBeenCalled())
}

describe('SchedulerSection run now', () => {
  it('says the task ran once it has', async () => {
    await runNow({ ...task, run_count: 2 })
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('scheduler.taskRan'))
    expect(notify.showInfo).not.toHaveBeenCalled()
  })

  it('says the task started when it is still running', async () => {
    await runNow({ ...task, queued: true })
    await waitFor(() => expect(notify.showInfo).toHaveBeenCalledWith('scheduler.taskQueued'))
    expect(notify.showSuccess).not.toHaveBeenCalled()
  })
})

describe('SchedulerSection stale state', () => {
  it('warns when the scheduler process stopped reporting', async () => {
    listed(true)
    render(<SchedulerSection hasPermission={() => true} />)
    expect(await screen.findByText('scheduler.stateStale')).toBeTruthy()
  })

  it('says nothing while it reports', async () => {
    listed(false)
    render(<SchedulerSection hasPermission={() => true} />)
    await screen.findByText('scheduler.runNow')
    expect(screen.queryByText('scheduler.stateStale')).toBeNull()
  })
})
